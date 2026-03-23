from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.core.database import get_database
from app.services.elevenlabs_service import ElevenLabsVoiceService
from app.services.voice_audio_processor import VoiceAudioProcessor
from app.services.voice_personality_config import (
    get_voice_settings_for_mode,
    get_all_voice_personalities
)
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter()

class CreateConversationRequest(BaseModel):
    session_id: str
    mode: str = "general"
    agent_id: Optional[str] = None

class SendTextRequest(BaseModel):
    conversation_id: str
    text: str

class EndConversationRequest(BaseModel):
    conversation_id: str

@router.post("/conversations")
async def create_conversation(
    request: CreateConversationRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Create a new voice agent conversation"""
    try:
        voice_service = ElevenLabsVoiceService()
        
        # Get agent ID for mode if not provided
        agent_id = request.agent_id or voice_service.get_agent_for_mode(request.mode)
        
        # Create conversation
        result = await voice_service.create_conversation(
            agent_id=agent_id,
            session_id=request.session_id,
            mode=request.mode
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to create conversation"))
        
        # Store conversation in database
        conversation_doc = {
            "conversation_id": result["conversation_id"],
            "session_id": request.session_id,
            "agent_id": agent_id,
            "mode": request.mode,
            "created_at": datetime.utcnow(),
            "status": "active"
        }
        
        await db.voice_conversations.insert_one(conversation_doc)
        
        return {
            "conversation_id": result["conversation_id"],
            "agent_id": agent_id,
            "session_id": request.session_id,
            "mode": request.mode,
            "status": "active",
            "created_at": conversation_doc["created_at"]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create conversation: {str(e)}")

@router.post("/conversations/{conversation_id}/audio")
async def stream_audio_to_agent(
    conversation_id: str,
    audio: UploadFile = File(...),
    apply_processing: bool = True
):
    """Stream audio to voice agent with optional processing"""
    try:
        voice_service = ElevenLabsVoiceService()
        audio_processor = VoiceAudioProcessor()
        
        # Read audio data
        audio_data = await audio.read()
        
        # Process audio if requested
        if apply_processing:
            audio_data = await audio_processor.process_input_audio(
                audio_data,
                source_format=audio.content_type.split('/')[-1] if audio.content_type else "wav",
                apply_noise_reduction=True,
                normalize=True
            )
        
        # Stream to agent
        result = await voice_service.stream_audio_to_agent(
            conversation_id=conversation_id,
            audio_data=audio_data
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to stream audio"))
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "processed": apply_processing,
            "timestamp": datetime.utcnow()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stream audio: {str(e)}")

@router.get("/conversations/{conversation_id}/audio-stream")
async def get_agent_audio_stream(conversation_id: str):
    """Get streaming audio response from voice agent"""
    try:
        voice_service = ElevenLabsVoiceService()
        
        async def audio_generator():
            async for chunk in voice_service.stream_agent_response(conversation_id):
                yield chunk
        
        return StreamingResponse(
            audio_generator(),
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stream audio: {str(e)}")

@router.post("/conversations/{conversation_id}/text")
async def send_text_to_agent(
    conversation_id: str,
    request: SendTextRequest
):
    """Send text message to voice agent"""
    try:
        voice_service = ElevenLabsVoiceService()
        
        result = await voice_service.send_text_to_agent(
            conversation_id=conversation_id,
            text=request.text
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to send text"))
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "response": result.get("response", ""),
            "timestamp": datetime.utcnow()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send text: {str(e)}")

@router.delete("/conversations/{conversation_id}")
async def end_conversation(
    conversation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """End a voice agent conversation"""
    try:
        voice_service = ElevenLabsVoiceService()
        
        result = await voice_service.end_conversation(conversation_id)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to end conversation"))
        
        # Update database
        await db.voice_conversations.update_one(
            {"conversation_id": conversation_id},
            {
                "$set": {
                    "status": "ended",
                    "ended_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "ended_at": datetime.utcnow()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to end conversation: {str(e)}")

@router.get("/conversations/{conversation_id}/status")
async def get_conversation_status(
    conversation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get conversation status"""
    try:
        # Get from database
        conversation = await db.voice_conversations.find_one({"conversation_id": conversation_id})
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {
            "conversation_id": conversation["conversation_id"],
            "session_id": conversation["session_id"],
            "agent_id": conversation["agent_id"],
            "mode": conversation["mode"],
            "status": conversation["status"],
            "created_at": conversation["created_at"],
            "ended_at": conversation.get("ended_at")
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")

@router.get("/agents")
async def list_available_agents():
    """List available voice agents"""
    try:
        voice_service = ElevenLabsVoiceService()
        
        result = await voice_service.list_available_agents()
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to list agents"))
        
        return {
            "agents": result["agents"],
            "timestamp": datetime.utcnow()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list agents: {str(e)}")

@router.get("/agents/mode/{mode}")
async def get_agent_for_mode(mode: str):
    """Get the appropriate agent for a specific mode"""
    try:
        voice_service = ElevenLabsVoiceService()
        agent_id = voice_service.get_agent_for_mode(mode)
        
        return {
            "mode": mode,
            "agent_id": agent_id,
            "timestamp": datetime.utcnow()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get agent: {str(e)}")

@router.post("/conversations/{conversation_id}/interrupt")
async def interrupt_conversation(conversation_id: str):
    """Interrupt the voice agent's current speech"""
    try:
        voice_service = ElevenLabsVoiceService()
        
        result = await voice_service.interrupt_agent(conversation_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to interrupt"))
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to interrupt: {str(e)}")

@router.post("/conversations/{conversation_id}/context")
async def add_to_context(
    conversation_id: str,
    role: str,
    content: str
):
    """Add a message to the conversation context"""
    try:
        voice_service = ElevenLabsVoiceService()
        
        result = await voice_service.add_to_conversation_context(
            conversation_id=conversation_id,
            role=role,
            content=content
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to add to context"))
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add to context: {str(e)}")

@router.get("/conversations/{conversation_id}/context")
async def get_context(
    conversation_id: str,
    limit: Optional[int] = None
):
    """Get the conversation context/history"""
    try:
        voice_service = ElevenLabsVoiceService()
        
        result = await voice_service.get_conversation_context(
            conversation_id=conversation_id,
            limit=limit
        )
        
        if not result["success"]:
            raise HTTPException(status_code=404, detail=result.get("error", "Conversation not found"))
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get context: {str(e)}")

@router.patch("/conversations/{conversation_id}/turn-taking")
async def set_turn_taking(
    conversation_id: str,
    mode: str = "automatic"
):
    """Set the turn-taking mode for the conversation"""
    try:
        voice_service = ElevenLabsVoiceService()
        
        result = await voice_service.set_turn_taking_mode(
            conversation_id=conversation_id,
            mode=mode
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to set turn-taking mode"))
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set turn-taking: {str(e)}")

@router.post("/conversations/{conversation_id}/turn-complete")
async def signal_turn_complete(conversation_id: str):
    """Signal that the user has completed their turn"""
    try:
        voice_service = ElevenLabsVoiceService()
        
        result = await voice_service.signal_user_turn_complete(conversation_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to signal turn complete"))
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to signal turn complete: {str(e)}")

@router.get("/personalities")
async def list_voice_personalities():
    """List all available voice personalities"""
    try:
        personalities = get_all_voice_personalities()
        
        return {
            "personalities": personalities,
            "total": len(personalities),
            "timestamp": datetime.utcnow()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list personalities: {str(e)}")

@router.get("/personalities/mode/{mode}")
async def get_mode_voice_settings(mode: str):
    """Get complete voice settings for a specific mode"""
    try:
        settings = get_voice_settings_for_mode(mode)
        
        return {
            "mode": mode,
            "settings": settings,
            "timestamp": datetime.utcnow()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get voice settings: {str(e)}")

@router.post("/audio/process")
async def process_audio(
    audio: UploadFile = File(...),
    apply_noise_reduction: bool = True,
    normalize: bool = True,
    enhance_quality: bool = True
):
    """Process audio with noise reduction, normalization, and quality enhancement"""
    try:
        audio_processor = VoiceAudioProcessor()
        
        # Read audio data
        audio_data = await audio.read()
        
        # Process audio
        processed_audio = await audio_processor.process_input_audio(
            audio_data,
            source_format=audio.content_type.split('/')[-1] if audio.content_type else "wav",
            apply_noise_reduction=apply_noise_reduction,
            normalize=normalize
        )
        
        # Get audio info
        audio_info = audio_processor.get_audio_info(processed_audio)
        
        return {
            "success": True,
            "audio_info": audio_info,
            "processing_applied": {
                "noise_reduction": apply_noise_reduction,
                "normalization": normalize,
                "quality_enhancement": enhance_quality
            },
            "timestamp": datetime.utcnow()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process audio: {str(e)}")

@router.post("/audio/convert")
async def convert_audio_format(
    audio: UploadFile = File(...),
    target_format: str = "wav"
):
    """Convert audio from one format to another"""
    try:
        audio_processor = VoiceAudioProcessor()
        
        # Read audio data
        audio_data = await audio.read()
        source_format = audio.content_type.split('/')[-1] if audio.content_type else "wav"
        
        # Convert format
        converted_audio = audio_processor.convert_format(
            audio_data,
            source_format=source_format,
            target_format=target_format
        )
        
        # Return as streaming response
        return StreamingResponse(
            iter([converted_audio]),
            media_type=f"audio/{target_format}",
            headers={
                "Content-Disposition": f"attachment; filename=converted.{target_format}"
            }
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to convert audio: {str(e)}")

@router.post("/audio/info")
async def get_audio_information(audio: UploadFile = File(...)):
    """Get information about an audio file"""
    try:
        audio_processor = VoiceAudioProcessor()
        
        # Read audio data
        audio_data = await audio.read()
        
        # Get audio info
        audio_info = audio_processor.get_audio_info(audio_data)
        
        return {
            "success": True,
            "audio_info": audio_info,
            "filename": audio.filename,
            "content_type": audio.content_type,
            "timestamp": datetime.utcnow()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get audio info: {str(e)}")
