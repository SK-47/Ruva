"""
API routes for Group Discussion Mode
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime

from app.services.modes.group_discussion_mode import (
    group_discussion_service,
    GroupDiscussionState
)
from app.core.database import get_database
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter()


class CreateGroupDiscussionRequest(BaseModel):
    room_id: str
    session_id: str
    participant_ids: List[str]
    participant_names: Dict[str, str]
    ai_facilitator_id: str
    topic: Optional[str] = None
    max_turns: Optional[int] = None


class SetTopicRequest(BaseModel):
    topic: str


class AddContributionRequest(BaseModel):
    participant_id: str
    participant_name: str
    text: str
    is_facilitator: bool = False


class StartTurnRequest(BaseModel):
    participant_id: str
    participant_name: str


class EndTurnRequest(BaseModel):
    participant_id: str
    contribution_text: str
    word_count: int
    speaking_time: float


class AddTopicSuggestionRequest(BaseModel):
    topic: str


@router.post("/group-discussions")
async def create_group_discussion(
    request: CreateGroupDiscussionRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Create a new group discussion session"""
    try:
        # Validate at least 2 participants
        if len(request.participant_ids) < 2:
            raise HTTPException(
                status_code=400,
                detail="Group discussion requires at least 2 participants"
            )
        
        # Create discussion
        discussion_state = group_discussion_service.create_discussion(
            room_id=request.room_id,
            session_id=request.session_id,
            participant_ids=request.participant_ids,
            participant_names=request.participant_names,
            ai_facilitator_id=request.ai_facilitator_id,
            topic=request.topic,
            max_turns=request.max_turns
        )
        
        # Store in database
        await db.group_discussion_sessions.insert_one(discussion_state.model_dump())
        
        return {
            "success": True,
            "session_id": request.session_id,
            "discussion_state": discussion_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create group discussion: {str(e)}")


@router.post("/group-discussions/{session_id}/topic")
async def set_discussion_topic(
    session_id: str,
    request: SetTopicRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Set the discussion topic"""
    try:
        discussion_state = group_discussion_service.set_topic(session_id, request.topic)
        
        # Update database
        await db.group_discussion_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "topic": discussion_state.topic,
                "phase": discussion_state.phase,
                "updated_at": discussion_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "topic": discussion_state.topic,
            "discussion_state": discussion_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set topic: {str(e)}")


@router.post("/group-discussions/{session_id}/start")
async def start_discussion(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Start the discussion phase"""
    try:
        discussion_state = group_discussion_service.start_discussion(session_id)
        
        # Update database
        await db.group_discussion_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "phase": discussion_state.phase,
                "current_turn": discussion_state.current_turn,
                "updated_at": discussion_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "discussion_state": discussion_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start discussion: {str(e)}")


@router.post("/group-discussions/{session_id}/contributions")
async def add_contribution(
    session_id: str,
    request: AddContributionRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Add a contribution to the discussion"""
    try:
        discussion_state = group_discussion_service.add_contribution(
            session_id,
            request.participant_id,
            request.participant_name,
            request.text,
            request.is_facilitator
        )
        
        # Update database
        await db.group_discussion_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "contributions": [c.model_dump() for c in discussion_state.contributions],
                "current_speaker_id": discussion_state.current_speaker_id,
                "updated_at": discussion_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "discussion_state": discussion_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add contribution: {str(e)}")


@router.post("/group-discussions/{session_id}/turns/start")
async def start_turn(
    session_id: str,
    request: StartTurnRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Start a participant's turn"""
    try:
        discussion_state = group_discussion_service.start_turn(
            session_id,
            request.participant_id,
            request.participant_name
        )
        
        # Update database
        await db.group_discussion_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "turns": [t.model_dump() for t in discussion_state.turns],
                "current_speaker_id": discussion_state.current_speaker_id,
                "updated_at": discussion_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "discussion_state": discussion_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start turn: {str(e)}")


@router.post("/group-discussions/{session_id}/turns/end")
async def end_turn(
    session_id: str,
    request: EndTurnRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """End a participant's turn"""
    try:
        discussion_state = group_discussion_service.end_turn(
            session_id,
            request.participant_id,
            request.contribution_text,
            request.word_count,
            request.speaking_time
        )
        
        # Update database
        await db.group_discussion_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "turns": [t.model_dump() for t in discussion_state.turns],
                "current_speaker_id": discussion_state.current_speaker_id,
                "updated_at": discussion_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "discussion_state": discussion_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to end turn: {str(e)}")


@router.get("/group-discussions/{session_id}/next-speaker")
async def suggest_next_speaker(session_id: str):
    """Suggest the next speaker based on participation balance"""
    try:
        next_speaker = group_discussion_service.suggest_next_speaker(session_id)
        
        return {
            "success": True,
            "next_speaker": next_speaker
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to suggest next speaker: {str(e)}")


@router.post("/group-discussions/{session_id}/topic-suggestions")
async def add_topic_suggestion(
    session_id: str,
    request: AddTopicSuggestionRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Add a topic suggestion from the facilitator"""
    try:
        discussion_state = group_discussion_service.add_topic_suggestion(
            session_id,
            request.topic
        )
        
        # Update database
        await db.group_discussion_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "suggested_topics": discussion_state.suggested_topics,
                "updated_at": discussion_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "suggested_topics": discussion_state.suggested_topics
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add topic suggestion: {str(e)}")


@router.get("/group-discussions/{session_id}/dynamics")
async def analyze_group_dynamics(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Analyze group dynamics and participation"""
    try:
        analysis = group_discussion_service.analyze_group_dynamics(session_id)
        
        # Update database
        await db.group_discussion_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "dynamics_analysis": analysis.model_dump(),
                "updated_at": datetime.utcnow()
            }}
        )
        
        return {
            "success": True,
            "analysis": analysis.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze dynamics: {str(e)}")


@router.post("/group-discussions/{session_id}/conclude")
async def conclude_discussion(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Move discussion to conclusion phase"""
    try:
        discussion_state = group_discussion_service.conclude_discussion(session_id)
        
        # Update database
        await db.group_discussion_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "phase": discussion_state.phase,
                "dynamics_analysis": discussion_state.dynamics_analysis.model_dump() if discussion_state.dynamics_analysis else None,
                "updated_at": discussion_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "discussion_state": discussion_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to conclude discussion: {str(e)}")


@router.post("/group-discussions/{session_id}/complete")
async def complete_discussion(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Mark discussion as completed"""
    try:
        discussion_state = group_discussion_service.complete_discussion(session_id)
        
        # Update database
        await db.group_discussion_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "phase": discussion_state.phase,
                "updated_at": discussion_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "discussion_state": discussion_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to complete discussion: {str(e)}")


@router.get("/group-discussions/{session_id}")
async def get_discussion_state(session_id: str):
    """Get the current state of a discussion"""
    try:
        discussion_state = group_discussion_service.get_discussion_state(session_id)
        
        if not discussion_state:
            raise HTTPException(status_code=404, detail="Discussion session not found")
        
        return {
            "success": True,
            "discussion_state": discussion_state.model_dump()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get discussion state: {str(e)}")


@router.get("/group-discussions/{session_id}/summary")
async def get_discussion_summary(session_id: str):
    """Get a summary of the discussion"""
    try:
        summary = group_discussion_service.get_discussion_summary(session_id)
        
        if not summary:
            raise HTTPException(status_code=404, detail="Discussion session not found")
        
        return {
            "success": True,
            "summary": summary
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get discussion summary: {str(e)}")


@router.post("/group-discussions/{session_id}/assign-roles")
async def assign_roles(
    session_id: str,
    topic: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Assign roles to participants based on topic"""
    try:
        discussion_state = group_discussion_service.get_discussion_state(session_id)
        if not discussion_state:
            raise HTTPException(status_code=404, detail="Discussion session not found")
        
        # Generate roles and scenario
        role_data = group_discussion_service.generate_roles_and_scenario(
            session_id, topic, len(discussion_state.participants)
        )
        
        # Assign roles to participants
        roles_assignment = {}
        for i, participant_id in enumerate(discussion_state.participants):
            if i < len(role_data['roles']):
                role_info = role_data['roles'][i]
                roles_assignment[participant_id] = {
                    "role": role_info['role'],
                    "description": role_info['description']
                }
        
        # Update discussion state
        updated_state = group_discussion_service.assign_roles(session_id, roles_assignment)
        
        # Update database
        await db.group_discussion_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "participant_roles": updated_state.participant_roles,
                "participant_role_descriptions": updated_state.participant_role_descriptions,
                "scenario": role_data['scenario'],
                "updated_at": updated_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "scenario": role_data['scenario'],
            "roles": roles_assignment,
            "category": role_data['category']
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to assign roles: {str(e)}")

@router.delete("/group-discussions/{session_id}")
async def end_discussion(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """End and cleanup a discussion session"""
    try:
        group_discussion_service.end_discussion(session_id)
        
        # Mark as completed in database
        await db.group_discussion_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "ended_at": datetime.utcnow()
            }}
        )
        
        return {
            "success": True,
            "message": "Discussion ended successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to end discussion: {str(e)}")
