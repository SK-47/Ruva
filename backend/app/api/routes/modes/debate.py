"""
API routes for Debate Mode
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging

from app.services.modes.debate_mode import (
    debate_service,
    DebateStance,
    DebateScore,
    DebateState
)

logger = logging.getLogger(__name__)
from app.core.database import get_database
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter()


class CreateDebateRequest(BaseModel):
    room_id: str
    session_id: str
    participant1_id: str
    participant1_name: str
    participant2_id: str
    participant2_name: str
    ai_judge_id: str
    topic: Optional[str] = None


class SetTopicRequest(BaseModel):
    topic: str


class SetStancesRequest(BaseModel):
    participant1_stance: DebateStance
    participant2_stance: DebateStance


class AddArgumentRequest(BaseModel):
    participant_id: str
    participant_name: str
    argument_text: str


class SubmitJudgmentRequest(BaseModel):
    winner_id: str
    winner_name: str
    verdict_summary: str
    user_performance: str
    ai_performance: str
    key_moment: str
    scores: List[DebateScore]


@router.post("/debates")
async def create_debate(
    request: CreateDebateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Create a new debate session"""
    try:
        logger.info(f"🎭 Creating debate session:")
        logger.info(f"  Room ID: {request.room_id}")
        logger.info(f"  Session ID: {request.session_id}")
        logger.info(f"  Participant 1: {request.participant1_name} ({request.participant1_id})")
        logger.info(f"  Participant 2: {request.participant2_name} ({request.participant2_id})")
        logger.info(f"  AI Judge: {request.ai_judge_id}")
        logger.info(f"  Topic: {request.topic}")
        
        # Validate that exactly 2 participants
        if request.participant1_id == request.participant2_id:
            logger.error(f"❌ Same participant ID for both participants: {request.participant1_id}")
            raise HTTPException(
                status_code=400,
                detail="Debate requires two different participants"
            )
        
        # Check if either participant is AI
        is_participant1_ai = request.participant1_id.startswith('ai_') or 'ai' in request.participant1_name.lower()
        is_participant2_ai = request.participant2_id.startswith('ai_') or 'ai' in request.participant2_name.lower()
        
        logger.info(f"🔍 Participant analysis:")
        logger.info(f"  Participant 1 is AI: {is_participant1_ai}")
        logger.info(f"  Participant 2 is AI: {is_participant2_ai}")
        
        if is_participant1_ai and is_participant2_ai:
            logger.warning(f"⚠️ Both participants are AI!")
        elif not is_participant1_ai and not is_participant2_ai:
            logger.info(f"✅ Both participants are human - perfect!")
        else:
            logger.info(f"🤖 Mixed human-AI debate")
        
        # Create debate
        debate_state = debate_service.create_debate(
            room_id=request.room_id,
            session_id=request.session_id,
            participant1_id=request.participant1_id,
            participant1_name=request.participant1_name,
            participant2_id=request.participant2_id,
            participant2_name=request.participant2_name,
            ai_judge_id=request.ai_judge_id,
            topic=request.topic
        )
        
        logger.info(f"✅ Debate created successfully with stance chooser: {debate_state.stance_chooser_id}")
        
        # Store in database
        await db.debate_sessions.insert_one(debate_state.model_dump())
        
        return {
            "success": True,
            "session_id": request.session_id,
            "debate_state": debate_state.model_dump()
        }
    
    except ValueError as e:
        logger.error(f"❌ Validation error creating debate: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Error creating debate: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create debate: {str(e)}")


