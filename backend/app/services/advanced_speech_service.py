"""
Advanced Speech Analysis Service - Tier 2 (Detailed Analysis)

This service provides comprehensive speech analysis using:
- Parselmouth for advanced prosodic analysis
- Background processing queue for detailed analysis
- Comprehensive prosody metrics calculation
"""

import parselmouth
from parselmouth.praat import call
import numpy as np
from typing import Dict, List, Any, Optional
import tempfile
import os
import logging
import io
import soundfile as sf
import librosa
from asyncio import Queue
import asyncio

from app.models.speech import ProsodyMetrics, VADSegment, BodyLanguageAnalysis
from app.core.config import settings

logger = logging.getLogger(__name__)

# Body language service is optional - will use Gemini API instead
try:
    from app.services.body_language_service import BodyLanguageAnalysisService
    BODY_LANGUAGE_AVAILABLE = True
except ImportError:
    BODY_LANGUAGE_AVAILABLE = False
    logger.warning("Body language service not available - OpenCV/MediaPipe not installed")


class AdvancedSpeechAnalysisService:
    """Service for advanced speech analysis using Parselmouth and other tools"""
    
    def __init__(self):
        self.analysis_queue = Queue()
        self.is_processing = False
        self.body_language_service = BodyLanguageAnalysisService() if BODY_LANGUAGE_AVAILABLE else None
        logger.info("Advanced Speech Analysis Service initialized")
    
    async def analyze_prosody_detailed(
        self, 
        audio_data: bytes, 
        transcript: str = "",
        vad_segments: Optional[List[VADSegment]] = None
    ) -> ProsodyMetrics:
        """
        Perform detailed prosodic analysis using Parselmouth
        
        Args:
            audio_data: Raw audio bytes
            transcript: Transcribed text
            vad_segments: Voice activity detection segments
            
        Returns:
            ProsodyMetrics with comprehensive prosodic features
        """
        try:
            # Save audio to temporary file for Parselmouth
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                # Load audio with Parselmouth
                sound = parselmouth.Sound(temp_file_path)
                
                # Calculate duration
                duration = sound.duration
                
                # Calculate words per minute
                word_count = len(transcript.split()) if transcript else 0
                words_per_minute = (word_count / duration * 60) if duration > 0 else 0
                
                # Extract pitch features
                pitch_features = self._extract_pitch_features(sound)
                
                # Extract intensity features
                intensity_features = self._extract_intensity_features(sound)
                
                # Extract voice quality features
                voice_quality = self._extract_voice_quality_features(sound)
                
                # Extract formants
                formants = self._extract_formants(sound)
                
                # Detect filler words and pauses
                filler_word_count = self._count_filler_words(transcript)
                pause_metrics = self._analyze_pauses(vad_segments, duration) if vad_segments else {
                    "pause_count": 0,
                    "average_pause_length": 0.0
                }
                
                # Create comprehensive prosody metrics
                prosody_metrics = ProsodyMetrics(
                    duration=duration,
                    words_per_minute=words_per_minute,
                    average_pitch=pitch_features["mean_pitch"],
                    pitch_range=pitch_features["pitch_range"],
                    average_intensity=intensity_features["mean_intensity"],
                    intensity_range=intensity_features["intensity_range"],
                    jitter=voice_quality["jitter"],
                    shimmer=voice_quality["shimmer"],
                    harmonic_to_noise_ratio=voice_quality["hnr"],
                    formants=formants,
                    sentiment_score=0.0,  # Placeholder for sentiment analysis
                    sentiment_label="neutral",  # Placeholder
                    filler_word_count=filler_word_count,
                    pause_count=pause_metrics["pause_count"],
                    average_pause_length=pause_metrics["average_pause_length"]
                )
                
                logger.info(f"Detailed prosody analysis completed in {duration:.2f}s")
                return prosody_metrics
                
            finally:
                # Clean up temporary file
                os.unlink(temp_file_path)
                
        except Exception as e:
            logger.error(f"Detailed prosody analysis failed: {e}")
            # Return default metrics on failure
            return self._get_default_prosody_metrics(transcript)
    
    def _extract_pitch_features(self, sound: parselmouth.Sound) -> Dict[str, float]:
        """Extract pitch features using Parselmouth"""
        try:
            # Extract pitch using autocorrelation method
            pitch = call(sound, "To Pitch", 0.0, 75, 600)  # 75-600 Hz range for human speech
            
            # Get pitch values
            pitch_values = pitch.selected_array['frequency']
            pitch_values = pitch_values[pitch_values > 0]  # Remove unvoiced frames
            
            if len(pitch_values) > 0:
                mean_pitch = float(np.mean(pitch_values))
                std_pitch = float(np.std(pitch_values))
                min_pitch = float(np.min(pitch_values))
                max_pitch = float(np.max(pitch_values))
                pitch_range = max_pitch - min_pitch
            else:
                mean_pitch = 150.0
                std_pitch = 0.0
                min_pitch = 150.0
                max_pitch = 150.0
                pitch_range = 0.0
            
            return {
                "mean_pitch": mean_pitch,
                "std_pitch": std_pitch,
                "min_pitch": min_pitch,
                "max_pitch": max_pitch,
                "pitch_range": pitch_range
            }
            
        except Exception as e:
            logger.error(f"Pitch extraction failed: {e}")
            return {
                "mean_pitch": 150.0,
                "std_pitch": 0.0,
                "min_pitch": 150.0,
                "max_pitch": 150.0,
                "pitch_range": 0.0
            }
    
    def _extract_intensity_features(self, sound: parselmouth.Sound) -> Dict[str, float]:
        """Extract intensity (loudness) features"""
        try:
            # Extract intensity
            intensity = call(sound, "To Intensity", 75, 0.0, "yes")
            
            # Get intensity values
            intensity_values = intensity.values[0]
            intensity_values = intensity_values[intensity_values > 0]
            
            if len(intensity_values) > 0:
                mean_intensity = float(np.mean(intensity_values))
                std_intensity = float(np.std(intensity_values))
                min_intensity = float(np.min(intensity_values))
                max_intensity = float(np.max(intensity_values))
                intensity_range = max_intensity - min_intensity
            else:
                mean_intensity = 65.0
                std_intensity = 0.0
                min_intensity = 65.0
                max_intensity = 65.0
                intensity_range = 0.0
            
            return {
                "mean_intensity": mean_intensity,
                "std_intensity": std_intensity,
                "min_intensity": min_intensity,
                "max_intensity": max_intensity,
                "intensity_range": intensity_range
            }
            
        except Exception as e:
            logger.error(f"Intensity extraction failed: {e}")
            return {
                "mean_intensity": 65.0,
                "std_intensity": 0.0,
                "min_intensity": 65.0,
                "max_intensity": 65.0,
                "intensity_range": 0.0
            }
    
    def _extract_voice_quality_features(self, sound: parselmouth.Sound) -> Dict[str, float]:
        """Extract voice quality features: jitter, shimmer, HNR"""
        try:
            # Create PointProcess for jitter and shimmer calculation
            point_process = call(sound, "To PointProcess (periodic, cc)", 75, 600)
            
            # Calculate jitter (local)
            jitter = call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
            
            # Calculate shimmer (local)
            shimmer = call([sound, point_process], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
            
            # Calculate Harmonics-to-Noise Ratio
            harmonicity = call(sound, "To Harmonicity (cc)", 0.01, 75, 0.1, 1.0)
            hnr = call(harmonicity, "Get mean", 0, 0)
            
            return {
                "jitter": float(jitter) if not np.isnan(jitter) else 0.01,
                "shimmer": float(shimmer) if not np.isnan(shimmer) else 0.05,
                "hnr": float(hnr) if not np.isnan(hnr) else 15.0
            }
            
        except Exception as e:
            logger.error(f"Voice quality extraction failed: {e}")
            return {
                "jitter": 0.01,
                "shimmer": 0.05,
                "hnr": 15.0
            }
    
    def _extract_formants(self, sound: parselmouth.Sound, num_formants: int = 3) -> List[float]:
        """Extract formant frequencies"""
        try:
            # Create Formant object
            formant = call(sound, "To Formant (burg)", 0.0, 5, 5500, 0.025, 50)
            
            # Extract mean formant values
            formants = []
            for i in range(1, num_formants + 1):
                try:
                    formant_value = call(formant, "Get mean", i, 0, 0, "hertz")
                    if not np.isnan(formant_value):
                        formants.append(float(formant_value))
                    else:
                        # Use typical formant values as fallback
                        formants.append([800.0, 1200.0, 2500.0][i-1])
                except Exception:
                    formants.append([800.0, 1200.0, 2500.0][i-1])
            
            return formants
            
        except Exception as e:
            logger.error(f"Formant extraction failed: {e}")
            return [800.0, 1200.0, 2500.0]
    
    def _count_filler_words(self, transcript: str) -> int:
        """Count filler words in transcript with comprehensive detection"""
        if not transcript:
            return 0
        
        # Comprehensive list of filler words and phrases
        filler_words = [
            "um", "uh", "er", "ah", "like", "you know", "so", "well",
            "actually", "basically", "literally", "kind of", "sort of",
            "i mean", "you see", "right", "okay", "alright", "anyway",
            "hmm", "mhm", "yeah", "yep", "nah", "huh"
        ]
        
        # Multi-word fillers
        multi_word_fillers = [
            "you know", "i mean", "kind of", "sort of", "you see",
            "i guess", "i think", "you know what i mean"
        ]
        
        transcript_lower = transcript.lower()
        count = 0
        
        # Count multi-word fillers first
        for filler in multi_word_fillers:
            count += transcript_lower.count(filler)
        
        # Count single-word fillers
        words = transcript_lower.split()
        for word in words:
            cleaned_word = word.strip(".,!?;:'\"")
            if cleaned_word in filler_words:
                count += 1
        
        return count
    
    def _analyze_pauses(self, vad_segments: List[VADSegment], total_duration: float) -> Dict[str, Any]:
        """Analyze pause patterns from VAD segments"""
        if not vad_segments or total_duration <= 0:
            return {
                "pause_count": 0,
                "average_pause_length": 0.0,
                "total_pause_time": 0.0
            }
        
        # Sort segments by start time
        sorted_segments = sorted(vad_segments, key=lambda x: x.start_time)
        
        pauses = []
        for i in range(len(sorted_segments) - 1):
            pause_duration = sorted_segments[i + 1].start_time - sorted_segments[i].end_time
            if pause_duration > 0.1:  # Only count pauses > 100ms
                pauses.append(pause_duration)
        
        pause_count = len(pauses)
        total_pause_time = sum(pauses)
        average_pause_length = total_pause_time / pause_count if pause_count > 0 else 0.0
        
        return {
            "pause_count": pause_count,
            "average_pause_length": float(average_pause_length),
            "total_pause_time": float(total_pause_time)
        }
    
    def _get_default_prosody_metrics(self, transcript: str = "") -> ProsodyMetrics:
        """Return default prosody metrics when analysis fails"""
        word_count = len(transcript.split()) if transcript else 0
        
        return ProsodyMetrics(
            duration=1.0,
            words_per_minute=word_count * 60,
            average_pitch=150.0,
            pitch_range=50.0,
            average_intensity=65.0,
            intensity_range=20.0,
            jitter=0.01,
            shimmer=0.05,
            harmonic_to_noise_ratio=15.0,
            formants=[800.0, 1200.0, 2500.0],
            sentiment_score=0.0,
            sentiment_label="neutral",
            filler_word_count=self._count_filler_words(transcript),
            pause_count=0,
            average_pause_length=0.0
        )
    
    async def queue_analysis(self, analysis_task: Dict[str, Any]) -> None:
        """Add analysis task to background processing queue"""
        await self.analysis_queue.put(analysis_task)
        logger.info(f"Analysis task queued: {analysis_task.get('task_id', 'unknown')}")
    
    async def process_analysis_queue(self) -> None:
        """Process analysis tasks from the queue in the background"""
        self.is_processing = True
        logger.info("Started background analysis queue processor")
        
        while self.is_processing:
            try:
                # Get task from queue with timeout
                task = await asyncio.wait_for(self.analysis_queue.get(), timeout=1.0)
                
                # Process the task
                task_type = task.get("type", "unknown")
                
                if task_type == "prosody":
                    result = await self.analyze_prosody_detailed(
                        task["audio_data"],
                        task.get("transcript", ""),
                        task.get("vad_segments")
                    )
                    task["callback"](result)
                
                elif task_type == "body_language":
                    result = await self.analyze_body_language(
                        task["video_data"],
                        task.get("frame_rate", 30)
                    )
                    task["callback"](result)
                
                # Mark task as done
                self.analysis_queue.task_done()
                
            except asyncio.TimeoutError:
                # No tasks in queue, continue waiting
                continue
            except Exception as e:
                logger.error(f"Error processing analysis task: {e}")
    
    async def stop_queue_processor(self) -> None:
        """Stop the background queue processor"""
        self.is_processing = False
        logger.info("Stopped background analysis queue processor")
    
    async def analyze_body_language(
        self, 
        video_data: bytes, 
        frame_rate: int = 30
    ) -> BodyLanguageAnalysis:
        """
        Analyze body language from video data using computer vision
        Note: This feature requires OpenCV/MediaPipe. Use Gemini API for body language analysis instead.
        """
        if not BODY_LANGUAGE_AVAILABLE or not self.body_language_service:
            logger.warning("Body language service not available - returning default analysis")
            return BodyLanguageAnalysis(
                posture={
                    "confidence": 0.5,
                    "shoulderPosition": "unknown",
                    "headPosition": "unknown"
                },
                facial_expression={
                    "engagement": 0.5,
                    "eyeContact": 0.5,
                    "expressions": ["neutral"]
                },
                gestures={
                    "handMovement": 0.5,
                    "gestureTypes": [],
                    "appropriateness": 0.5
                },
                overall_confidence=0.5,
                recommendations=["Body language analysis via Gemini API - local CV not available"]
            )
        
        return await self.body_language_service.analyze_video_frames(
            video_data,
            frame_rate=frame_rate,
            sample_rate=5  # Analyze every 5th frame
        )
    
    def calculate_speech_quality_score(self, prosody_metrics: ProsodyMetrics) -> Dict[str, Any]:
        """
        Calculate comprehensive speech quality score based on prosody metrics
        
        Returns a score from 0-100 with breakdown by category
        """
        scores = {}
        
        # Pitch quality (0-100)
        # Ideal pitch range is 50-100 Hz for variation
        pitch_score = 100
        if prosody_metrics.pitch_range < 30:
            pitch_score = 60  # Monotone
        elif prosody_metrics.pitch_range > 150:
            pitch_score = 70  # Too variable
        scores["pitch_quality"] = pitch_score
        
        # Voice quality (0-100)
        # Based on jitter, shimmer, and HNR
        voice_score = 100
        if prosody_metrics.jitter > 0.02:
            voice_score -= 20
        if prosody_metrics.shimmer > 0.08:
            voice_score -= 20
        if prosody_metrics.harmonic_to_noise_ratio < 10:
            voice_score -= 30
        scores["voice_quality"] = max(0, voice_score)
        
        # Fluency (0-100)
        # Based on filler words and pauses
        fluency_score = 100
        if prosody_metrics.filler_word_count > 5:
            fluency_score -= min(50, prosody_metrics.filler_word_count * 5)
        if prosody_metrics.average_pause_length > 1.0:
            fluency_score -= 20
        scores["fluency"] = max(0, fluency_score)
        
        # Pace (0-100)
        # Ideal speaking rate is 140-180 WPM
        pace_score = 100
        wpm = prosody_metrics.words_per_minute
        if wpm < 100:
            pace_score = 60  # Too slow
        elif wpm > 200:
            pace_score = 70  # Too fast
        elif wpm < 140 or wpm > 180:
            pace_score = 85  # Slightly off ideal
        scores["pace"] = pace_score
        
        # Overall score (weighted average)
        overall_score = (
            scores["pitch_quality"] * 0.25 +
            scores["voice_quality"] * 0.30 +
            scores["fluency"] * 0.25 +
            scores["pace"] * 0.20
        )
        
        return {
            "overall_score": round(overall_score, 2),
            "category_scores": scores,
            "grade": self._score_to_grade(overall_score),
            "recommendations": self._generate_recommendations(scores, prosody_metrics)
        }
    
    def _score_to_grade(self, score: float) -> str:
        """Convert numeric score to letter grade"""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"
    
    def _generate_recommendations(
        self, 
        scores: Dict[str, float], 
        metrics: ProsodyMetrics
    ) -> List[str]:
        """Generate personalized recommendations based on scores"""
        recommendations = []
        
        if scores["pitch_quality"] < 80:
            if metrics.pitch_range < 30:
                recommendations.append(
                    "Vary your pitch more to sound more engaging and natural"
                )
            else:
                recommendations.append(
                    "Try to maintain more consistent pitch variation"
                )
        
        if scores["voice_quality"] < 80:
            if metrics.jitter > 0.02:
                recommendations.append(
                    "Work on voice stability - practice breath control exercises"
                )
            if metrics.harmonic_to_noise_ratio < 10:
                recommendations.append(
                    "Improve voice clarity - ensure proper microphone technique"
                )
        
        if scores["fluency"] < 80:
            if metrics.filler_word_count > 5:
                recommendations.append(
                    f"Reduce filler words (detected {metrics.filler_word_count}) - pause instead of using fillers"
                )
            if metrics.average_pause_length > 1.0:
                recommendations.append(
                    "Reduce long pauses - practice maintaining flow"
                )
        
        if scores["pace"] < 80:
            wpm = metrics.words_per_minute
            if wpm < 100:
                recommendations.append(
                    f"Increase speaking pace (current: {wpm:.0f} WPM, target: 140-180 WPM)"
                )
            elif wpm > 200:
                recommendations.append(
                    f"Slow down your speaking pace (current: {wpm:.0f} WPM, target: 140-180 WPM)"
                )
        
        if not recommendations:
            recommendations.append("Excellent speech quality! Keep up the great work.")
        
        return recommendations
