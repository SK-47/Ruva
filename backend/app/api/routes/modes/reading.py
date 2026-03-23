"""
Reading Mode API Routes
"""

from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from typing import Optional, List
import logging

from app.core.database import get_database
from app.services.modes.reading_mode import reading_service, ReadingDifficulty, ReadingGenre

logger = logging.getLogger(__name__)

router = APIRouter()

class CreateReadingSessionRequest(BaseModel):
    room_id: str
    participant_id: str
    participant_name: str
    difficulty_level: ReadingDifficulty = ReadingDifficulty.BEGINNER

class SetPassageRequest(BaseModel):
    passage: str
    genre: ReadingGenre = ReadingGenre.NON_FICTION

class CompleteReadingRequest(BaseModel):
    transcript: str
    reading_duration: float

@router.post("/reading-sessions")
async def create_reading_session(
    request: CreateReadingSessionRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Create a new reading session"""
    try:
        import uuid
        session_id = f"reading_{request.room_id}_{int(datetime.utcnow().timestamp())}"
        
        reading_state = reading_service.create_session(
            room_id=request.room_id,
            session_id=session_id,
            participant_id=request.participant_id,
            participant_name=request.participant_name,
            difficulty_level=request.difficulty_level
        )
        
        # Store in database
        await db.reading_sessions.insert_one({
            "session_id": session_id,
            "room_id": request.room_id,
            "participant_id": request.participant_id,
            "participant_name": request.participant_name,
            "difficulty_level": request.difficulty_level,
            "created_at": reading_state.created_at,
            "updated_at": reading_state.updated_at
        })
        
        return {
            "session_id": session_id,
            "reading_state": reading_state.model_dump()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating reading session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create reading session: {str(e)}")

@router.post("/reading-sessions/{session_id}/passage")
async def set_reading_passage(
    session_id: str,
    request: SetPassageRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Set a reading passage for the session"""
    try:
        reading_state = reading_service.set_passage(
            session_id,
            request.passage,
            request.genre
        )
        
        # Update database
        await db.reading_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "current_passage": request.passage,
                "current_genre": request.genre,
                "phase": reading_state.phase,
                "updated_at": reading_state.updated_at
            }}
        )
        
        return {
            "session_id": session_id,
            "passage": request.passage,
            "genre": request.genre,
            "reading_state": reading_state.model_dump()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set passage: {str(e)}")

@router.post("/reading-sessions/{session_id}/generate-passage")
async def generate_reading_passage(
    session_id: str,
    difficulty_level: ReadingDifficulty = ReadingDifficulty.BEGINNER,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Generate an adaptive passage for reading session"""
    try:
        passage = reading_service.generate_adaptive_passage(session_id)
        
        reading_state = reading_service.set_passage(
            session_id,
            passage,
            ReadingGenre.NON_FICTION
        )
        
        # Update database
        await db.reading_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "current_passage": passage,
                "current_genre": ReadingGenre.NON_FICTION,
                "phase": reading_state.phase,
                "updated_at": reading_state.updated_at
            }}
        )
        
        return {
            "session_id": session_id,
            "passage": passage,
            "difficulty_level": difficulty_level
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate passage: {str(e)}")

@router.post("/reading-sessions/{session_id}/start")
async def start_reading_attempt(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Start a new reading attempt"""
    try:
        reading_state = reading_service.start_reading_attempt(session_id)
        
        # Update database
        await db.reading_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "phase": reading_state.phase,
                "total_attempts": reading_state.total_attempts,
                "updated_at": reading_state.updated_at
            }}
        )
        
        return {
            "session_id": session_id,
            "attempt_number": reading_state.current_attempt.attempt_number,
            "passage": reading_state.current_attempt.passage,
            "word_count": reading_state.current_attempt.word_count,
            "reading_state": reading_state.model_dump()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start reading attempt: {str(e)}")

@router.post("/reading-sessions/{session_id}/complete")
async def complete_reading_attempt(
    session_id: str,
    request: CompleteReadingRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Complete the current reading attempt"""
    try:
        reading_state = reading_service.complete_reading_attempt(
            session_id,
            request.transcript,
            request.reading_duration
        )
        
        # Generate feedback
        feedback = reading_service.analyze_reading_performance(session_id)
        
        # Update database
        await db.reading_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "phase": reading_state.phase,
                "total_attempts": reading_state.total_attempts,
                "session_feedback": feedback.model_dump() if feedback else None,
                "updated_at": reading_state.updated_at
            }}
        )
        
        return {
            "session_id": session_id,
            "reading_state": reading_state.model_dump(),
            "feedback": feedback.model_dump() if feedback else None
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to complete reading attempt: {str(e)}")

@router.get("/reading-sessions/{session_id}")
async def get_reading_session(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get reading session state"""
    try:
        reading_state = reading_service.get_session_state(session_id)
        
        if not reading_state:
            raise HTTPException(status_code=404, detail="Reading session not found")
        
        return {
            "session_id": session_id,
            "reading_state": reading_state.model_dump()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get reading session: {str(e)}")

@router.get("/reading-sessions/{session_id}/summary")
async def get_reading_summary(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get reading session summary"""
    try:
        summary = reading_service.get_session_summary(session_id)
        
        if not summary:
            raise HTTPException(status_code=404, detail="Reading session not found")
        
        return summary
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get reading summary: {str(e)}")

@router.post("/reading-sessions/{session_id}/reset")
async def reset_for_new_passage(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Reset session for a new passage"""
    try:
        reading_state = reading_service.get_session_state(session_id)
        if not reading_state:
            raise HTTPException(status_code=404, detail="Reading session not found")
        
        # Reset to setup phase
        reading_state.phase = reading_service.ReadingPhase.SETUP
        reading_state.current_passage = None
        reading_state.current_attempt = None
        reading_state.session_feedback = None
        reading_state.updated_at = datetime.utcnow()
        
        # Update database
        await db.reading_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "phase": reading_state.phase,
                "current_passage": None,
                "current_attempt": None,
                "session_feedback": None,
                "updated_at": reading_state.updated_at
            }}
        )
        
        return {
            "session_id": session_id,
            "message": "Session reset for new passage",
            "reading_state": reading_state.model_dump()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset session: {str(e)}")

# Import datetime for the routes
from datetime import datetime