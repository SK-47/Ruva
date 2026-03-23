from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from app.models.session import Session, CreateSessionRequest, UpdateSessionRequest, SessionStatus
from app.core.database import get_database
from app.services.session_service import SessionService
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter()


def get_session_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> SessionService:
    """Dependency to get session service"""
    return SessionService(db)


@router.post("/", response_model=Session)
async def create_session(
    request: CreateSessionRequest,
    service: SessionService = Depends(get_session_service)
):
    """Create a new session"""
    session = await service.start_session(
        room_id=request.room_id,
        participants=request.participants,
        mode="general",  # Can be extended to include mode in request
        metadata={}
    )
    
    return session

@router.get("/{session_id}", response_model=Session)
async def get_session(
    session_id: str,
    service: SessionService = Depends(get_session_service)
):
    """Get session details"""
    session = await service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session


@router.get("/{session_id}/full")
async def get_session_full(
    session_id: str,
    service: SessionService = Depends(get_session_service)
):
    """Get session with all associated data including speech analyses"""
    session_data = await service.get_session_with_analyses(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session_data

@router.put("/{session_id}", response_model=Session)
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Update session status"""
    update_data = {"status": request.status}
    
    if request.end_time:
        update_data["end_time"] = request.end_time
    elif request.status in [SessionStatus.COMPLETED, SessionStatus.CANCELLED]:
        update_data["end_time"] = datetime.utcnow()
    
    result = await db.sessions.update_one(
        {"id": session_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Return updated session
    session_data = await db.sessions.find_one({"id": session_id})
    return Session(**session_data)


@router.post("/{session_id}/end", response_model=Session)
async def end_session(
    session_id: str,
    reason: str = "completed",
    service: SessionService = Depends(get_session_service)
):
    """End a session"""
    try:
        session = await service.end_session(session_id, reason)
        return session
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/user/{user_id}/sessions", response_model=List[Session])
async def get_user_sessions(
    user_id: str,
    limit: int = 50,
    status: Optional[SessionStatus] = None,
    service: SessionService = Depends(get_session_service)
):
    """Get user's session history"""
    sessions = await service.get_participant_sessions(user_id, limit, status)
    return sessions


@router.get("/room/{room_id}/sessions", response_model=List[Session])
async def get_room_sessions(
    room_id: str,
    limit: int = 50,
    service: SessionService = Depends(get_session_service)
):
    """Get sessions for a specific room"""
    sessions = await service.get_room_sessions(room_id, limit)
    return sessions


@router.post("/{session_id}/transcript")
async def add_transcript(
    session_id: str,
    participant_id: str,
    text: str,
    confidence: float = 1.0,
    service: SessionService = Depends(get_session_service)
):
    """Add a transcript entry to the session"""
    await service.add_transcript(session_id, participant_id, text, confidence)
    return {"status": "success", "message": "Transcript added"}


@router.post("/{session_id}/ai-interaction")
async def add_ai_interaction(
    session_id: str,
    ai_participant_id: str,
    prompt: str,
    response: str,
    response_time: float,
    service: SessionService = Depends(get_session_service)
):
    """Record an AI interaction in the session"""
    await service.add_ai_interaction(
        session_id, ai_participant_id, prompt, response, response_time
    )
    return {"status": "success", "message": "AI interaction recorded"}


@router.get("/{session_id}/participant/{participant_id}/metrics")
async def get_participant_metrics(
    session_id: str,
    participant_id: str,
    service: SessionService = Depends(get_session_service)
):
    """Get aggregated metrics for a participant in a session"""
    metrics = await service.calculate_aggregated_metrics(session_id, participant_id)
    return metrics