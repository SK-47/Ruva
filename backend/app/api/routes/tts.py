"""
TTS API routes
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import logging

from app.services.tts_service import TTSService

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize TTS service
tts_service = TTSService()


class TTSRequest(BaseModel):
    text: str
    voice: str = "default"


class ElevenLabsRequest(BaseModel):
    text: str
    voice_id: str = "EXAVITQu4vr4xnSDxMaL"  # Sarah - Mature, Reassuring, Confident
    model_id: str = "eleven_multilingual_v2"


@router.post("/speak")
async def text_to_speech(request: TTSRequest):
    """
    Convert text to speech using available TTS service
    """
    try:
        if not tts_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="No TTS service available. Please configure ElevenLabs API key or install gTTS."
            )
        
        # Generate speech
        audio_bytes = await tts_service.text_to_speech(request.text, request.voice)
        
        if not audio_bytes:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate speech"
            )
        
        # Return audio as MP3
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=speech.mp3"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/elevenlabs")
async def elevenlabs_tts(request: ElevenLabsRequest):
    """
    Convert text to speech using ElevenLabs specifically
    """
    try:
        if not tts_service.elevenlabs_available:
            raise HTTPException(
                status_code=503,
                detail="ElevenLabs TTS not available. Please configure ElevenLabs API key."
            )
        
        # Generate speech using ElevenLabs
        audio_bytes = await tts_service.elevenlabs_tts(request.text, request.voice_id)
        
        if not audio_bytes:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate speech with ElevenLabs"
            )
        
        # Return audio as MP3
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=speech.mp3"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ElevenLabs TTS endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_tts():
    """
    Test TTS with a simple message
    """
    try:
        test_text = "Hello! This is a test of the ElevenLabs text-to-speech system. If you can hear this, the API is working correctly."
        
        if not tts_service.is_available():
            return {
                "success": False,
                "error": "No TTS service available",
                "status": {
                    "elevenlabs": tts_service.elevenlabs_available,
                    "google_tts": tts_service.google_tts_available
                }
            }
        
        # Try ElevenLabs first
        if tts_service.elevenlabs_available:
            audio_bytes = await tts_service.elevenlabs_tts(test_text, "EXAVITQu4vr4xnSDxMaL")  # Sarah voice
            if audio_bytes:
                return Response(
                    content=audio_bytes,
                    media_type="audio/mpeg",
                    headers={
                        "Content-Disposition": "inline; filename=test_speech.mp3",
                        "X-TTS-Service": "ElevenLabs"
                    }
                )
        
        # Fallback to generic TTS
        audio_bytes = await tts_service.text_to_speech(test_text, "default")
        if audio_bytes:
            return Response(
                content=audio_bytes,
                media_type="audio/mpeg",
                headers={
                    "Content-Disposition": "inline; filename=test_speech.mp3",
                    "X-TTS-Service": "Fallback"
                }
            )
        
        return {
            "success": False,
            "error": "Failed to generate test audio"
        }
        
    except Exception as e:
        logger.error(f"TTS test endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def tts_status():
    """
    Get TTS service status
    """
    return {
        "available": tts_service.is_available(),
        "service": tts_service.get_available_service(),
        "elevenlabs": tts_service.elevenlabs_available,
        "google_tts": tts_service.google_tts_available
    }
