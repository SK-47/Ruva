from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class VADSegment(BaseModel):
    start_time: float
    end_time: float
    confidence: float
    is_speech: bool

class ProsodyMetrics(BaseModel):
    duration: float
    words_per_minute: float
    average_pitch: float
    pitch_range: float
    average_intensity: float
    intensity_range: float
    jitter: float
    shimmer: float
    harmonic_to_noise_ratio: float
    formants: List[float]
    sentiment_score: float
    sentiment_label: str
    filler_word_count: int
    pause_count: int
    average_pause_length: float

class BodyLanguageAnalysis(BaseModel):
    posture: dict
    facial_expression: dict
    gestures: dict
    overall_confidence: float
    recommendations: List[str]

class SpeechAnalysis(BaseModel):
    id: str
    session_id: str
    participant_id: str
    transcript: str
    vad_segments: List[VADSegment]
    prosody_metrics: ProsodyMetrics
    body_language_analysis: Optional[BodyLanguageAnalysis] = None
    timestamp: datetime

class TranscribeRequest(BaseModel):
    audio_data: bytes
    participant_id: str
    session_id: str

class AnalyzeRequest(BaseModel):
    audio_data: bytes
    transcript: str
    participant_id: str
    session_id: str
    include_body_language: bool = False