# AI Integration Documentation

## Overview

This document describes the AI integration implementation for the BreakThrough application, including Gemini API and ElevenLabs Voice Agent integration.

## Components

### 1. Gemini API Integration (`ai_service.py`)

The Gemini API integration provides text-based AI responses with the following features:

#### Features
- **Rate Limiting**: Automatic rate limiting (60 requests per minute by default)
- **Retry Logic**: Exponential backoff retry mechanism for transient failures
- **Error Handling**: Comprehensive error handling for API failures
- **Secure Credentials**: Environment-based API key management
- **Mode-Specific Personalities**: Different AI personalities for each coaching mode

#### Usage Example
```python
from app.services.ai_service import AIService

ai_service = AIService()

response = await ai_service.generate_response(
    prompt="Help me improve my public speaking",
    context="User is practicing for a presentation",
    mode="general"
)

print(response["text"])
```

#### Configuration
Set the following environment variable:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
```

### 2. ElevenLabs Voice Agent Integration (`elevenlabs_service.py`)

The ElevenLabs integration provides natural voice conversations with the following features:

#### Features
- **Conversation Management**: Create and manage voice agent conversations
- **Real-time Audio Streaming**: Bidirectional audio streaming
- **Interruption Handling**: Support for interrupting agent speech
- **Turn-Taking**: Automatic and manual turn-taking modes
- **Context Management**: Maintain conversation history and context
- **Voice Personality Configuration**: Mode-specific voice characteristics

#### Usage Example
```python
from app.services.elevenlabs_service import ElevenLabsVoiceService

voice_service = ElevenLabsVoiceService()

# Create conversation
result = await voice_service.create_conversation(
    agent_id="agent_id",
    session_id="session_123",
    mode="debate"
)

conversation_id = result["conversation_id"]

# Stream audio to agent
await voice_service.stream_audio_to_agent(
    conversation_id=conversation_id,
    audio_data=audio_bytes
)

# Get agent response
async for chunk in voice_service.stream_agent_response(conversation_id):
    # Process audio chunk
    pass
```

#### Configuration
Set the following environment variables:
```bash
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Optional: Configure specific agent IDs for each mode
ELEVENLABS_AGENT_JAM=
ELEVENLABS_AGENT_DEBATE=
ELEVENLABS_AGENT_DISCUSSION=
ELEVENLABS_AGENT_READING=
ELEVENLABS_AGENT_INTERVIEW=
ELEVENLABS_AGENT_BUSINESS=
ELEVENLABS_AGENT_THERAPY=
ELEVENLABS_AGENT_SOCIAL=
ELEVENLABS_AGENT_GENERAL=
```

### 3. AI Personalities (`ai_personalities.py`)

Defines mode-specific AI personalities with system prompts migrated from the original Streamlit application.

#### Available Modes
- **JAM**: Just-A-Minute practice with mistake detection
- **Debate**: Structured debate with AI judge
- **Group Discussion**: Facilitated group discussions
- **Reading**: Pronunciation and reading practice
- **Interview**: Professional interview practice
- **Business Talks**: Business communication scenarios
- **Therapy**: Supportive therapeutic conversations
- **Socialising**: Social confidence building
- **General**: General speech coaching

#### Usage Example
```python
from app.services.ai_personalities import get_personality, get_system_prompt

# Get full personality configuration
personality = get_personality("debate")
print(personality["name"])  # "Debate Judge"
print(personality["tone"])  # "formal and analytical"

# Get just the system prompt
prompt = get_system_prompt("jam")
```

### 4. Voice Personality Configuration (`voice_personality_config.py`)

Configures voice characteristics for ElevenLabs agents including tone, pace, emotion, and coaching behaviors.

#### Voice Characteristics
Each personality type has specific voice settings:
- **Stability**: Voice consistency (0.0-1.0)
- **Similarity Boost**: Voice similarity to original (0.0-1.0)
- **Style**: Style exaggeration (0.0-1.0)
- **Tone**: Voice tone (e.g., "enthusiastic", "formal", "warm")
- **Pace**: Speaking pace (e.g., "moderate-fast", "measured")
- **Emotion**: Emotional quality (e.g., "encouraging", "neutral-serious")

#### Usage Example
```python
from app.services.voice_personality_config import get_voice_settings_for_mode

settings = get_voice_settings_for_mode("debate")
print(settings["voice_characteristics"]["tone"])  # "formal"
print(settings["coaching_behaviors"]["rounds"])  # 6
```

### 5. Voice Audio Processor (`voice_audio_processor.py`)

Handles audio processing for voice agent integration including:

#### Features
- **Noise Reduction**: Spectral gating for background noise removal
- **Audio Normalization**: Level normalization for consistent volume
- **Quality Enhancement**: Dynamic range compression and filtering
- **Format Conversion**: Convert between audio formats (WAV, MP3, etc.)
- **Real-time Streaming**: Chunk-based audio streaming

#### Usage Example
```python
from app.services.voice_audio_processor import VoiceAudioProcessor

processor = VoiceAudioProcessor()

# Process input audio
processed = await processor.process_input_audio(
    audio_data=raw_audio,
    source_format="wav",
    apply_noise_reduction=True,
    normalize=True
)

