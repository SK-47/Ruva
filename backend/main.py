from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import socketio
import uvicorn
from dotenv import load_dotenv
import os

from app.api.routes import rooms, sessions, speech, ai, voice_agent, reports, tts, auth
from app.api.routes.modes import debate, group_discussion, jam, reading
from app.core.config import settings
from app.core.database import init_db
from app.core.redis_client import init_redis
from app.websocket.socket_manager import sio

# Load environment variables
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await init_redis()
    yield
    # Shutdown
    pass

# Create FastAPI app
app = FastAPI(
    title="Ruva API",
    description="Ruva AI speech coaching application backend",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(rooms.router, prefix="/api/rooms", tags=["rooms"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(speech.router, prefix="/api/speech", tags=["speech"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(voice_agent.router, prefix="/api/voice-agent", tags=["voice-agent"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(tts.router, prefix="/api/tts", tags=["tts"])

# Include mode-specific routes
app.include_router(debate.router, prefix="/api/modes", tags=["debate-mode"])
app.include_router(group_discussion.router, prefix="/api/modes", tags=["group-discussion-mode"])
app.include_router(jam.router, prefix="/api/modes", tags=["jam-mode"])
app.include_router(reading.router, prefix="/api/modes", tags=["reading-mode"])

# Create Socket.IO app
socket_app = socketio.ASGIApp(sio, app)

@app.get("/")
async def root():
    return {"message": "SpeechApp API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "main:socket_app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )