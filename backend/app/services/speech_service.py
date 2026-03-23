import whisper
import torch
import numpy as np
from typing import Dict, List, Any, Optional
import tempfile
import os
import time
import logging
import io
import soundfile as sf
import librosa
from silero_vad import load_silero_vad, read_audio, get_speech_timestamps

from app.models.speech import VADSegment, ProsodyMetrics
from app.core.config import settings
from app.services.advanced_speech_service import AdvancedSpeechAnalysisService

logger = logging.getLogger(__name__)

class SpeechService:
    def __init__(self):
        self.whisper_model = None
        self.vad_model = None
        self.advanced_analysis_service = AdvancedSpeechAnalysisService()
        self._load_models()
    
    def _load_models(self):
        """Load speech processing models"""
        try:
            # Load Whisper model
            self.whisper_model = whisper.load_model(settings.WHISPER_MODEL)
            logger.info(f"Loaded Whisper model: {settings.WHISPER_MODEL}")
            
            # Load Silero VAD model
            self.vad_model = load_silero_vad()
            logger.info("Loaded Silero VAD model")
            
            logger.info("Speech service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to load speech models: {e}")
            raise
    
    async def transcribe_audio_streaming(self, audio_data: bytes, participant_id: str, room_id: str) -> Dict[str, Any]:
        """Transcribe audio with streaming support for real-time delivery"""
        try:
            start_time = time.time()
            
            # First, check if there's speech activity
            vad_segments = await self.detect_voice_activity(audio_data)
            
            if not vad_segments:
                return {
                    "text": "",
                    "confidence": 0.0,
                    "has_speech": False,
                    "processing_time": time.time() - start_time,
                    "vad_segments": []
                }
            
            # Save audio data to temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                # Use faster Whisper model for real-time processing
                # For streaming, we prioritize speed over accuracy
                result = self.whisper_model.transcribe(
                    temp_file_path,
                    language="en",  # Specify language for faster processing
                    task="transcribe",
                    fp16=torch.cuda.is_available(),  # Use FP16 if GPU available
                    verbose=False
                )
                
                processing_time = time.time() - start_time
                
                transcript_result = {
                    "text": result["text"].strip(),
                    "confidence": self._calculate_confidence(result),
                    "language": result.get("language", "en"),
                    "processing_time": processing_time,
                    "has_speech": True,
                    "segments": result.get("segments", []),
                    "vad_segments": [segment.model_dump() for segment in vad_segments],
                    "participant_id": participant_id,
                    "room_id": room_id,
                    "timestamp": time.time()
                }
                
                # Log performance metrics
                logger.info(f"Streaming transcription completed in {processing_time:.2f}s for participant {participant_id}")
                
                return transcript_result
                
            finally:
                # Clean up temporary file
                os.unlink(temp_file_path)
                
        except Exception as e:
            logger.error(f"Streaming transcription failed: {e}")
            return {
                "text": "",
                "confidence": 0.0,
                "has_speech": False,
                "processing_time": time.time() - start_time,
                "error": str(e),
                "participant_id": participant_id,
                "room_id": room_id
            }
    
    async def transcribe_audio(self, audio_data: bytes) -> Dict[str, Any]:
        """Transcribe audio using Whisper - handles WebM, WAV, and other formats"""
        try:
            start_time = time.time()
            
            # Detect format and use appropriate extension
            # WebM starts with 0x1A45DFA3
            if len(audio_data) >= 4 and audio_data[:4] == b'\x1a\x45\xdf\xa3':
                temp_suffix = ".webm"
            # WAV starts with 'RIFF'
            elif len(audio_data) >= 4 and audio_data[:4] == b'RIFF':
                temp_suffix = ".wav"
            else:
                # Default to webm for unknown formats
                temp_suffix = ".webm"
            
            # Save audio data to temporary file
            with tempfile.NamedTemporaryFile(suffix=temp_suffix, delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                # Whisper can handle various audio formats including WebM
                result = self.whisper_model.transcribe(
                    temp_file_path,
                    language="en",  # Specify language for faster processing
                    task="transcribe",
                    fp16=False,  # Use FP32 for CPU
                    verbose=False
                )
                
                processing_time = time.time() - start_time
                
                return {
                    "text": result["text"].strip(),
                    "confidence": self._calculate_confidence(result),
                    "language": result.get("language", "en"),
                    "processing_time": processing_time,
                    "has_speech": len(result["text"].strip()) > 0,
                    "segments": result.get("segments", [])
                }
                
            finally:
                # Clean up temporary file
                os.unlink(temp_file_path)
                
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return {
                "text": "",
                "confidence": 0.0,
                "has_speech": False,
                "processing_time": time.time() - start_time,
                "error": str(e)
            }
    
    def _calculate_confidence(self, whisper_result: Dict) -> float:
        """Calculate average confidence from Whisper segments"""
        segments = whisper_result.get("segments", [])
        if not segments:
            return 0.0
        
        # Average the confidence scores from all segments
        confidences = [segment.get("avg_logprob", 0.0) for segment in segments]
        # Convert log probabilities to confidence scores (0-1)
        avg_confidence = np.mean(confidences)
        # Transform to 0-1 range (rough approximation)
        confidence = max(0.0, min(1.0, (avg_confidence + 1.0) / 2.0))
        
        return confidence
    
    async def detect_voice_activity(self, audio_data: bytes) -> List[VADSegment]:
        """Detect voice activity using Silero VAD - handles WebM and other formats"""
        try:
            # Convert audio bytes to numpy array (handles WebM, WAV, etc.)
            audio_array = self._bytes_to_audio_array(audio_data)
            
            # Ensure audio is at the correct sample rate for VAD (16kHz)
            if len(audio_array.shape) > 1:
                # Convert stereo to mono if needed
                audio_array = np.mean(audio_array, axis=1)
            
            # Resample to 16kHz if needed
            if settings.SAMPLE_RATE != 16000:
                audio_array = librosa.resample(
                    audio_array, 
                    orig_sr=settings.SAMPLE_RATE, 
                    target_sr=16000
                )
            
            # Convert to torch tensor
            audio_tensor = torch.from_numpy(audio_array).float()
            
            # Get speech timestamps using Silero VAD
            speech_timestamps = get_speech_timestamps(
                audio_tensor, 
                self.vad_model,
                sampling_rate=16000,
                threshold=0.5,
                min_speech_duration_ms=250,
                min_silence_duration_ms=100
            )
            
            # Convert timestamps to VADSegment objects
            vad_segments = []
            for timestamp in speech_timestamps:
                start_time = timestamp['start'] / 16000.0  # Convert samples to seconds
                end_time = timestamp['end'] / 16000.0
                
                vad_segments.append(VADSegment(
                    start_time=start_time,
                    end_time=end_time,
                    confidence=0.9,  # Silero VAD doesn't provide confidence, use default
                    is_speech=True
                ))
            
            # If no speech detected, return empty list
            if not vad_segments:
                logger.info("No speech activity detected")
                return []
            
            logger.info(f"Detected {len(vad_segments)} speech segments")
            return vad_segments
            
        except Exception as e:
            logger.error(f"VAD detection failed: {e}")
            # Return a fallback segment covering the entire audio
            return [VADSegment(
                start_time=0.0,
                end_time=self._estimate_audio_duration(audio_data),
                confidence=0.5,
                is_speech=True
            )]
    
    def _bytes_to_audio_array(self, audio_data: bytes) -> np.ndarray:
        """Convert audio bytes to numpy array - handles WebM, WAV, and raw PCM"""
        try:
            # First, try using soundfile (handles WAV, FLAC, OGG)
            audio_io = io.BytesIO(audio_data)
            audio_array, sample_rate = sf.read(audio_io)
            
            # Resample if needed
            if sample_rate != settings.SAMPLE_RATE:
                audio_array = librosa.resample(
                    audio_array, 
                    orig_sr=sample_rate, 
                    target_sr=settings.SAMPLE_RATE
                )
            
            # Convert to mono if stereo
            if len(audio_array.shape) > 1:
                audio_array = np.mean(audio_array, axis=1)
            
            return audio_array.astype(np.float32)
            
        except Exception as first_error:
            # If soundfile fails, try using librosa (handles more formats including WebM)
            try:
                # Save to temp file for librosa
                with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp_file:
                    temp_file.write(audio_data)
                    temp_file_path = temp_file.name
                
                try:
                    # Load with librosa (handles WebM via ffmpeg)
                    audio_array, sample_rate = librosa.load(
                        temp_file_path, 
                        sr=settings.SAMPLE_RATE,
                        mono=True
                    )
                    return audio_array.astype(np.float32)
                finally:
                    os.unlink(temp_file_path)
                    
            except Exception as second_error:
                # Last resort: try to interpret as raw PCM audio
                try:
                    # Assume 16-bit PCM audio
                    audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
                    # Normalize to [-1, 1] range
                    audio_array = audio_array / 32768.0
                    return audio_array
                except Exception as e:
                    logger.error(f"Failed to convert audio bytes to array: {e}")
                    logger.error(f"First error (soundfile): {first_error}")
                    logger.error(f"Second error (librosa): {second_error}")
                    raise
    
    def _estimate_audio_duration(self, audio_data: bytes) -> float:
        """Estimate audio duration from byte length"""
        try:
            # Rough estimation: assume 16-bit mono audio at sample rate
            bytes_per_sample = 2  # 16-bit = 2 bytes
            estimated_samples = len(audio_data) / bytes_per_sample
            duration = estimated_samples / settings.SAMPLE_RATE
            return duration
        except Exception:
            return 1.0  # Default fallback duration
    
    async def process_audio_chunk(self, audio_chunk: bytes, chunk_index: int = 0) -> Dict[str, Any]:
        """Process a single audio chunk for real-time analysis"""
        try:
            start_time = time.time()
            
            # Detect voice activity in the chunk
            vad_segments = await self.detect_voice_activity(audio_chunk)
            
            # Only process if speech is detected
            has_speech = len(vad_segments) > 0
            
            result = {
                "chunk_index": chunk_index,
                "has_speech": has_speech,
                "vad_segments": [segment.model_dump() for segment in vad_segments],
                "processing_time": time.time() - start_time,
                "chunk_duration": self._estimate_audio_duration(audio_chunk)
            }
            
            # If speech detected, do quick analysis
            if has_speech and len(audio_chunk) > 1024:  # Only if chunk is large enough
                try:
                    # Quick transcription for immediate feedback
                    transcription = await self.transcribe_audio(audio_chunk)
                    result["transcript"] = transcription["text"]
                    result["confidence"] = transcription["confidence"]
                    
                    # Calculate basic metrics for immediate feedback
                    basic_metrics = await self.calculate_basic_metrics(
                        audio_chunk, 
                        transcription["text"], 
                        vad_segments
                    )
                    result["basic_metrics"] = basic_metrics
                    
                except Exception as e:
                    logger.warning(f"Quick analysis failed for chunk {chunk_index}: {e}")
                    result["transcript"] = ""
                    result["confidence"] = 0.0
                    result["basic_metrics"] = {}
            
            return result
            
        except Exception as e:
            logger.error(f"Audio chunk processing failed: {e}")
            return {
                "chunk_index": chunk_index,
                "has_speech": False,
                "vad_segments": [],
                "processing_time": 0.0,
                "chunk_duration": 0.0,
                "error": str(e)
            }
    
    def create_audio_buffer(self, buffer_size_seconds: float = 2.0) -> 'AudioBuffer':
        """Create an audio buffer for streaming processing"""
        return AudioBuffer(buffer_size_seconds, settings.SAMPLE_RATE)
    
    async def create_streaming_pipeline(self, participant_id: str, room_id: str) -> 'StreamingTranscriptionPipeline':
        """Create a streaming transcription pipeline for real-time processing"""
        return StreamingTranscriptionPipeline(self, participant_id, room_id)
    
    async def analyze_prosody(self, audio_data: bytes, transcript: str = "") -> ProsodyMetrics:
        """Analyze prosodic features using advanced Parselmouth analysis"""
        return await self.advanced_analysis_service.analyze_prosody_detailed(
            audio_data, 
            transcript
        )
    
    def _count_filler_words(self, transcript: str) -> int:
        """Count filler words in transcript"""
        filler_words = ["um", "uh", "er", "ah", "like", "you know", "so", "well"]
        words = transcript.lower().split()
        return sum(1 for word in words if word in filler_words)
    
    async def calculate_basic_metrics(self, audio_data: bytes, transcript: str = "", vad_segments: List[VADSegment] = None) -> Dict[str, Any]:
        """Calculate basic speech metrics for immediate feedback"""
        try:
            start_time = time.time()
            
            # Convert audio to numpy array
            audio_array = self._bytes_to_audio_array(audio_data)
            duration = len(audio_array) / settings.SAMPLE_RATE
            
            # Calculate basic metrics
            pitch_metrics = BasicSpeechMetrics.calculate_basic_pitch(audio_array, settings.SAMPLE_RATE)
            volume_metrics = BasicSpeechMetrics.calculate_volume_metrics(audio_array)
            speaking_rate_metrics = BasicSpeechMetrics.calculate_speaking_rate(transcript, duration)
            
            # Use provided VAD segments or detect them
            if vad_segments is None:
                vad_segments = await self.detect_voice_activity(audio_data)
            
            pause_metrics = BasicSpeechMetrics.calculate_pause_metrics(vad_segments, duration)
            
            # Combine all metrics
            all_metrics = {
                "duration": duration,
                "pitch": pitch_metrics,
                "volume": volume_metrics,
                "speaking_rate": speaking_rate_metrics,
                "pause_metrics": pause_metrics,
                "processing_time": time.time() - start_time
            }
            
            # Generate immediate feedback
            feedback = BasicSpeechMetrics.generate_immediate_feedback(all_metrics)
            all_metrics["immediate_feedback"] = feedback
            
            return all_metrics
            
        except Exception as e:
            logger.error(f"Error calculating basic metrics: {e}")
            return {
                "duration": 0.0,
                "pitch": {"average_pitch": 150.0, "pitch_confidence": 0.0},
                "volume": {"average_volume": 0.0, "peak_volume": 0.0, "average_volume_db": -60.0, "peak_volume_db": -60.0, "dynamic_range": 0.0},
                "speaking_rate": {"word_count": 0, "words_per_minute": 0.0, "syllable_count": 0, "syllables_per_minute": 0.0},
                "pause_metrics": {"pause_count": 0, "total_pause_time": 0.0, "average_pause_length": 0.0, "speech_ratio": 0.0},
                "immediate_feedback": {"overall_score": 0.0, "feedback_items": [], "recommendations": []},
                "processing_time": 0.0,
                "error": str(e)
            }
    
    async def analyze_speech(
        self, 
        audio_data: bytes, 
        transcript: Optional[str] = None,
        include_body_language: bool = False,
        video_data: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """Perform comprehensive speech analysis"""
        try:
            # Transcribe if no transcript provided
            if not transcript:
                transcription_result = await self.transcribe_audio(audio_data)
                transcript = transcription_result["text"]
            
            # Detect voice activity
            vad_segments = await self.detect_voice_activity(audio_data)
            
            # Analyze prosody
            prosody_metrics = await self.analyze_prosody(audio_data, transcript)
            
            result = {
                "transcript": transcript,
                "vad_segments": [segment.model_dump() for segment in vad_segments],
                "prosody_metrics": prosody_metrics.model_dump()
            }
            
            # Add body language analysis if requested and video data provided
            if include_body_language and video_data:
                body_language = await self.advanced_analysis_service.analyze_body_language(
                    video_data,
                    frame_rate=30
                )
                result["body_language_analysis"] = body_language.model_dump()
            
            return result
            
        except Exception as e:
            logger.error(f"Speech analysis failed: {e}")
            raise


class StreamingTranscriptionPipeline:
    """Pipeline for real-time streaming transcription"""
    
    def __init__(self, speech_service: SpeechService, participant_id: str, room_id: str):
        self.speech_service = speech_service
        self.participant_id = participant_id
        self.room_id = room_id
        self.audio_buffer = speech_service.create_audio_buffer(buffer_size_seconds=1.5)
        self.is_active = False
        self.last_transcript_time = 0
        self.min_transcript_interval = 0.5  # Minimum seconds between transcripts
    
    async def process_audio_chunk(self, audio_data: bytes) -> Optional[Dict[str, Any]]:
        """Process an audio chunk and return transcription if ready"""
        try:
            current_time = time.time()
            
            # Add audio to buffer
            complete_chunks = self.audio_buffer.add_audio_data(audio_data)
            
            # Process complete chunks
            for chunk in complete_chunks:
                # Convert numpy array back to bytes for processing
                chunk_bytes = self._numpy_to_bytes(chunk)
                
                # Check if enough time has passed since last transcript
                if current_time - self.last_transcript_time < self.min_transcript_interval:
                    continue
                
                # Transcribe the chunk
                result = await self.speech_service.transcribe_audio_streaming(
                    chunk_bytes, 
                    self.participant_id, 
                    self.room_id
                )
                
                if result.get("has_speech") and result.get("text"):
                    self.last_transcript_time = current_time
                    return result
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing audio chunk in streaming pipeline: {e}")
            return None
    
    async def finalize(self) -> Optional[Dict[str, Any]]:
        """Process any remaining audio in the buffer"""
        try:
            remaining_audio = self.audio_buffer.get_remaining_audio()
            if remaining_audio is not None and len(remaining_audio) > 0:
                chunk_bytes = self._numpy_to_bytes(remaining_audio)
                return await self.speech_service.transcribe_audio_streaming(
                    chunk_bytes, 
                    self.participant_id, 
                    self.room_id
                )
            return None
        except Exception as e:
            logger.error(f"Error finalizing streaming pipeline: {e}")
            return None
    
    def _numpy_to_bytes(self, audio_array: np.ndarray) -> bytes:
        """Convert numpy array to audio bytes"""
        try:
            # Convert float32 to int16
            audio_int16 = (audio_array * 32767).astype(np.int16)
            return audio_int16.tobytes()
        except Exception as e:
            logger.error(f"Error converting numpy array to bytes: {e}")
            return b""


class BasicSpeechMetrics:
    """Calculate basic speech metrics for immediate feedback"""
    
    @staticmethod
    def calculate_basic_pitch(audio_array: np.ndarray, sample_rate: int = 16000) -> Dict[str, float]:
        """Calculate basic pitch metrics using simple autocorrelation"""
        try:
            # Remove DC component
            audio_array = audio_array - np.mean(audio_array)
            
            # Calculate autocorrelation
            autocorr = np.correlate(audio_array, audio_array, mode='full')
            autocorr = autocorr[len(autocorr)//2:]
            
            # Find fundamental frequency
            min_period = int(sample_rate / 500)  # 500 Hz max
            max_period = int(sample_rate / 50)   # 50 Hz min
            
            if len(autocorr) > max_period:
                # Find peak in valid range
                valid_autocorr = autocorr[min_period:max_period]
                if len(valid_autocorr) > 0:
                    peak_idx = np.argmax(valid_autocorr) + min_period
                    fundamental_freq = sample_rate / peak_idx
                else:
                    fundamental_freq = 150.0  # Default
            else:
                fundamental_freq = 150.0  # Default
            
            return {
                "average_pitch": float(fundamental_freq),
                "pitch_confidence": float(np.max(autocorr) / np.sum(np.abs(autocorr))) if np.sum(np.abs(autocorr)) > 0 else 0.0
            }
            
        except Exception as e:
            logger.error(f"Error calculating basic pitch: {e}")
            return {"average_pitch": 150.0, "pitch_confidence": 0.0}
    
    @staticmethod
    def calculate_volume_metrics(audio_array: np.ndarray) -> Dict[str, float]:
        """Calculate volume/intensity metrics"""
        try:
            # RMS (Root Mean Square) for overall volume
            rms = np.sqrt(np.mean(audio_array ** 2))
            
            # Peak amplitude
            peak = np.max(np.abs(audio_array))
            
            # Convert to dB scale (approximate)
            rms_db = 20 * np.log10(rms + 1e-10)  # Add small value to avoid log(0)
            peak_db = 20 * np.log10(peak + 1e-10)
            
            # Dynamic range
            dynamic_range = peak_db - rms_db
            
            return {
                "average_volume": float(rms),
                "peak_volume": float(peak),
                "average_volume_db": float(rms_db),
                "peak_volume_db": float(peak_db),
                "dynamic_range": float(dynamic_range)
            }
            
        except Exception as e:
            logger.error(f"Error calculating volume metrics: {e}")
            return {
                "average_volume": 0.0,
                "peak_volume": 0.0,
                "average_volume_db": -60.0,
                "peak_volume_db": -60.0,
                "dynamic_range": 0.0
            }
    
    @staticmethod
    def calculate_speaking_rate(transcript: str, duration_seconds: float) -> Dict[str, float]:
        """Calculate speaking rate metrics"""
        try:
            if not transcript or duration_seconds <= 0:
                return {
                    "word_count": 0,
                    "words_per_minute": 0.0,
                    "syllable_count": 0,
                    "syllables_per_minute": 0.0
                }
            
            # Count words (simple split by whitespace)
            words = transcript.strip().split()
            word_count = len(words)
            
            # Estimate syllable count (simple heuristic)
            syllable_count = BasicSpeechMetrics._estimate_syllables(transcript)
            
            # Calculate rates
            words_per_minute = (word_count / duration_seconds) * 60
            syllables_per_minute = (syllable_count / duration_seconds) * 60
            
            return {
                "word_count": word_count,
                "words_per_minute": float(words_per_minute),
                "syllable_count": syllable_count,
                "syllables_per_minute": float(syllables_per_minute)
            }
            
        except Exception as e:
            logger.error(f"Error calculating speaking rate: {e}")
            return {
                "word_count": 0,
                "words_per_minute": 0.0,
                "syllable_count": 0,
                "syllables_per_minute": 0.0
            }
    
    @staticmethod
    def _estimate_syllables(text: str) -> int:
        """Estimate syllable count using simple heuristics"""
        try:
            text = text.lower().strip()
            if not text:
                return 0
            
            # Remove punctuation and split into words
            import re
            words = re.findall(r'\b[a-z]+\b', text)
            
            total_syllables = 0
            for word in words:
                # Count vowel groups
                vowels = 'aeiouy'
                syllable_count = 0
                prev_was_vowel = False
                
                for char in word:
                    is_vowel = char in vowels
                    if is_vowel and not prev_was_vowel:
                        syllable_count += 1
                    prev_was_vowel = is_vowel
                
                # Handle silent 'e'
                if word.endswith('e') and syllable_count > 1:
                    syllable_count -= 1
                
                # Ensure at least 1 syllable per word
                syllable_count = max(1, syllable_count)
                total_syllables += syllable_count
            
            return total_syllables
            
        except Exception as e:
            logger.error(f"Error estimating syllables: {e}")
            return len(text.split())  # Fallback to word count
    
    @staticmethod
    def calculate_pause_metrics(vad_segments: List[VADSegment], total_duration: float) -> Dict[str, float]:
        """Calculate pause and silence metrics"""
        try:
            if not vad_segments or total_duration <= 0:
                return {
                    "pause_count": 0,
                    "total_pause_time": 0.0,
                    "average_pause_length": 0.0,
                    "speech_ratio": 0.0
                }
            
            # Calculate pauses between speech segments
            pauses = []
            total_speech_time = 0.0
            
            # Sort segments by start time
            sorted_segments = sorted(vad_segments, key=lambda x: x.start_time)
            
            for i, segment in enumerate(sorted_segments):
                total_speech_time += segment.end_time - segment.start_time
                
                # Check for pause after this segment
                if i < len(sorted_segments) - 1:
                    next_segment = sorted_segments[i + 1]
                    pause_duration = next_segment.start_time - segment.end_time
                    if pause_duration > 0.1:  # Only count pauses > 100ms
                        pauses.append(pause_duration)
            
            # Calculate metrics
            pause_count = len(pauses)
            total_pause_time = sum(pauses)
            average_pause_length = total_pause_time / pause_count if pause_count > 0 else 0.0
            speech_ratio = total_speech_time / total_duration if total_duration > 0 else 0.0
            
            return {
                "pause_count": pause_count,
                "total_pause_time": float(total_pause_time),
                "average_pause_length": float(average_pause_length),
                "speech_ratio": float(speech_ratio)
            }
            
        except Exception as e:
            logger.error(f"Error calculating pause metrics: {e}")
            return {
                "pause_count": 0,
                "total_pause_time": 0.0,
                "average_pause_length": 0.0,
                "speech_ratio": 0.0
            }
    
    @staticmethod
    def generate_immediate_feedback(metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Generate immediate feedback based on basic metrics"""
        try:
            feedback = {
                "overall_score": 0.0,
                "feedback_items": [],
                "recommendations": []
            }
            
            # Analyze speaking rate
            wpm = metrics.get("speaking_rate", {}).get("words_per_minute", 0)
            if wpm > 0:
                if wpm < 120:
                    feedback["feedback_items"].append({
                        "category": "pace",
                        "message": "Speaking pace is quite slow",
                        "score": 0.6,
                        "suggestion": "Try to speak a bit faster for better engagement"
                    })
                elif wpm > 200:
                    feedback["feedback_items"].append({
                        "category": "pace",
                        "message": "Speaking pace is very fast",
                        "score": 0.7,
                        "suggestion": "Slow down slightly for better clarity"
                    })
                else:
                    feedback["feedback_items"].append({
                        "category": "pace",
                        "message": "Good speaking pace",
                        "score": 0.9,
                        "suggestion": "Maintain this comfortable pace"
                    })
            
            # Analyze volume
            volume_db = metrics.get("volume", {}).get("average_volume_db", -60)
            if volume_db > -20:
                feedback["feedback_items"].append({
                    "category": "volume",
                    "message": "Good volume level",
                    "score": 0.9,
                    "suggestion": "Volume is clear and audible"
                })
            elif volume_db < -40:
                feedback["feedback_items"].append({
                    "category": "volume",
                    "message": "Volume is quite low",
                    "score": 0.6,
                    "suggestion": "Speak louder for better clarity"
                })
            else:
                feedback["feedback_items"].append({
                    "category": "volume",
                    "message": "Volume could be improved",
                    "score": 0.7,
                    "suggestion": "Increase volume slightly"
                })
            
            # Analyze pauses
            speech_ratio = metrics.get("pause_metrics", {}).get("speech_ratio", 0)
            if speech_ratio > 0.8:
                feedback["feedback_items"].append({
                    "category": "fluency",
                    "message": "Very fluent speech",
                    "score": 0.9,
                    "suggestion": "Excellent flow with minimal pauses"
                })
            elif speech_ratio < 0.6:
                feedback["feedback_items"].append({
                    "category": "fluency",
                    "message": "Many pauses detected",
                    "score": 0.6,
                    "suggestion": "Try to reduce hesitations and pauses"
                })
            else:
                feedback["feedback_items"].append({
                    "category": "fluency",
                    "message": "Good speech fluency",
                    "score": 0.8,
                    "suggestion": "Natural pace with appropriate pauses"
                })
            
            # Calculate overall score
            if feedback["feedback_items"]:
                feedback["overall_score"] = sum(item["score"] for item in feedback["feedback_items"]) / len(feedback["feedback_items"])
            
            return feedback
            
        except Exception as e:
            logger.error(f"Error generating immediate feedback: {e}")
            return {
                "overall_score": 0.5,
                "feedback_items": [],
                "recommendations": ["Unable to analyze speech at this time"]
            }


class AudioBuffer:
    """Buffer for managing streaming audio data"""
    
    def __init__(self, buffer_size_seconds: float, sample_rate: int):
        self.buffer_size_seconds = buffer_size_seconds
        self.sample_rate = sample_rate
        self.max_samples = int(buffer_size_seconds * sample_rate)
        self.buffer = np.array([], dtype=np.float32)
        self.total_samples_processed = 0
    
    def add_audio_data(self, audio_data: bytes) -> List[np.ndarray]:
        """Add audio data to buffer and return complete chunks"""
        try:
            # Convert bytes to audio array
            new_audio = self._bytes_to_audio_array(audio_data)
            
            # Add to buffer
            self.buffer = np.concatenate([self.buffer, new_audio])
            
            # Extract complete chunks
            chunks = []
            while len(self.buffer) >= self.max_samples:
                chunk = self.buffer[:self.max_samples]
                chunks.append(chunk)
                self.buffer = self.buffer[self.max_samples:]
                self.total_samples_processed += self.max_samples
            
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to add audio data to buffer: {e}")
            return []
    
    def get_remaining_audio(self) -> Optional[np.ndarray]:
        """Get any remaining audio in the buffer"""
        if len(self.buffer) > 0:
            remaining = self.buffer.copy()
            self.buffer = np.array([], dtype=np.float32)
            return remaining
        return None
    
    def _bytes_to_audio_array(self, audio_data: bytes) -> np.ndarray:
        """Convert audio bytes to numpy array"""
        try:
            # Try to read as WAV file first
            audio_io = io.BytesIO(audio_data)
            audio_array, sample_rate = sf.read(audio_io)
            
            # Resample if needed
            if sample_rate != self.sample_rate:
                audio_array = librosa.resample(
                    audio_array, 
                    orig_sr=sample_rate, 
                    target_sr=self.sample_rate
                )
            
            # Convert to mono if stereo
            if len(audio_array.shape) > 1:
                audio_array = np.mean(audio_array, axis=1)
            
            return audio_array.astype(np.float32)
            
        except Exception:
            # If that fails, try to interpret as raw audio data
            try:
                # Assume 16-bit PCM audio
                audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
                # Normalize to [-1, 1] range
                audio_array = audio_array / 32768.0
                return audio_array
            except Exception as e:
                logger.error(f"Failed to convert audio bytes to array: {e}")
                raise


# End of AudioBuffer class