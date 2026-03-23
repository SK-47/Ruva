from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum

class RoomMode(str, Enum):
    DEBATE = "debate"
    GROUP_DISCUSSION = "group-discussion"
    JAM = "jam"
    READING = "reading"
    INTERVIEW = "interview"
    BUSINESS_TALKS = "business-talks"
    SOCIALISING = "socialising"

class DiscussionMode(str, Enum):
    BUSINESS = "business"
    CASUAL = "casual"

class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"

class Participant(BaseModel):
    id: str
    name: str
    is_ai: bool = False
    joined_at: datetime
    is_speaking: bool = False
    connection_status: ConnectionStatus = ConnectionStatus.CONNECTED
    role: Optional[str] = None  # For group discussions (e.g., "Creator", "Gallery Owner")
    role_description: Optional[str] = None  # Detailed role context
    is_ready: bool = False  # For group discussions ready system
    evaluation_metrics: Optional[dict] = None  # Individual performance tracking

class Room(BaseModel):
    id: str
    name: str
    mode: RoomMode
    max_participants: int
    participants: List[Participant] = []
    ai_judge_enabled: bool = False
    ai_facilitator_enabled: bool = False
    ai_player_enabled: bool = False
    created_at: datetime
    is_active: bool = True
    current_topic: Optional[str] = None
    debate_rounds: Optional[int] = None
    current_round: Optional[int] = None
    discussion_mode: Optional[DiscussionMode] = None  # For group discussions
    scenario: Optional[str] = None  # AI-generated scenario
    round_in_progress: bool = False  # Track if round is active
    round_start_time: Optional[datetime] = None

class CreateRoomRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    mode: RoomMode
    ai_enabled: bool = False
    ai_player_enabled: bool = False
    max_participants: Optional[int] = None

class JoinRoomRequest(BaseModel):
    participant_name: str = Field(..., min_length=1, max_length=50)