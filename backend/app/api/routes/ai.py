from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime

from app.core.database import get_database
from app.services.ai_service import AIService
from app.services.ai_personalities import list_available_modes, get_personality
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter()

class GenerateRequest(BaseModel):
    prompt: str
    context: Optional[str] = None
    mode: Optional[str] = "general"
    participant_id: Optional[str] = None
    session_id: Optional[str] = None

class HostResponseRequest(BaseModel):
    room_mode: str
    current_topic: Optional[str] = None
    conversation_history: List[str] = []
    participant_count: int = 1
    session_id: Optional[str] = None

@router.post("/generate")
async def generate_response(
    request: GenerateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Generate AI response using Gemini API"""
    try:
        # Initialize AI service
        ai_service = AIService()
        
        # Generate response
        response = await ai_service.generate_response(
            prompt=request.prompt,
            context=request.context,
            mode=request.mode
        )
        
        return {
            "response": response["text"],
            "model": response.get("model", "gemini"),
            "tokens_used": response.get("tokens_used", 0),
            "response_time": response.get("response_time", 0),
            "participant_id": request.participant_id,
            "session_id": request.session_id,
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

@router.post("/host-response")
async def generate_host_response(
    request: HostResponseRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Generate AI host response based on room mode and context"""
    try:
        # Initialize AI service
        ai_service = AIService()
        
        # Generate contextual host response
        response = await ai_service.generate_host_response(
            room_mode=request.room_mode,
            current_topic=request.current_topic,
            conversation_history=request.conversation_history,
            participant_count=request.participant_count
        )
        
        # Store AI interaction if session_id provided
        if request.session_id:
            interaction = {
                "id": str(uuid.uuid4()),
                "session_id": request.session_id,
                "participant_id": "ai_host",
                "prompt": f"Host response for {request.room_mode} mode",
                "response": response["text"],
                "timestamp": datetime.utcnow(),
                "response_time": response.get("response_time", 0)
            }
            
            await db.sessions.update_one(
                {"id": request.session_id},
                {"$push": {"ai_interactions": interaction}}
            )
        
        return {
            "response": response["text"],
            "host_type": f"{request.room_mode}_host",
            "model": response.get("model", "gemini"),
            "response_time": response.get("response_time", 0),
            "session_id": request.session_id,
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Host response generation failed: {str(e)}")

@router.get("/models")
async def list_available_models():
    """List available AI models"""
    return {
        "models": [
            {
                "name": "gemini-pro",
                "description": "Google Gemini Pro model for text generation",
                "capabilities": ["text_generation", "conversation", "analysis"]
            }
        ],
        "default_model": "gemini-pro"
    }

@router.get("/usage/{session_id}")
async def get_ai_usage(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get AI usage statistics for a session"""
    session_data = await db.sessions.find_one({"id": session_id})
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    
    ai_interactions = session_data.get("ai_interactions", [])
    
    total_interactions = len(ai_interactions)
    total_response_time = sum(interaction.get("response_time", 0) for interaction in ai_interactions)
    average_response_time = total_response_time / total_interactions if total_interactions > 0 else 0
    
    return {
        "session_id": session_id,
        "total_interactions": total_interactions,
        "total_response_time": total_response_time,
        "average_response_time": average_response_time,
        "interactions": ai_interactions
    }

@router.get("/modes")
async def list_coaching_modes():
    """List all available coaching modes with their AI personalities"""
    return {
        "modes": list_available_modes(),
        "total_modes": len(list_available_modes())
    }

@router.get("/modes/{mode}")
async def get_mode_personality(mode: str):
    """Get the AI personality configuration for a specific mode"""
    try:
        personality = get_personality(mode)
        return {
            "mode": mode,
            "personality": personality
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Mode not found: {str(e)}")