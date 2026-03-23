"""
Mode-specific services for different coaching modes
"""

from .debate_mode import debate_service, DebateState, DebatePhase
from .group_discussion_mode import group_discussion_service, GroupDiscussionState, DiscussionPhase
from .jam_mode import jam_service, JAMState, JAMPhase
from .reading_mode import reading_service, ReadingState, ReadingPhase

__all__ = [
    "debate_service",
    "DebateState",
    "DebatePhase",
    "group_discussion_service",
    "GroupDiscussionState",
    "DiscussionPhase",
    "jam_service",
    "JAMState",
    "JAMPhase",
    "reading_service",
    "ReadingState",
    "ReadingPhase",
]
