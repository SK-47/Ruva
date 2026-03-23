from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os

class Settings(BaseSettings):
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Ruva"
    
    # CORS
    ALLOWED_ORIGINS: str | List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    @property
    def cors_origins(self) -> List[str]:
        if isinstance(self.ALLOWED_ORIGINS, str):
            val = str(self.ALLOWED_ORIGINS)
            return [o.strip() for o in val.split(",") if o.strip()]
        return self.ALLOWED_ORIGINS  # type: ignore
    
    # Database
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "speech_app")
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # AI Services
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    
    # ElevenLabs Voice Agent IDs (optional - will use defaults if not set)
    ELEVENLABS_AGENT_JAM: str = os.getenv("ELEVENLABS_AGENT_JAM", "")
    ELEVENLABS_AGENT_DEBATE: str = os.getenv("ELEVENLABS_AGENT_DEBATE", "")
    ELEVENLABS_AGENT_DISCUSSION: str = os.getenv("ELEVENLABS_AGENT_DISCUSSION", "")
    ELEVENLABS_AGENT_READING: str = os.getenv("ELEVENLABS_AGENT_READING", "")
    ELEVENLABS_AGENT_INTERVIEW: str = os.getenv("ELEVENLABS_AGENT_INTERVIEW", "")
    ELEVENLABS_AGENT_BUSINESS: str = os.getenv("ELEVENLABS_AGENT_BUSINESS", "")
    ELEVENLABS_AGENT_THERAPY: str = os.getenv("ELEVENLABS_AGENT_THERAPY", "")
    ELEVENLABS_AGENT_SOCIAL: str = os.getenv("ELEVENLABS_AGENT_SOCIAL", "")
    ELEVENLABS_AGENT_GENERAL: str = os.getenv("ELEVENLABS_AGENT_GENERAL", "")
    
    # TURN Server
    TURN_URL: str = os.getenv("TURN_URL", "")
    TURN_USERNAME: str = os.getenv("TURN_USERNAME", "")
    TURN_CREDENTIAL: str = os.getenv("TURN_CREDENTIAL", "")
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
    SAMPLE_RATE: int = 16000
    
    # File Storage
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        extra='ignore'  # Ignore extra fields in .env file
    )

settings = Settings()