@router.post("/debates/{session_id}/topic")
async def set_debate_topic(
    session_id: str,
    request: SetTopicRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Set the debate topic"""
    try:
        logger.info(f"🎯 Setting debate topic for session {session_id}: {request.topic}")
        
        debate_state = debate_service.set_topic(session_id, request.topic)
        
        # Update database
        await db.debate_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "topic": debate_state.topic,
                "updated_at": debate_state.updated_at
            }}
        )
        
        # IMPORTANT: Also update the room's current_topic so all participants see the same topic
        try:
            # Find the room associated with this session
            # First check if this is a debate session
            debate_session_data = await db.debate_sessions.find_one({"session_id": session_id})
            session_data = None
            
            if debate_session_data and debate_session_data.get("room_id"):
                # Direct room_id from debate session
                room_id = debate_session_data["room_id"]
                logger.info(f"📝 Found room {room_id} from debate session")
            else:
                # Fallback: look in general sessions collection
                session_data = await db.sessions.find_one({"id": session_id})
                if session_data and session_data.get("room_id"):
                    room_id = session_data["room_id"]
                    logger.info(f"📝 Found room {room_id} from general session")
                else:
                    logger.warning(f"⚠️ Could not find room for session {session_id} in either collection")
                    room_id = None
            
            if room_id:
                logger.info(f"📝 Updating room {room_id} with topic: {request.topic}")
                
                await db.rooms.update_one(
                    {"id": room_id},
                    {"$set": {"current_topic": request.topic}}
                )
                logger.info(f"✅ Room topic updated successfully")
                
                # Also store the room_id in the debate session if not already there
                if not debate_session_data or not debate_session_data.get("room_id"):
                    await db.debate_sessions.update_one(
                        {"session_id": session_id},
                        {"$set": {"room_id": room_id}}
                    )
                    logger.info(f"✅ Added room_id to debate session")
            else:
                logger.warning(f"⚠️ Could not find room for session {session_id}")
        except Exception as room_error:
            logger.error(f"❌ Failed to update room topic: {room_error}")
            # Don't fail the whole request if room update fails
        
        return {
            "success": True,
            "topic": debate_state.topic,
            "debate_state": debate_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set topic: {str(e)}")


@router.post("/debates/{session_id}/stances")
async def set_debate_stances(
    session_id: str,
    request: SetStancesRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Set the stances for both participants"""
    try:
        debate_state = await debate_service.set_stances(
            session_id,
            request.participant1_stance,
            request.participant2_stance
        )
        
        # Update database
        await db.debate_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "participant1_stance": debate_state.participant1_stance,
                "participant2_stance": debate_state.participant2_stance,
                "phase": debate_state.phase,
                "current_round": debate_state.current_round,
                "current_speaker_id": debate_state.current_speaker_id,
                "updated_at": debate_state.updated_at
            }}
        )
        
        # Check if AI should speak first and generate argument
        if debate_state.current_speaker_id == debate_state.participant2_id:
            # AI should speak first, generate argument
            ai_argument = await debate_service.generate_ai_argument(session_id)
            if ai_argument:
                # Add AI argument to debate
                debate_state = debate_service.add_argument(
                    session_id,
                    debate_state.participant2_id,
                    debate_state.participant2_name,
                    ai_argument
                )
                
                # Update database with AI argument
                await db.debate_sessions.update_one(
                    {"session_id": session_id},
                    {"$set": {
                        "arguments": [arg.model_dump() for arg in debate_state.arguments],
                        "phase": debate_state.phase,
                        "current_round": debate_state.current_round,
                        "current_speaker_id": debate_state.current_speaker_id,
                        "updated_at": debate_state.updated_at
                    }}
                )
        
        return {
            "success": True,
            "debate_state": debate_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set stances: {str(e)}")


@router.post("/debates/{session_id}/arguments")
async def add_debate_argument(
    session_id: str,
    request: AddArgumentRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Add an argument to the debate"""
    try:
        debate_state = debate_service.add_argument(
            session_id,
            request.participant_id,
            request.participant_name,
            request.argument_text
        )
        
        # Update database
        await db.debate_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "arguments": [arg.model_dump() for arg in debate_state.arguments],
                "phase": debate_state.phase,
                "current_round": debate_state.current_round,
                "current_speaker_id": debate_state.current_speaker_id,
                "updated_at": debate_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "debate_state": debate_state.model_dump(),
            "next_speaker": debate_service.get_next_speaker(session_id)
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add argument: {str(e)}")


@router.post("/debates/{session_id}/judgment")
async def submit_debate_judgment(
    session_id: str,
    request: SubmitJudgmentRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Submit the final judgment for the debate"""
    try:
        debate_state = debate_service.submit_judgment(
            session_id,
            request.winner_id,
            request.winner_name,
            request.verdict_summary,
            request.user_performance,
            request.ai_performance,
            request.key_moment,
            request.scores
        )
        
        # Update database
        await db.debate_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "judgment": debate_state.judgment.model_dump() if debate_state.judgment else None,
                "phase": debate_state.phase,
                "updated_at": debate_state.updated_at
            }}
        )
        
        return {
            "success": True,
            "judgment": debate_state.judgment.model_dump() if debate_state.judgment else None,
            "debate_state": debate_state.model_dump()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit judgment: {str(e)}")


@router.get("/debates/{session_id}")
async def get_debate_state(session_id: str):
    """Get the current state of a debate"""
    try:
        debate_state = debate_service.get_debate_state(session_id)
        
        if not debate_state:
            raise HTTPException(status_code=404, detail="Debate session not found")
        
        return {
            "success": True,
            "debate_state": debate_state.model_dump()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get debate state: {str(e)}")


@router.get("/debates/{session_id}/summary")
async def get_debate_summary(session_id: str):
    """Get a summary of the debate"""
    try:
        summary = debate_service.get_debate_summary(session_id)
        
        if not summary:
            raise HTTPException(status_code=404, detail="Debate session not found")
        
        return {
            "success": True,
            "summary": summary
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get debate summary: {str(e)}")


@router.get("/debates/{session_id}/next-speaker")
async def get_next_speaker(session_id: str):
    """Get the next speaker in the debate"""
    try:
        next_speaker = debate_service.get_next_speaker(session_id)
        
        if not next_speaker:
            return {
                "success": True,
                "next_speaker": None,
                "message": "No next speaker (debate may be complete or not started)"
            }
        
        return {
            "success": True,
            "next_speaker": next_speaker
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get next speaker: {str(e)}")


@router.delete("/debates/{session_id}")
async def end_debate(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """End and cleanup a debate session"""
    try:
        debate_service.end_debate(session_id)
        
        # Mark as completed in database
        await db.debate_sessions.update_one(
            {"session_id": session_id},
            {"$set": {
                "ended_at": datetime.utcnow()
            }}
        )
        
        return {
            "success": True,
            "message": "Debate ended successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to end debate: {str(e)}")
