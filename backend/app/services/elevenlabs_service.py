import aiohttp
import asyncio
import logging
import json
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import datetime

from app.core.config import settings
from app.services.ai_personalities import get_voice_personality
from app.services.voice_personality_config import (
    get_voice_characteristics,
    get_voice_settings_for_mode,
    get_coaching_behaviors
)

logger = logging.getLogger(__name__)

class ElevenLabsVoiceService:
    """Service for ElevenLabs Voice Agent integration"""
    
    BASE_URL = "https://api.elevenlabs.io/v1"
    
    def __init__(self):
        self.api_key = settings.ELEVENLABS_API_KEY
        self.session: Optional[aiohttp.ClientSession] = None
        self.active_conversations: Dict[str, Dict[str, Any]] = {}
        self.conversation_contexts: Dict[str, list] = {}  # Store conversation history
        
        if not self.api_key or self.api_key == "your_elevenlabs_api_key_here":
            logger.warning("ElevenLabs API key not configured. Voice agent features will be unavailable.")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json"
                }
            )
        return self.session
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def create_conversation(
        self,
        agent_id: str,
        session_id: str,
        mode: str = "general"
    ) -> Dict[str, Any]:
        """Create a new voice agent conversation session with personality configuration"""
        if not self.api_key or self.api_key == "your_elevenlabs_api_key_here":
            return {
                "success": False,
                "error": "ElevenLabs API key not configured",
                "conversation_id": None
            }
        
        try:
            session = await self._get_session()
            
            # Get voice settings for this mode
            voice_settings = get_voice_settings_for_mode(mode)
            voice_characteristics = voice_settings["voice_characteristics"]
            
            # Create conversation with ElevenLabs including voice settings
            async with session.post(
                f"{self.BASE_URL}/convai/conversations",
                json={
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "voice_settings": {
                        "stability": voice_characteristics["stability"],
                        "similarity_boost": voice_characteristics["similarity_boost"],
                        "style": voice_characteristics.get("style", 0.5),
                        "use_speaker_boost": voice_characteristics.get("use_speaker_boost", True)
                    }
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    conversation_id = data.get("conversation_id")
                    
                    # Store conversation metadata with personality info
                    self.active_conversations[conversation_id] = {
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "mode": mode,
                        "created_at": datetime.utcnow(),
                        "status": "active",
                        "is_speaking": False,
                        "can_be_interrupted": True,
                        "personality_type": voice_settings["personality_type"],
                        "voice_characteristics": voice_characteristics,
                        "coaching_behaviors": voice_settings["coaching_behaviors"]
                    }
                    
                    # Initialize conversation context
                    self.conversation_contexts[conversation_id] = []
                    
                    logger.info(f"Created ElevenLabs conversation: {conversation_id} with {voice_settings['personality_type']} personality")
                    
                    return {
                        "success": True,
                        "conversation_id": conversation_id,
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "personality": voice_settings["personality_type"],
                        "voice_characteristics": voice_characteristics
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to create conversation: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"API error: {response.status}",
                        "conversation_id": None
                    }
        
        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            return {
                "success": False,
                "error": str(e),
                "conversation_id": None
            }
    
    async def stream_audio_to_agent(
        self,
        conversation_id: str,
        audio_data: bytes,
        audio_format: str = "pcm_16000"
    ) -> Dict[str, Any]:
        """Stream audio data to the voice agent"""
        if conversation_id not in self.active_conversations:
            return {
                "success": False,
                "error": "Conversation not found"
            }
        
        try:
            session = await self._get_session()
            
            # Send audio to ElevenLabs
            async with session.post(
                f"{self.BASE_URL}/convai/conversations/{conversation_id}/audio",
                data=audio_data,
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": f"audio/{audio_format}"
                }
            ) as response:
                if response.status == 200:
                    return {
                        "success": True,
                        "conversation_id": conversation_id
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to stream audio: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"API error: {response.status}"
                    }
        
        except Exception as e:
            logger.error(f"Error streaming audio: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def stream_agent_response(
        self,
        conversation_id: str
    ) -> AsyncGenerator[bytes, None]:
        """Stream voice agent response audio"""
        if conversation_id not in self.active_conversations:
            logger.error(f"Conversation {conversation_id} not found")
            return
        
        try:
            session = await self._get_session()
            
            # Stream response from ElevenLabs
            async with session.get(
                f"{self.BASE_URL}/convai/conversations/{conversation_id}/audio-stream"
            ) as response:
                if response.status == 200:
                    async for chunk in response.content.iter_chunked(4096):
                        yield chunk
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to stream response: {response.status} - {error_text}")
        
        except Exception as e:
            logger.error(f"Error streaming agent response: {e}")
    
    async def send_text_to_agent(
        self,
        conversation_id: str,
        text: str
    ) -> Dict[str, Any]:
        """Send text message to voice agent (for testing or text-based interaction)"""
        if conversation_id not in self.active_conversations:
            return {
                "success": False,
                "error": "Conversation not found"
            }
        
        try:
            session = await self._get_session()
            
            async with session.post(
                f"{self.BASE_URL}/convai/conversations/{conversation_id}/text",
                json={"text": text}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "response": data.get("response", ""),
                        "conversation_id": conversation_id
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to send text: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"API error: {response.status}"
                    }
        
        except Exception as e:
            logger.error(f"Error sending text: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def end_conversation(
        self,
        conversation_id: str
    ) -> Dict[str, Any]:
        """End a voice agent conversation"""
        if conversation_id not in self.active_conversations:
            return {
                "success": False,
                "error": "Conversation not found"
            }
        
        try:
            session = await self._get_session()
            
            async with session.delete(
                f"{self.BASE_URL}/convai/conversations/{conversation_id}"
            ) as response:
                if response.status in [200, 204]:
                    # Update conversation status
                    self.active_conversations[conversation_id]["status"] = "ended"
                    self.active_conversations[conversation_id]["ended_at"] = datetime.utcnow()
                    
                    logger.info(f"Ended conversation: {conversation_id}")
                    
                    return {
                        "success": True,
                        "conversation_id": conversation_id
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to end conversation: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"API error: {response.status}"
                    }
        
        except Exception as e:
            logger.error(f"Error ending conversation: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_conversation_status(
        self,
        conversation_id: str
    ) -> Dict[str, Any]:
        """Get the status of a conversation"""
        if conversation_id not in self.active_conversations:
            return {
                "success": False,
                "error": "Conversation not found"
            }
        
        return {
            "success": True,
            "conversation": self.active_conversations[conversation_id]
        }
    
    async def list_available_agents(self) -> Dict[str, Any]:
        """List available voice agents"""
        if not self.api_key or self.api_key == "your_elevenlabs_api_key_here":
            return {
                "success": False,
                "error": "ElevenLabs API key not configured",
                "agents": []
            }
        
        try:
            session = await self._get_session()
            
            async with session.get(f"{self.BASE_URL}/convai/agents") as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "agents": data.get("agents", [])
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to list agents: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"API error: {response.status}",
                        "agents": []
                    }
        
        except Exception as e:
            logger.error(f"Error listing agents: {e}")
            return {
                "success": False,
                "error": str(e),
                "agents": []
            }
    
    def get_agent_for_mode(self, mode: str) -> str:
        """Get the appropriate agent ID for a given mode"""
        # Get voice personality from AI personalities configuration
        voice_personality = get_voice_personality(mode)
        
        # Map voice personalities to ElevenLabs agent IDs
        # These would be configured based on actual ElevenLabs agent IDs
        # For now, return placeholder IDs that should be configured via environment variables
        agent_mapping = {
            "energetic_coach": settings.ELEVENLABS_AGENT_JAM or "jam_coach_agent_id",
            "authoritative_judge": settings.ELEVENLABS_AGENT_DEBATE or "debate_judge_agent_id",
            "warm_facilitator": settings.ELEVENLABS_AGENT_DISCUSSION or "discussion_facilitator_agent_id",
            "professional_coach": settings.ELEVENLABS_AGENT_READING or "reading_coach_agent_id",
            "professional_interviewer": settings.ELEVENLABS_AGENT_INTERVIEW or "interview_agent_id",
            "business_professional": settings.ELEVENLABS_AGENT_BUSINESS or "business_coach_agent_id",
            "calm_companion": settings.ELEVENLABS_AGENT_THERAPY or "therapy_companion_agent_id",
            "friendly_coach": settings.ELEVENLABS_AGENT_SOCIAL or "social_coach_agent_id",
            "neutral_coach": settings.ELEVENLABS_AGENT_GENERAL or "general_coach_agent_id"
        }
        
        return agent_mapping.get(voice_personality, agent_mapping["neutral_coach"])
    
    async def add_to_conversation_context(
        self,
        conversation_id: str,
        role: str,
        content: str
    ) -> Dict[str, Any]:
        """Add a message to the conversation context"""
        if conversation_id not in self.active_conversations:
            return {
                "success": False,
                "error": "Conversation not found"
            }
        
        if conversation_id not in self.conversation_contexts:
            self.conversation_contexts[conversation_id] = []
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow()
        }
        
        self.conversation_contexts[conversation_id].append(message)
        
        logger.info(f"Added {role} message to conversation {conversation_id}")
        
        return {
            "success": True,
            "message": message
        }
    
    async def get_conversation_context(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get the conversation context/history"""
        if conversation_id not in self.active_conversations:
            return {
                "success": False,
                "error": "Conversation not found",
                "context": []
            }
        
        context = self.conversation_contexts.get(conversation_id, [])
        
        if limit:
            context = context[-limit:]
        
        return {
            "success": True,
            "context": context,
            "total_messages": len(self.conversation_contexts.get(conversation_id, []))
        }
    
    async def interrupt_agent(
        self,
        conversation_id: str
    ) -> Dict[str, Any]:
        """Interrupt the voice agent's current speech"""
        if conversation_id not in self.active_conversations:
            return {
                "success": False,
                "error": "Conversation not found"
            }
        
        conversation = self.active_conversations[conversation_id]
        
        if not conversation.get("is_speaking", False):
            return {
                "success": False,
                "error": "Agent is not currently speaking"
            }
        
        if not conversation.get("can_be_interrupted", True):
            return {
                "success": False,
                "error": "Agent cannot be interrupted at this time"
            }
        
        try:
            session = await self._get_session()
            
            # Send interruption signal to ElevenLabs
            async with session.post(
                f"{self.BASE_URL}/convai/conversations/{conversation_id}/interrupt"
            ) as response:
                if response.status == 200:
                    # Update conversation state
                    self.active_conversations[conversation_id]["is_speaking"] = False
                    
                    logger.info(f"Interrupted conversation: {conversation_id}")
                    
                    return {
                        "success": True,
                        "conversation_id": conversation_id,
                        "interrupted_at": datetime.utcnow()
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to interrupt: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"API error: {response.status}"
                    }
        
        except Exception as e:
            logger.error(f"Error interrupting agent: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def set_turn_taking_mode(
        self,
        conversation_id: str,
        mode: str = "automatic"
    ) -> Dict[str, Any]:
        """
        Set the turn-taking mode for the conversation
        Modes: 'automatic' (agent decides when to speak), 'manual' (explicit turn control)
        """
        if conversation_id not in self.active_conversations:
            return {
                "success": False,
                "error": "Conversation not found"
            }
        
        valid_modes = ["automatic", "manual"]
        if mode not in valid_modes:
            return {
                "success": False,
                "error": f"Invalid mode. Must be one of: {valid_modes}"
            }
        
        try:
            session = await self._get_session()
            
            async with session.patch(
                f"{self.BASE_URL}/convai/conversations/{conversation_id}/settings",
                json={"turn_taking_mode": mode}
            ) as response:
                if response.status == 200:
                    self.active_conversations[conversation_id]["turn_taking_mode"] = mode
                    
                    logger.info(f"Set turn-taking mode to '{mode}' for conversation {conversation_id}")
                    
                    return {
                        "success": True,
                        "conversation_id": conversation_id,
                        "turn_taking_mode": mode
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to set turn-taking mode: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"API error: {response.status}"
                    }
        
        except Exception as e:
            logger.error(f"Error setting turn-taking mode: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def signal_user_turn_complete(
        self,
        conversation_id: str
    ) -> Dict[str, Any]:
        """Signal that the user has completed their turn (for manual turn-taking)"""
        if conversation_id not in self.active_conversations:
            return {
                "success": False,
                "error": "Conversation not found"
            }
        
        try:
            session = await self._get_session()
            
            async with session.post(
                f"{self.BASE_URL}/convai/conversations/{conversation_id}/turn-complete"
            ) as response:
                if response.status == 200:
                    logger.info(f"Signaled turn complete for conversation {conversation_id}")
                    
                    return {
                        "success": True,
                        "conversation_id": conversation_id,
                        "timestamp": datetime.utcnow()
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to signal turn complete: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"API error: {response.status}"
                    }
        
        except Exception as e:
            logger.error(f"Error signaling turn complete: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def update_agent_speaking_state(
        self,
        conversation_id: str,
        is_speaking: bool
    ) -> Dict[str, Any]:
        """Update the agent's speaking state"""
        if conversation_id not in self.active_conversations:
            return {
                "success": False,
                "error": "Conversation not found"
            }
        
        self.active_conversations[conversation_id]["is_speaking"] = is_speaking
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "is_speaking": is_speaking
        }
