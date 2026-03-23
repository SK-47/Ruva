"""
Tests for Advanced Speech Analysis Service

These tests verify the Tier 2 detailed analysis functionality including:
- Parselmouth prosody analysis
- Advanced speech quality metrics
- Body language analysis integration
"""

import pytest
import numpy as np
import io
import soundfile as sf
from app.services.advanced_speech_service import AdvancedSpeechAnalysisService
from app.models.speech import ProsodyMetrics


@pytest.fixture
def advanced_service():
    """Create an instance of AdvancedSpeechAnalysisService"""
    return AdvancedSpeechAnalysisService()


@pytest.fixture
def sample_audio_data():
    """Generate sample audio data for testing"""
    # Generate a simple sine wave (440 Hz, 2 seconds)
    sample_rate = 16000
    duration = 2.0
    frequency = 440.0
    
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio_array = np.sin(2 * np.pi * frequency * t).astype(np.float32)
    
    # Convert to WAV bytes
    buffer = io.BytesIO()
    sf.write(buffer, audio_array, sample_rate, format='WAV')
    buffer.seek(0)
    
    return buffer.read()


@pytest.mark.asyncio
async def test_analyze_prosody_detailed_basic(advanced_service, sample_audio_data):
    """Test basic prosody analysis with sample audio"""
    transcript = "This is a test transcript for speech analysis"
    
    result = await advanced_service.analyze_prosody_detailed(
        sample_audio_data,
        transcript
    )
    
    # Verify result is ProsodyMetrics
    assert isinstance(result, ProsodyMetrics)
    
    # Verify basic metrics are present
    assert result.duration > 0
    assert result.words_per_minute >= 0
    assert result.average_pitch > 0
    assert result.pitch_range >= 0
    assert result.average_intensity > 0
    assert result.jitter >= 0
    assert result.shimmer >= 0
    assert result.harmonic_to_noise_ratio > 0
    assert len(result.formants) == 3


@pytest.mark.asyncio
async def test_filler_word_detection(advanced_service):
    """Test filler word detection in transcripts"""
    test_cases = [
        ("um well you know I think that's good", 3),  # um, well, you know
        ("This is a clean sentence", 0),
        ("like basically um I mean yeah", 4),  # like, basically, um, i mean
        ("", 0)
    ]
    
    for transcript, expected_count in test_cases:
        count = advanced_service._count_filler_words(transcript)
        assert count == expected_count, f"Failed for: {transcript}"


def test_speech_quality_score_calculation(advanced_service):
    """Test speech quality score calculation"""
    # Create sample prosody metrics
    good_metrics = ProsodyMetrics(
        duration=10.0,
        words_per_minute=150,  # Ideal pace
        average_pitch=150.0,
        pitch_range=60.0,  # Good variation
        average_intensity=65.0,
        intensity_range=20.0,
        jitter=0.01,  # Low jitter (good)
        shimmer=0.04,  # Low shimmer (good)
        harmonic_to_noise_ratio=18.0,  # High HNR (good)
        formants=[800.0, 1200.0, 2500.0],
        sentiment_score=0.0,
        sentiment_label="neutral",
        filler_word_count=1,  # Few fillers
        pause_count=3,
        average_pause_length=0.4
    )
    
    quality_score = advanced_service.calculate_speech_quality_score(good_metrics)
    
    # Verify structure
    assert "overall_score" in quality_score
    assert "category_scores" in quality_score
    assert "grade" in quality_score
    assert "recommendations" in quality_score
    
    # Verify score is reasonable for good metrics
    assert quality_score["overall_score"] >= 70
    assert quality_score["grade"] in ["A", "B", "C", "D", "F"]
    
    # Verify category scores
    assert "pitch_quality" in quality_score["category_scores"]
    assert "voice_quality" in quality_score["category_scores"]
    assert "fluency" in quality_score["category_scores"]
    assert "pace" in quality_score["category_scores"]


def test_speech_quality_score_poor_metrics(advanced_service):
    """Test speech quality score with poor metrics"""
    poor_metrics = ProsodyMetrics(
        duration=10.0,
        words_per_minute=80,  # Too slow
        average_pitch=150.0,
        pitch_range=15.0,  # Monotone
        average_intensity=65.0,
        intensity_range=20.0,
        jitter=0.03,  # High jitter (poor)
        shimmer=0.10,  # High shimmer (poor)
        harmonic_to_noise_ratio=8.0,  # Low HNR (poor)
        formants=[800.0, 1200.0, 2500.0],
        sentiment_score=0.0,
        sentiment_label="neutral",
        filler_word_count=15,  # Many fillers
        pause_count=10,
        average_pause_length=1.5  # Long pauses
    )
    
    quality_score = advanced_service.calculate_speech_quality_score(poor_metrics)
    
    # Verify score is lower for poor metrics
    assert quality_score["overall_score"] < 70
    
    # Verify recommendations are provided
    assert len(quality_score["recommendations"]) > 0


@pytest.mark.asyncio
async def test_analysis_queue_operations(advanced_service):
    """Test background analysis queue operations"""
    # Test queuing an analysis task
    task = {
        "task_id": "test_task_1",
        "type": "prosody",
        "audio_data": b"fake_audio_data",
        "transcript": "test transcript",
        "callback": lambda x: None
    }
    
    await advanced_service.queue_analysis(task)
    
    # Verify task was queued
    assert not advanced_service.analysis_queue.empty()


def test_default_prosody_metrics(advanced_service):
    """Test default prosody metrics generation"""
    transcript = "This is a test with five words"
    
    metrics = advanced_service._get_default_prosody_metrics(transcript)
    
    assert isinstance(metrics, ProsodyMetrics)
    assert metrics.duration == 1.0
    assert metrics.words_per_minute == len(transcript.split()) * 60
    assert metrics.filler_word_count == 0


@pytest.mark.asyncio
async def test_analyze_prosody_with_vad_segments(advanced_service, sample_audio_data):
    """Test prosody analysis with VAD segments"""
    from app.models.speech import VADSegment
    
    transcript = "Test transcript"
    vad_segments = [
        VADSegment(start_time=0.0, end_time=1.0, confidence=0.9, is_speech=True),
        VADSegment(start_time=1.5, end_time=2.0, confidence=0.85, is_speech=True)
    ]
    
    result = await advanced_service.analyze_prosody_detailed(
        sample_audio_data,
        transcript,
        vad_segments
    )
    
    assert isinstance(result, ProsodyMetrics)
    assert result.pause_count >= 0
    assert result.average_pause_length >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
