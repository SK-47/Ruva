from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from enum import Enum

class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Transcript(BaseModel):
    id: str
    participant_id: str
    text: str
    timestamp: datetime
    confidence: float

class AIInteraction(BaseModel):
    id: str
    session_id: str
    participant_id: str  # AI participant
    prompt: str
    response: str
    timestamp: datetime
    response_time: float

class Session(BaseModel):
    id: str
    room_id: str
    participants: List[str]
    start_time: datetime
    end_time: Optional[datetime] = None
    transcripts: List[Transcript] = []
    ai_interactions: List[AIInteraction] = []
    status: SessionStatus = SessionStatus.ACTIVE

class CreateSessionRequest(BaseModel):
    room_id: str
    participants: List[str] = []  # Optional - can be empty initially

class UpdateSessionRequest(BaseModel):
    status: SessionStatus
    end_time: Optional[datetime] = None