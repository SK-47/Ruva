from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import List
import uuid
from datetime import datetime

from app.models.speech import SpeechAnalysis, TranscribeRequest, AnalyzeRequest
from app.core.database import get_database
from app.services.speech_service import SpeechService
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter()

@router.post("/transcribe")
async def transcribe_audio(
    audio_file: UploadFile = File(...),
    participant_id: str = None,
    session_id: str = None,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Transcribe audio to text"""
    if not audio_file.content_type.startswith('audio/'):
        raise HTTPException(status_code=400, detail="File must be audio format")
    
    try:
        # Read audio data
        audio_data = await audio_file.read()
        
        # Initialize speech service
        speech_service = SpeechService()
        
        # Transcribe audio
        transcript = await speech_service.transcribe_audio(audio_data)
        
        return {
            "transcript": transcript["text"],
            "confidence": transcript.get("confidence", 0.0),
            "participant_id": participant_id,
            "session_id": session_id,
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

@router.post("/analyze", response_model=SpeechAnalysis)
async def analyze_speech(
    audio_file: UploadFile = File(...),
    transcript: str = None,
    participant_id: str = None,
    session_id: str = None,
    include_body_language: bool = False,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Analyze speech for prosodic features and metrics"""
    if not audio_file.content_type.startswith('audio/'):
        raise HTTPException(status_code=400, detail="File must be audio format")
    
    try:
        # Read audio data
        audio_data = await audio_file.read()
        
        # Initialize speech service
        speech_service = SpeechService()
        
        # Perform comprehensive analysis
        analysis_result = await speech_service.analyze_speech(
            audio_data=audio_data,
            transcript=transcript,
            include_body_language=include_body_language
        )
        
        # Create speech analysis record
        analysis = SpeechAnalysis(
            id=str(uuid.uuid4()),
            session_id=session_id or "unknown",
            participant_id=participant_id or "unknown",
            transcript=transcript or analysis_result.get("transcript", ""),
            vad_segments=analysis_result.get("vad_segments", []),
            prosody_metrics=analysis_result["prosody_metrics"],
            body_language_analysis=analysis_result.get("body_language_analysis"),
            timestamp=datetime.utcnow()
        )
        
        # Store in database
        await db.speech_analysis.insert_one(analysis.model_dump())
        
        return analysis
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.get("/analysis/{session_id}", response_model=List[SpeechAnalysis])
async def get_session_analysis(
    session_id: str,
    participant_id: str = None,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get speech analysis for a session"""
    query = {"session_id": session_id}
    if participant_id:
        query["participant_id"] = participant_id
    
    analysis_data = await db.speech_analysis.find(query).sort("timestamp", 1).to_list(1000)
    
    return [SpeechAnalysis(**data) for data in analysis_data]

@router.get("/feedback/{analysis_id}")
async def get_ai_feedback(
    analysis_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get AI-generated feedback for speech analysis"""
    analysis_data = await db.speech_analysis.find_one({"id": analysis_id})
    if not analysis_data:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    analysis = SpeechAnalysis(**analysis_data)
    
    # TODO: Generate AI feedback using Gemini API
    # This will be implemented in a later task
    
    return {
        "analysis_id": analysis_id,
        "feedback": "AI feedback generation will be implemented in the AI integration task",
        "recommendations": [
            "Continue practicing to improve fluency",
            "Work on reducing filler words",
            "Maintain consistent speaking pace"
        ]
    }