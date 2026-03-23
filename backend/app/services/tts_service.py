"""  """"""
Text-to-Speech service with ElevenLabs and Google TTS fallback
"""

import logging
from typing import Optional
import io

from app.core.config import settings

logger = logging.getLogger(__name__)


class TTSService:
    def __init__(self):
        self.elevenlabs_available = False
        self.google_tts_available = False
        self.elevenlabs_client = None
        self._initialize_services()
    
    def _initialize_services(self):
        """Initialize available TTS services"""
        # Try ElevenLabs
        try:
            if settings.ELEVENLABS_API_KEY and settings.ELEVENLABS_API_KEY != "your_elevenlabs_api_key_here":
                import elevenlabs
                # Set the API key for the elevenlabs module
                elevenlabs.set_api_key(settings.ELEVENLABS_API_KEY)
                self.elevenlabs_available = True
                logger.info("ElevenLabs TTS initialized successfully")
        except Exception as e:
            logger.warning(f"ElevenLabs TTS not available: {e}")
        
        # Try Google TTS
        try:
            from gtts import gTTS
            self.google_tts_available = True
            logger.info("Google TTS initialized successfully")
        except Exception as e:
            logger.warning(f"Google TTS not available: {e}")
    
    async def text_to_speech(self, text: str, voice: str = "default") -> Optional[bytes]:
        """
        Convert text to speech using available TTS service
        
        Args:
            text: Text to convert to speech
            voice: Voice identifier (for ElevenLabs)
        
        Returns:
            Audio bytes or None if all services fail
        """
        # Try ElevenLabs first
        if self.elevenlabs_available:
            try:
                audio_bytes = await self._elevenlabs_tts(text, voice)
                if audio_bytes:
                    return audio_bytes
            except Exception as e:
                logger.error(f"ElevenLabs TTS failed: {e}")
        
        # Fallback to Google TTS
        if self.google_tts_available:
            try:
                audio_bytes = await self._google_tts(text)
                if audio_bytes:
                    return audio_bytes
            except Exception as e:
                logger.error(f"Google TTS failed: {e}")
        
        logger.error("All TTS services failed")
        return None
    
    async def elevenlabs_tts(self, text: str, voice: str = "default") -> Optional[bytes]:
        """Generate speech using ElevenLabs"""
        try:
            if not self.elevenlabs_available:
                logger.error("ElevenLabs not available")
                return None
            
            import elevenlabs
            
            # Use Sarah voice as default
            if voice == "default":
                voice = "EXAVITQu4vr4xnSDxMaL"  # Sarah - Mature, Reassuring, Confident
            
            # Generate audio using the v0.2.27 API
            audio_bytes = elevenlabs.generate(
                text=text,
                voice=voice,
                model="eleven_multilingual_v2"
            )
            
            return audio_bytes
            
        except Exception as e:
            logger.error(f"ElevenLabs TTS error: {e}")
            return None

    async def _elevenlabs_tts(self, text: str, voice: str = "default") -> Optional[bytes]:
        """Generate speech using ElevenLabs (internal method)"""
        return await self.elevenlabs_tts(text, voice)
    
    async def _google_tts(self, text: str, lang: str = "en") -> Optional[bytes]:
        """Generate speech using Google Cloud TTS with high-quality voices"""
        try:
            # Try Google Cloud TTS first (better quality)
            try:
                from google.cloud import texttospeech
                
                # Create client
                client = texttospeech.TextToSpeechClient()
                
                # Set the text input
                synthesis_input = texttospeech.SynthesisInput(text=text)
                
                # Build the voice request with high-quality neural female voice
                voice = texttospeech.VoiceSelectionParams(
                    language_code="en-US",
                    name="en-US-Neural2-F",  # High-quality female voice
                    ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
                )
                
                # Select the audio format
                audio_config = texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    speaking_rate=1.0,  # Normal speed
                    pitch=0.0,  # Normal pitch
                    volume_gain_db=0.0  # Normal volume
                )
                
                # Perform the text-to-speech request
                response = client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice,
                    audio_config=audio_config
                )
                
                logger.info("Using Google Cloud TTS (Neural2-F - Female)")
                return response.audio_content
                
            except Exception as cloud_error:
                logger.warning(f"Google Cloud TTS not available: {cloud_error}, falling back to gTTS")
                
                # Fallback to gTTS (free but lower quality)
                from gtts import gTTS
                
                # Create TTS object with better settings - gTTS doesn't have explicit gender control
                # but we can use different TLDs and languages that sound more feminine
                tts = gTTS(
                    text=text,
                    lang=lang,
                    slow=False,
                    tld='co.uk'  # UK accent tends to sound more pleasant
                )
                
                # Save to bytes buffer
                audio_buffer = io.BytesIO()
                tts.write_to_fp(audio_buffer)
                audio_buffer.seek(0)
                
                logger.info("Using gTTS (fallback - UK accent)")
                return audio_buffer.read()
            
        except Exception as e:
            logger.error(f"Google TTS error: {e}")
            return None
    
    def is_available(self) -> bool:
        """Check if any TTS service is available"""
        return self.elevenlabs_available or self.google_tts_available
    
    def get_available_service(self) -> str:
        """Get the name of the available TTS service"""
        if self.elevenlabs_available:
            return "ElevenLabs"
        elif self.google_tts_available:
            return "Google TTS"
        else:
            return "None"
