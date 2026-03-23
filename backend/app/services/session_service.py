"""
Session Service - Manages session lifecycle, data collection, and participant tracking

This service handles:
- Session start/end lifecycle
- Real-time data collection during sessions
- Participant tracking and metrics aggregation
- Session state management
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

from app.models.session import (
    Session, SessionStatus, Transcript, AIInteraction
)
from app.models.speech import SpeechAnalysis, ProsodyMetrics
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class SessionService:
    """Service for managing session lifecycle and data collection"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        logger.info("Session Service initialized")
    
    async def start_session(
        self,
        room_id: str,
        participants: List[str],
        mode: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Session:
        """
        Start a new session
        
        Args:
            room_id: ID of the room
            participants: List of participant IDs
            mode: Session mode (debate, group-discussion, jam, reading)
            metadata: Optional metadata for the session
            
        Returns:
            Created Session object
        """
        session_id = str(uuid.uuid4())
        
        session = Session(
            id=session_id,
            room_id=room_id,
            participants=participants,
            start_time=datetime.utcnow(),
            status=SessionStatus.ACTIVE
        )
        
        # Prepare session document with metadata
        session_doc = session.model_dump()
        session_doc["mode"] = mode
        session_doc["metadata"] = metadata or {}
        session_doc["participant_metrics"] = {
            participant_id: {
                "total_speaking_time": 0.0,
                "word_count": 0,
                "speech_count": 0,
                "average_prosody": None
            }
            for participant_id in participants
        }
        
        # Store in database
        await self.db.sessions.insert_one(session_doc)
        
        logger.info(f"Session {session_id} started for room {room_id} with {len(participants)} participants")
        return session
    
    async def end_session(
        self,
        session_id: str,
        reason: str = "completed"
    ) -> Session:
        """
        End an active session
        
        Args:
            session_id: ID of the session to end
            reason: Reason for ending (completed, cancelled, error)
            
        Returns:
            Updated Session object
        """
        # Determine status based on reason
        status = SessionStatus.COMPLETED if reason == "completed" else SessionStatus.CANCELLED
        
        # Update session
        result = await self.db.sessions.update_one(
            {"id": session_id, "status": SessionStatus.ACTIVE},
            {
                "$set": {
                    "status": status,
                    "end_time": datetime.utcnow(),
                    "end_reason": reason
                }
            }
        )
        
        if result.matched_count == 0:
            logger.warning(f"Session {session_id} not found or already ended")
            raise ValueError(f"Session {session_id} not found or already ended")
        
        # Retrieve updated session
        session_data = await self.db.sessions.find_one({"id": session_id})
        
        logger.info(f"Session {session_id} ended with status {status}")
        return Session(**session_data)
    
    async def add_transcript(
        self,
        session_id: str,
        participant_id: str,
        text: str,
        confidence: float = 1.0
    ) -> None:
        """
        Add a transcript entry to the session
        
        Args:
            session_id: ID of the session
            participant_id: ID of the participant who spoke
            text: Transcribed text
            confidence: Transcription confidence score
        """
        transcript = Transcript(
            id=str(uuid.uuid4()),
            participant_id=participant_id,
            text=text,
            timestamp=datetime.utcnow(),
            confidence=confidence
        )
        
        # Add to session transcripts
        await self.db.sessions.update_one(
            {"id": session_id},
            {
                "$push": {"transcripts": transcript.model_dump()},
                "$inc": {
                    f"participant_metrics.{participant_id}.word_count": len(text.split()),
                    f"participant_metrics.{participant_id}.speech_count": 1
                }
            }
        )
        
        logger.debug(f"Added transcript for participant {participant_id} in session {session_id}")
    
    async def add_ai_interaction(
        self,
        session_id: str,
        ai_participant_id: str,
        prompt: str,
        response: str,
        response_time: float
    ) -> None:
        """
        Record an AI interaction in the session
        
        Args:
            session_id: ID of the session
            ai_participant_id: ID of the AI participant
            prompt: Prompt sent to AI
            response: AI response
            response_time: Time taken to generate response (seconds)
        """
        ai_interaction = AIInteraction(
            id=str(uuid.uuid4()),
            session_id=session_id,
            participant_id=ai_participant_id,
            prompt=prompt,
            response=response,
            timestamp=datetime.utcnow(),
            response_time=response_time
        )
        
        # Add to session AI interactions
        await self.db.sessions.update_one(
            {"id": session_id},
            {"$push": {"ai_interactions": ai_interaction.model_dump()}}
        )
        
        logger.debug(f"Added AI interaction for session {session_id}")
    
    async def record_speech_analysis(
        self,
        session_id: str,
        participant_id: str,
        speech_analysis: SpeechAnalysis
    ) -> None:
        """
        Record speech analysis results for a participant
        
        Args:
            session_id: ID of the session
            participant_id: ID of the participant
            speech_analysis: Complete speech analysis data
        """
        # Store speech analysis in separate collection
        analysis_doc = speech_analysis.model_dump()
        await self.db.speech_analyses.insert_one(analysis_doc)
        
        # Update participant metrics in session
        prosody = speech_analysis.prosody_metrics
        
        await self.db.sessions.update_one(
            {"id": session_id},
            {
                "$inc": {
                    f"participant_metrics.{participant_id}.total_speaking_time": prosody.duration
                },
                "$push": {
                    f"participant_metrics.{participant_id}.prosody_history": {
                        "timestamp": speech_analysis.timestamp.isoformat(),
                        "duration": prosody.duration,
                        "words_per_minute": prosody.words_per_minute,
                        "average_pitch": prosody.average_pitch,
                        "filler_word_count": prosody.filler_word_count
                    }
                }
            }
        )
        
        logger.debug(f"Recorded speech analysis for participant {participant_id} in session {session_id}")
    
    async def update_participant_metrics(
        self,
        session_id: str,
        participant_id: str,
        metrics_update: Dict[str, Any]
    ) -> None:
        """
        Update aggregated metrics for a participant
        
        Args:
            session_id: ID of the session
            participant_id: ID of the participant
            metrics_update: Dictionary of metrics to update
        """
        # Build update operations
        update_ops = {}
        for key, value in metrics_update.items():
            update_ops[f"participant_metrics.{participant_id}.{key}"] = value
        
        await self.db.sessions.update_one(
            {"id": session_id},
            {"$set": update_ops}
        )
        
        logger.debug(f"Updated metrics for participant {participant_id} in session {session_id}")
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """
        Retrieve a session by ID
        
        Args:
            session_id: ID of the session
            
        Returns:
            Session object or None if not found
        """
        session_data = await self.db.sessions.find_one({"id": session_id})
        if not session_data:
            return None
        
        return Session(**session_data)
    
    async def get_session_with_analyses(
        self,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve session with all associated speech analyses
        
        Args:
            session_id: ID of the session
            
        Returns:
            Dictionary containing session and analyses
        """
        session_data = await self.db.sessions.find_one({"id": session_id})
        if not session_data:
            return None
        
        # Get all speech analyses for this session
        analyses = await self.db.speech_analyses.find(
            {"session_id": session_id}
        ).sort("timestamp", 1).to_list(None)
        
        return {
            "session": Session(**session_data),
            "speech_analyses": analyses,
            "participant_count": len(session_data.get("participants", [])),
            "total_transcripts": len(session_data.get("transcripts", [])),
            "total_ai_interactions": len(session_data.get("ai_interactions", []))
        }
    
    async def get_participant_sessions(
        self,
        participant_id: str,
        limit: int = 50,
        status: Optional[SessionStatus] = None
    ) -> List[Session]:
        """
        Get all sessions for a participant
        
        Args:
            participant_id: ID of the participant
            limit: Maximum number of sessions to return
            status: Optional filter by session status
            
        Returns:
            List of Session objects
        """
        query = {"participants": participant_id}
        if status:
            query["status"] = status
        
        sessions_data = await self.db.sessions.find(query).sort(
            "start_time", -1
        ).limit(limit).to_list(limit)
        
        return [Session(**session_data) for session_data in sessions_data]
    
    async def get_room_sessions(
        self,
        room_id: str,
        limit: int = 50
    ) -> List[Session]:
        """
        Get all sessions for a room
        
        Args:
            room_id: ID of the room
            limit: Maximum number of sessions to return
            
        Returns:
            List of Session objects
        """
        sessions_data = await self.db.sessions.find(
            {"room_id": room_id}
        ).sort("start_time", -1).limit(limit).to_list(limit)
        
        return [Session(**session_data) for session_data in sessions_data]
    
    async def calculate_aggregated_metrics(
        self,
        session_id: str,
        participant_id: str
    ) -> Dict[str, Any]:
        """
        Calculate aggregated metrics for a participant in a session
        
        Args:
            session_id: ID of the session
            participant_id: ID of the participant
            
        Returns:
            Dictionary of aggregated metrics
        """
        # Get all speech analyses for this participant in this session
        analyses = await self.db.speech_analyses.find({
            "session_id": session_id,
            "participant_id": participant_id
        }).to_list(None)
        
        if not analyses:
            return {
                "total_speeches": 0,
                "total_duration": 0.0,
                "total_words": 0,
                "average_wpm": 0.0,
                "average_pitch": 0.0,
                "average_intensity": 0.0,
                "total_filler_words": 0,
                "total_pauses": 0
            }
        
        # Aggregate metrics
        total_duration = sum(a["prosody_metrics"]["duration"] for a in analyses)
        total_words = sum(len(a["transcript"].split()) for a in analyses)
        total_filler_words = sum(a["prosody_metrics"]["filler_word_count"] for a in analyses)
        total_pauses = sum(a["prosody_metrics"]["pause_count"] for a in analyses)
        
        # Calculate averages
        avg_wpm = (total_words / total_duration * 60) if total_duration > 0 else 0
        avg_pitch = sum(a["prosody_metrics"]["average_pitch"] for a in analyses) / len(analyses)
        avg_intensity = sum(a["prosody_metrics"]["average_intensity"] for a in analyses) / len(analyses)
        
        return {
            "total_speeches": len(analyses),
            "total_duration": round(total_duration, 2),
            "total_words": total_words,
            "average_wpm": round(avg_wpm, 2),
            "average_pitch": round(avg_pitch, 2),
            "average_intensity": round(avg_intensity, 2),
            "total_filler_words": total_filler_words,
            "total_pauses": total_pauses,
            "filler_words_per_minute": round((total_filler_words / total_duration * 60) if total_duration > 0 else 0, 2)
        }
