"""
API routes for JAM (Just-A-Minute) Mode
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.services.modes.jam_mode import (
    jam_service,
    JAMState
)
from app.core.database import get_database
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter()


class CreateJAMSessionRequest(BaseModel):
    room_id: str
    session_id: str
    participant_id: str
    participant_name: str
    ai_coach_id: str


class SetTopicRequest(BaseModel):
    topic: str
    genre: Optional[str] = None


class EndAttemptRequest(BaseModel):
    transcript: str
    duration: float


@router.post("/jam-sessions")
async def create_jam_session(
    request: CreateJAMSessionRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Create a new JAM session"""
    try:
        # Create JAM session
        jam_state = jam_service.create_jam_session(
            room_id=request.room_id,
            session_id=request.session_id,
            participant_id=request.participant_id,
            participant_name=request.participant_name,
            ai_coach_id=request.ai_coach_id
        )
        
        # Store in database
        await db.jam_sessions.insert_one(jam_state.model_dump())
        
        return {
            "success": True,
            "session_id": request.session_id,
            "jam_state": jam_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create JAM session: {str(e)}")


@router.post("/jam-sessions/{session_id}/topic")
async def set_jam_topic(
    session_id: str,
    request: SetTopicRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Set a new topic for the JAM session"""
    try:
        jam_state = jam_service.set_topic(
            session_id,
            request.topic,
            request.genre
        )
        
        # Update database
        await db.jam_sessions.update_one(
            {"session_id": session_id},
            {"$set": jam_state.model_dump()},
            upsert=True
        )
        
        return {
            "success": True,
            "session_id": session_id,
            "topic": request.topic,
            "phase": jam_state.phase
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set topic: {str(e)}")

@router.post("/jam-sessions/{session_id}/start-attempt")
async def start_jam_attempt(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Start a new JAM attempt"""
    try:
        jam_state = jam_service.start_attempt(session_id)
        
        # Update database
        await db.jam_sessions.update_one(
            {"session_id": session_id},
            {"$set": jam_state.model_dump()},
            upsert=True
        )
        
        return {
            "success": True,
            "session_id": session_id,
            "attempt_number": jam_state.current_attempt.attempt_number if jam_state.current_attempt else 0,
            "phase": jam_state.phase
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start attempt: {str(e)}")

@router.post("/jam-sessions/{session_id}/end-attempt")
async def end_jam_attempt(
    session_id: str,
    request: EndAttemptRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """End the current JAM attempt"""
    try:
        jam_state = jam_service.end_attempt(
            session_id,
            request.transcript,
            request.duration
        )
        
        # Generate feedback
        feedback = jam_service.generate_feedback(session_id)
        
        # Update database
        await db.jam_sessions.update_one(
            {"session_id": session_id},
            {"$set": jam_state.model_dump()},
            upsert=True
        )
        
        return {
            "success": True,
            "session_id": session_id,
            "attempt": jam_state.attempts[-1].model_dump() if jam_state.attempts else None,
            "feedback": feedback.model_dump(),
            "phase": jam_state.phase
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to end attempt: {str(e)}")

@router.get("/jam-sessions/{session_id}")
async def get_jam_session(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get JAM session state"""
    try:
        jam_state = jam_service.get_session_state(session_id)
        
        if not jam_state:
            raise HTTPException(status_code=404, detail="JAM session not found")
        
        return {
            "success": True,
            "session": jam_state.model_dump()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")

@router.get("/jam-sessions/{session_id}/feedback")
async def get_jam_feedback(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get comprehensive feedback for JAM session"""
    try:
        feedback = jam_service.generate_feedback(session_id)
        
        return {
            "success": True,
            "feedback": feedback.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate feedback: {str(e)}")

@router.post("/jam-sessions/{session_id}/generate-topic")
async def generate_jam_topic(
    session_id: str,
    difficulty_level: int = 1,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Generate an adaptive topic for JAM session"""
    try:
        topic = jam_service.generate_adaptive_topic(session_id, difficulty_level)
        
        return {
            "success": True,
            "topic": topic,
            "difficulty_level": difficulty_level
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate topic: {str(e)}")


@router.post("/jam-sessions/{session_id}/start-attempt")
async def start_jam_attempt(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Start a new speaking attempt"""
    try:
        jam_state = jam_service.start_attempt(session_id)
        
        # Update database
        await db.jam_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "current_attempt": jam_state.current_attempt.model_dump() if jam_state.current_attempt else None,
                "phase": jam_state.phase,
                "updated_at": jam_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "phase": jam_state.phase,
            "attempt_number": jam_state.current_attempt.attempt_number if jam_state.current_attempt else 0,
            "topic": jam_state.current_topic,
            "jam_state": jam_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start attempt: {str(e)}")


@router.post("/jam-sessions/{session_id}/end-attempt")
async def end_jam_attempt(
    session_id: str,
    request: EndAttemptRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """End the current speaking attempt"""
    try:
        jam_state = jam_service.end_attempt(
            session_id,
            request.transcript,
            request.duration
        )
        
        # Update database
        await db.jam_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "attempts": [a.model_dump() for a in jam_state.attempts],
                "total_attempts": jam_state.total_attempts,
                "phase": jam_state.phase,
                "updated_at": jam_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "attempt": jam_state.current_attempt.model_dump() if jam_state.current_attempt else None,
            "jam_state": jam_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to end attempt: {str(e)}")


@router.get("/jam-sessions/{session_id}/feedback")
async def get_jam_feedback(session_id: str):
    """Generate feedback for the current attempt"""
    try:
        feedback = jam_service.generate_feedback(session_id)
        
        return {
            "success": True,
            "feedback": feedback.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate feedback: {str(e)}")


@router.post("/jam-sessions/{session_id}/reset")
async def reset_jam_session(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Reset session for a new topic"""
    try:
        jam_state = jam_service.reset_for_new_topic(session_id)
        
        # Update database
        await db.jam_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "current_topic": jam_state.current_topic,
                "current_attempt": None,
                "phase": jam_state.phase,
                "updated_at": jam_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "message": "Session reset for new topic",
            "jam_state": jam_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset session: {str(e)}")


@router.post("/jam-sessions/{session_id}/complete")
async def complete_jam_session(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Mark session as completed"""
    try:
        jam_state = jam_service.complete_session(session_id)
        
        # Update database
        await db.jam_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "phase": jam_state.phase,
                "updated_at": jam_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "jam_state": jam_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to complete session: {str(e)}")


@router.get("/jam-sessions/{session_id}")
async def get_jam_state(session_id: str):
    """Get the current state of a JAM session"""
    try:
        jam_state = jam_service.get_jam_state(session_id)
        
        if not jam_state:
            raise HTTPException(status_code=404, detail="JAM session not found")
        
        return {
            "success": True,
            "jam_state": jam_state.model_dump()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get JAM state: {str(e)}")


@router.get("/jam-sessions/{session_id}/summary")
async def get_jam_summary(session_id: str):
    """Get a summary of the JAM session"""
    try:
        summary = jam_service.get_session_summary(session_id)
        
        if not summary:
            raise HTTPException(status_code=404, detail="JAM session not found")
        
        return {
            "success": True,
            "summary": summary
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get JAM summary: {str(e)}")


@router.delete("/jam-sessions/{session_id}")
async def end_jam_session(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """End and cleanup a JAM session"""
    try:
        jam_service.end_session(session_id)
        
        # Mark as completed in database
        await db.jam_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "ended_at": datetime.utcnow()
            }}
        )
        
        return {
            "success": True,
            "message": "JAM session ended successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to end JAM session: {str(e)}")


@router.get("/jam-sessions/{session_id}/genres")
async def get_available_genres(session_id: str):
    """Get available topic genres (excluding recently used)"""
    try:
        jam_state = jam_service.get_jam_state(session_id)
        
        if not jam_state:
            raise HTTPException(status_code=404, detail="JAM session not found")
        
        # Get all genres except the last one used
        available_genres = [
            g for g in jam_service.TOPIC_GENRES 
            if g not in jam_state.previous_genres[-1:]
        ]
        
        return {
            "success": True,
            "available_genres": available_genres,
            "previous_genres": jam_state.previous_genres
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get genres: {str(e)}")
