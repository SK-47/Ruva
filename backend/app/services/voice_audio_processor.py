"""
Audio processing service for ElevenLabs Voice Agent integration.
Handles real-time audio streaming, quality optimization, noise reduction, and format conversion.
"""

import asyncio
import logging
import io
from typing import Optional, AsyncGenerator
import numpy as np

logger = logging.getLogger(__name__)

# Try to import audio processing libraries
try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    logger.warning("soundfile not available. Some audio processing features will be limited.")
    SOUNDFILE_AVAILABLE = False

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    logger.warning("librosa not available. Advanced audio processing will be limited.")
    LIBROSA_AVAILABLE = False


class VoiceAudioProcessor:
    """Audio processor for voice agent streaming"""
    
    # Audio format constants
    SAMPLE_RATE = 16000  # 16kHz for voice
    CHANNELS = 1  # Mono
    CHUNK_SIZE = 4096  # Bytes per chunk
    
    def __init__(self):
        self.sample_rate = self.SAMPLE_RATE
        self.channels = self.CHANNELS
        self.chunk_size = self.CHUNK_SIZE
    
    async def process_input_audio(
        self,
        audio_data: bytes,
        source_format: str = "wav",
        apply_noise_reduction: bool = True,
        normalize: bool = True
    ) -> bytes:
        """
        Process input audio for optimal voice agent consumption
        
        Args:
            audio_data: Raw audio bytes
            source_format: Source audio format (wav, mp3, etc.)
            apply_noise_reduction: Whether to apply noise reduction
            normalize: Whether to normalize audio levels
        
        Returns:
            Processed audio bytes in PCM format
        """
        try:
            if not SOUNDFILE_AVAILABLE:
                logger.warning("Audio processing libraries not available, returning raw audio")
                return audio_data
            
            # Read audio data
            audio_io = io.BytesIO(audio_data)
            audio_array, sr = sf.read(audio_io)
            
            # Convert to mono if stereo
            if len(audio_array.shape) > 1:
                audio_array = np.mean(audio_array, axis=1)
            
            # Resample to target sample rate if needed
            if sr != self.sample_rate and LIBROSA_AVAILABLE:
                audio_array = librosa.resample(
                    audio_array,
                    orig_sr=sr,
                    target_sr=self.sample_rate
                )
            
            # Apply noise reduction if requested and available
            if apply_noise_reduction and LIBROSA_AVAILABLE:
                audio_array = self._apply_noise_reduction(audio_array)
            
            # Normalize audio levels if requested
            if normalize:
                audio_array = self._normalize_audio(audio_array)
            
            # Convert back to bytes
            output_io = io.BytesIO()
            sf.write(output_io, audio_array, self.sample_rate, format='WAV', subtype='PCM_16')
            output_io.seek(0)
            
            return output_io.read()
        
        except Exception as e:
            logger.error(f"Error processing input audio: {e}")
            # Return original audio if processing fails
            return audio_data
    
    async def process_output_audio(
        self,
        audio_data: bytes,
        target_format: str = "mp3",
        enhance_quality: bool = True
    ) -> bytes:
        """
        Process output audio from voice agent for optimal playback
        
        Args:
            audio_data: Raw audio bytes from voice agent
            target_format: Target audio format for playback
            enhance_quality: Whether to apply quality enhancement
        
        Returns:
            Processed audio bytes in target format
        """
        try:
            if not SOUNDFILE_AVAILABLE:
                logger.warning("Audio processing libraries not available, returning raw audio")
                return audio_data
            
            # Read audio data
            audio_io = io.BytesIO(audio_data)
            audio_array, sr = sf.read(audio_io)
            
            # Apply quality enhancement if requested
            if enhance_quality and LIBROSA_AVAILABLE:
                audio_array = self._enhance_audio_quality(audio_array)
            
            # Convert to target format
            output_io = io.BytesIO()
            
            if target_format.lower() == "mp3":
                # For MP3, we'll use WAV as intermediate (MP3 encoding requires additional libraries)
                sf.write(output_io, audio_array, sr, format='WAV', subtype='PCM_16')
            else:
                sf.write(output_io, audio_array, sr, format=target_format.upper())
            
            output_io.seek(0)
            return output_io.read()
        
        except Exception as e:
            logger.error(f"Error processing output audio: {e}")
            return audio_data
    
    async def stream_audio_chunks(
        self,
        audio_data: bytes,
        chunk_size: Optional[int] = None
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream audio data in chunks for real-time processing
        
        Args:
            audio_data: Complete audio data
            chunk_size: Size of each chunk in bytes
        
        Yields:
            Audio chunks
        """
        chunk_size = chunk_size or self.chunk_size
        
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            yield chunk
            # Small delay to simulate real-time streaming
            await asyncio.sleep(0.01)
    
    def _apply_noise_reduction(self, audio_array: np.ndarray) -> np.ndarray:
        """Apply basic noise reduction to audio"""
        try:
            if not LIBROSA_AVAILABLE:
                return audio_array
            
            # Simple spectral gating for noise reduction
            # This is a basic implementation - production systems would use more sophisticated methods
            
            # Compute short-time Fourier transform
            stft = librosa.stft(audio_array)
            magnitude = np.abs(stft)
            
            # Estimate noise floor (bottom 10% of magnitudes)
            noise_floor = np.percentile(magnitude, 10, axis=1, keepdims=True)
            
            # Apply spectral gate
            mask = magnitude > (noise_floor * 2)  # Threshold at 2x noise floor
            stft_filtered = stft * mask
            
            # Inverse STFT
            audio_filtered = librosa.istft(stft_filtered)
            
            return audio_filtered
        
        except Exception as e:
            logger.error(f"Error in noise reduction: {e}")
            return audio_array
    
    def _normalize_audio(self, audio_array: np.ndarray, target_level: float = 0.9) -> np.ndarray:
        """Normalize audio to target level"""
        try:
            # Find peak amplitude
            peak = np.abs(audio_array).max()
            
            if peak > 0:
                # Scale to target level
                audio_array = audio_array * (target_level / peak)
            
            return audio_array
        
        except Exception as e:
            logger.error(f"Error normalizing audio: {e}")
            return audio_array
    
    def _enhance_audio_quality(self, audio_array: np.ndarray) -> np.ndarray:
        """Apply quality enhancement to audio"""
        try:
            if not LIBROSA_AVAILABLE:
                return audio_array
            
            # Apply subtle high-pass filter to remove low-frequency rumble
            audio_filtered = librosa.effects.preemphasis(audio_array, coef=0.97)
            
            # Apply dynamic range compression (simple version)
            # This helps make quiet parts more audible without clipping loud parts
            threshold = 0.5
            ratio = 3.0
            
            mask = np.abs(audio_filtered) > threshold
            compressed = audio_filtered.copy()
            compressed[mask] = np.sign(audio_filtered[mask]) * (
                threshold + (np.abs(audio_filtered[mask]) - threshold) / ratio
            )
            
            return compressed
        
        except Exception as e:
            logger.error(f"Error enhancing audio quality: {e}")
            return audio_array
    
    def convert_format(
        self,
        audio_data: bytes,
        source_format: str,
        target_format: str
    ) -> bytes:
        """
        Convert audio from one format to another
        
        Args:
            audio_data: Audio data in source format
            source_format: Source format (wav, mp3, etc.)
            target_format: Target format
        
        Returns:
            Audio data in target format
        """
        try:
            if not SOUNDFILE_AVAILABLE:
                logger.warning("Audio format conversion not available")
                return audio_data
            
            # Read audio
            audio_io = io.BytesIO(audio_data)
            audio_array, sr = sf.read(audio_io)
            
            # Write in target format
            output_io = io.BytesIO()
            sf.write(output_io, audio_array, sr, format=target_format.upper())
            output_io.seek(0)
            
            return output_io.read()
        
        except Exception as e:
            logger.error(f"Error converting audio format: {e}")
            return audio_data
    
    def get_audio_info(self, audio_data: bytes) -> dict:
        """Get information about audio data"""
        try:
            if not SOUNDFILE_AVAILABLE:
                return {
                    "error": "Audio analysis not available",
                    "size_bytes": len(audio_data)
                }
            
            audio_io = io.BytesIO(audio_data)
            audio_array, sr = sf.read(audio_io)
            
            duration = len(audio_array) / sr
            channels = 1 if len(audio_array.shape) == 1 else audio_array.shape[1]
            
            return {
                "sample_rate": sr,
                "channels": channels,
                "duration_seconds": duration,
                "samples": len(audio_array),
                "size_bytes": len(audio_data),
                "format": "PCM"
            }
        
        except Exception as e:
            logger.error(f"Error getting audio info: {e}")
            return {
                "error": str(e),
                "size_bytes": len(audio_data)
            }
