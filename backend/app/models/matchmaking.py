from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

class MatchmakingMode(str, Enum):
    GROUP_DISCUSSION = "group-discussion"
    JAM = "jam"
    DEBATE = "debate"
    READING = "reading"
    INTERVIEW = "interview"
    BUSINESS_TALKS = "business-talks"
    SOCIALISING = "socialising"

class QueueStatus(str, Enum):
    WAITING = "waiting"
    MATCHED = "matched"
    CANCELLED = "cancelled"

class MatchStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"

class RoomPreferences(BaseModel):
    mode: MatchmakingMode
    max_players: int = 2  # Total players including user
    include_ai: bool = True  # Whether to include AI participants
    ai_only: bool = False  # If true, only AI opponents (instant match)
    skill_level: str = "beginner"

class QueueEntry(BaseModel):
    user_id: str
    username: str
    display_name: str
    preferences: RoomPreferences
    joined_at: datetime
    status: QueueStatus = QueueStatus.WAITING
    estimated_wait_time: Optional[int] = None  # seconds

class Match(BaseModel):
    id: str
    mode: MatchmakingMode
    participants: List[str]  # user IDs
    participant_names: dict[str, str]  # user_id -> display_name
    ai_participants: List[str] = []  # AI participant IDs
    session_id: str
    room_id: str
    status: MatchStatus
    created_at: datetime
    expires_at: datetime
    accepted_by: List[str] = []  # user IDs who accepted
    preferences: RoomPreferences

class JoinQueueRequest(BaseModel):
    mode: MatchmakingMode
    max_players: int = 2
    include_ai: bool = True
    ai_only: bool = False
    skill_level: Optional[str] = "beginner"

class MatchResponse(BaseModel):
    match_id: str
    mode: MatchmakingMode
    participants: List[dict]  # [{"user_id": str, "display_name": str, "is_ai": bool}]
    session_id: str
    room_id: str
    expires_in: int  # seconds