# Get audio information
info = processor.get_audio_info(audio_data)
print(f"Duration: {info['duration_seconds']}s")
```

## API Endpoints

### AI Endpoints (`/api/ai`)

#### Generate AI Response
```http
POST /api/ai/generate
Content-Type: application/json

{
  "prompt": "Help me with my speech",
  "context": "User is nervous about presentation",
  "mode": "general",
  "participant_id": "user_123",
  "session_id": "session_456"
}
```

#### Generate Host Response
```http
POST /api/ai/host-response
Content-Type: application/json

{
  "room_mode": "debate",
  "current_topic": "Climate change policy",
  "conversation_history": ["Previous message 1", "Previous message 2"],
  "participant_count": 2,
  "session_id": "session_456"
}
```

#### List Available Modes
```http
GET /api/ai/modes
```

#### Get Mode Personality
```http
GET /api/ai/modes/{mode}
```

### Voice Agent Endpoints (`/api/voice-agent`)

#### Create Conversation
```http
POST /api/voice-agent/conversations
Content-Type: application/json

{
  "session_id": "session_123",
  "mode": "debate",
  "agent_id": "optional_agent_id"
}
```

#### Stream Audio to Agent
```http
POST /api/voice-agent/conversations/{conversation_id}/audio
Content-Type: multipart/form-data

audio: <audio_file>
apply_processing: true
```

#### Get Agent Audio Stream
```http
GET /api/voice-agent/conversations/{conversation_id}/audio-stream
```

#### Interrupt Agent
```http
POST /api/voice-agent/conversations/{conversation_id}/interrupt
```

#### Add to Conversation Context
```http
POST /api/voice-agent/conversations/{conversation_id}/context
Content-Type: application/json

{
  "role": "user",
  "content": "Hello, I'm ready to practice"
}
```

#### Get Conversation Context
```http
GET /api/voice-agent/conversations/{conversation_id}/context?limit=10
```

#### Set Turn-Taking Mode
```http
PATCH /api/voice-agent/conversations/{conversation_id}/turn-taking
Content-Type: application/json

{
  "mode": "automatic"  // or "manual"
}
```

#### Signal Turn Complete
```http
POST /api/voice-agent/conversations/{conversation_id}/turn-complete
```

#### End Conversation
```http
DELETE /api/voice-agent/conversations/{conversation_id}
```

#### List Voice Personalities
```http
GET /api/voice-agent/personalities
```

#### Get Voice Settings for Mode
```http
GET /api/voice-agent/personalities/mode/{mode}
```

#### Process Audio
```http
POST /api/voice-agent/audio/process
Content-Type: multipart/form-data

audio: <audio_file>
apply_noise_reduction: true
normalize: true
enhance_quality: true
```

#### Convert Audio Format
```http
POST /api/voice-agent/audio/convert
Content-Type: multipart/form-data

audio: <audio_file>
target_format: wav
```

#### Get Audio Information
```http
POST /api/voice-agent/audio/info
Content-Type: multipart/form-data

audio: <audio_file>
```

## Error Handling

### Gemini API Errors
- **Rate Limiting**: Automatically handled with exponential backoff
- **Network Errors**: Retried up to 3 times
- **Authentication Errors**: Logged and returned to user
- **API Unavailable**: Graceful fallback with error message

### ElevenLabs Errors
- **Connection Errors**: Logged and returned with error details
- **Invalid Conversation**: 404 error with clear message
- **Streaming Errors**: Handled gracefully with partial results

## Testing

To test the AI integration:

1. **Set up environment variables**:
   ```bash
   cp backend/.env.example backend/.env
   # Edit .env with your API keys
   ```

2. **Test Gemini API**:
   ```bash
   curl -X POST http://localhost:8000/api/ai/generate \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Hello", "mode": "general"}'
   ```

3. **Test ElevenLabs Voice Agent**:
   ```bash
   # Create conversation
   curl -X POST http://localhost:8000/api/voice-agent/conversations \
     -H "Content-Type: application/json" \
     -d '{"session_id": "test_123", "mode": "general"}'
   ```

## Performance Considerations

### Gemini API
- Rate limit: 60 requests per minute (configurable)
- Average response time: 1-3 seconds
- Retry delay: Exponential backoff (1s, 2s, 4s)

### ElevenLabs Voice Agent
- Audio streaming: Real-time with minimal latency
- Chunk size: 4096 bytes (configurable)
- Sample rate: 16kHz for voice optimization

### Audio Processing
- Noise reduction: ~100-200ms overhead
- Format conversion: ~50-100ms overhead
- Normalization: ~10-20ms overhead

## Security

- API keys stored in environment variables
- No API keys logged or exposed in responses
- Secure credential validation on startup
- Rate limiting to prevent abuse
- Input validation on all endpoints

## Future Enhancements

1. **Caching**: Implement response caching for common queries
2. **Metrics**: Add detailed performance metrics and monitoring
3. **Advanced Audio Processing**: More sophisticated noise reduction algorithms
4. **Multi-language Support**: Support for multiple languages in voice agents
5. **Custom Voice Training**: Support for custom voice models
6. **Conversation Analytics**: Track and analyze conversation patterns
