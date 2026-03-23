from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List
from datetime import datetime
import uuid
import logging

from app.models.room import Room, CreateRoomRequest, JoinRoomRequest, RoomMode, Participant, DiscussionMode, ConnectionStatus
from app.core.database import get_database
from app.core.redis_client import get_redis
from app.core.config import settings
from app.services.ai_service import AIService
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)
router = APIRouter()
ai_service = AIService()

@router.get("/ice-config")
async def get_ice_config():
    """Return ICE server config for WebRTC"""
    ice_servers = [
        {"urls": "stun:stun.l.google.com:19302"},
        {"urls": "stun:stun1.l.google.com:19302"},
    ]
    if settings.TURN_URL and settings.TURN_USERNAME and settings.TURN_CREDENTIAL:
        ice_servers.append({
            "urls": settings.TURN_URL,
            "username": settings.TURN_USERNAME,
            "credential": settings.TURN_CREDENTIAL,
        })
    return {"iceServers": ice_servers}

@router.post("/", response_model=Room)
async def create_room(
    request: CreateRoomRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Create a new room"""
    room_id = str(uuid.uuid4())
    
    # Determine max participants based on mode
    if request.max_participants is None:
        if request.mode == RoomMode.DEBATE:
            max_participants = 10
        elif request.mode in [RoomMode.INTERVIEW, RoomMode.BUSINESS_TALKS, RoomMode.SOCIALISING]:
            max_participants = 4
        elif request.mode == RoomMode.JAM:
            max_participants = 10
        else:  # GROUP_DISCUSSION, READING
            max_participants = 10
    else:
        max_participants = request.max_participants
    
    topic = None
    if request.mode == RoomMode.DEBATE:
        topics = [
            "Social media does more harm than good",
            "Remote work is better than office work",
            "AI will create more jobs than it destroys",
            "Space exploration is worth the cost",
            "Universal basic income would solve poverty",
        ]
        import random
        topic = random.choice(topics)

    # Add AI player if enabled
    ai_participants = []
    if request.ai_player_enabled:
        ai_participant = Participant(
            id=f"ai_player_{room_id[:8]}",
            name="AI Contender" if request.mode == RoomMode.DEBATE else "AI Participant",
            is_ai=True,
            joined_at=datetime.utcnow(),
            connection_status=ConnectionStatus.CONNECTED,
            is_ready=True
        )
        ai_participants.append(ai_participant)

    room = Room(
        id=room_id,
        name=request.name,
        mode=request.mode,
        max_participants=max_participants,
        participants=ai_participants,
        ai_judge_enabled=request.ai_enabled and request.mode == RoomMode.DEBATE,
        ai_facilitator_enabled=request.ai_enabled and request.mode == RoomMode.GROUP_DISCUSSION,
        ai_player_enabled=request.ai_player_enabled,
        created_at=datetime.utcnow(),
        is_active=True,
        current_topic=topic
    )
    
    # Store in database
    await db.rooms.insert_one(room.model_dump())
    
    return room

@router.get("/{room_id}", response_model=Room)
async def get_room(
    room_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get room details"""
    logger.info(f"🔍 API: Getting room details for room_id: {room_id}")
    
    try:
        room_data = await db.rooms.find_one({"id": room_id})
        logger.info(f"📊 API: Database query result: {room_data is not None}")
        
        if not room_data:
            logger.warning(f"❌ API: Room {room_id} not found in database")
            # Let's also check what rooms exist
            all_rooms = await db.rooms.find({}).to_list(10)
            logger.info(f"📋 API: Available rooms in database: {[r.get('id', 'no-id') for r in all_rooms]}")
            raise HTTPException(status_code=404, detail="Room not found")
        
        logger.info(f"✅ API: Room {room_id} found successfully")
        return Room(**room_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Error retrieving room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/", response_model=List[Room])
async def list_rooms(
    active_only: bool = True,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """List all rooms"""
    query = {"is_active": True} if active_only else {}
    rooms_data = await db.rooms.find(query).to_list(100)
    
    return [Room(**room_data) for room_data in rooms_data]

@router.post("/{room_id}/join", response_model=Room)
async def join_room(
    room_id: str,
    request: JoinRoomRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    redis = Depends(get_redis)
):
    """Join a room"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = Room(**room_data)
    
    if not room.is_active:
        raise HTTPException(status_code=400, detail="Room is not active")
    
    if len(room.participants) >= room.max_participants:
        raise HTTPException(status_code=400, detail="Room is full")
    
    # Check if participant name is already taken
    if any(p.name == request.participant_name for p in room.participants):
        raise HTTPException(status_code=400, detail="Participant name already taken")
    
    # Create new participant
    participant = Participant(
        id=str(uuid.uuid4()),
        name=request.participant_name,
        joined_at=datetime.utcnow()
    )
    
    # Add participant to room
    room.participants.append(participant)
    
    # Update database
    await db.rooms.update_one(
        {"id": room_id},
        {"$set": {"participants": [p.model_dump() for p in room.participants]}}
    )
    
    # Update Redis cache - use mode='json' to serialize datetime objects
    await redis.set_room_state(room_id, room.model_dump(mode='json'))
    
    # Notify other participants via WebSocket (if needed immediately)
    # The actual broadcast is usually handled by the websocket service,
    # but we can trigger it here if the logic allows.
    
    return room

@router.delete("/{room_id}/leave")
async def leave_room_simple(
    room_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Leave a room (participant cleanup handled via WebSocket)"""
    return {"message": "Left room"}

@router.delete("/{room_id}/leave/{participant_id}")
async def leave_room(
    room_id: str,
    participant_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    redis = Depends(get_redis)
):
    """Leave a room"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = Room(**room_data)
    
    # Remove participant
    room.participants = [p for p in room.participants if p.id != participant_id]
    
    # Update database
    await db.rooms.update_one(
        {"id": room_id},
        {"$set": {"participants": [p.model_dump() for p in room.participants]}}
    )
    
    # Update Redis cache - use mode='json' to serialize datetime objects
    try:
        await redis.set_room_state(room_id, room.model_dump(mode='json'))
    except Exception as e:
        # Log the error but don't fail the request
        print(f"Warning: Failed to update Redis cache: {e}")
    
    # Clean up matchmaking state for this user
    try:
        from app.services.matchmaking_service import matchmaking_service
        await matchmaking_service.cleanup_user_match(participant_id)
        print(f"Cleaned up matchmaking state for participant {participant_id}")
    except Exception as e:
        print(f"Warning: Failed to cleanup matchmaking state: {e}")
    
    return {"message": "Left room successfully"}

@router.patch("/{room_id}/participants/{participant_id}/role")
async def update_participant_role(
    room_id: str,
    participant_id: str,
    role: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    redis = Depends(get_redis)
):
    """Update participant role (e.g. stance in debate)"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = Room(**room_data)
    for p in room.participants:
        if p.id == participant_id:
            p.role = role
            break
    else:
        raise HTTPException(status_code=404, detail="Participant not found")
    
    # Update database
    await db.rooms.update_one(
        {"id": room_id},
        {"$set": {"participants": [p.model_dump() for p in room.participants]}}
    )
    
    # Update Redis cache
    await redis.set_room_state(room_id, room.model_dump(mode='json'))
    
    return {"message": "Role updated", "role": role}

@router.delete("/{room_id}")
async def delete_room(
    room_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Delete a room"""
    result = await db.rooms.update_one(
        {"id": room_id},
        {"$set": {"is_active": False}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Room not found")
    
    return {"message": "Room deleted successfully"}

@router.delete("/")
async def clear_all_rooms(
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Clear all rooms and participants"""
    # Delete all rooms
    await db.rooms.delete_many({})
    
    return {"message": "All rooms cleared successfully"}

@router.post("/{room_id}/generate-scenario")
async def generate_scenario(
    room_id: str,
    discussion_mode: DiscussionMode,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Generate a roleplay scenario for group discussion"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = Room(**room_data)
    
    if room.mode != RoomMode.GROUP_DISCUSSION:
        raise HTTPException(status_code=400, detail="Scenario generation only available for group discussions")
    
    # Generate scenario
    scenario_data = await ai_service.generate_discussion_scenario(
        discussion_mode=discussion_mode.value,
        participant_count=len(room.participants) or 2
    )
    
    # Update room with scenario and discussion mode
    await db.rooms.update_one(
        {"id": room_id},
        {"$set": {
            "scenario": scenario_data["scenario"],
            "discussion_mode": discussion_mode.value
        }}
    )
    
    return {
        "scenario": scenario_data["scenario"],
        "roles": scenario_data["roles"],
        "discussion_mode": discussion_mode.value
    }

@router.post("/{room_id}/start-round")
async def start_round(
    room_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Start a discussion round"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = Room(**room_data)
    
    if room.round_in_progress:
        raise HTTPException(status_code=400, detail="Round already in progress")
    
    # Start round
    await db.rooms.update_one(
        {"id": room_id},
        {"$set": {
            "round_in_progress": True,
            "round_start_time": datetime.utcnow()
        }}
    )
    
    return {"message": "Round started", "start_time": datetime.utcnow()}

@router.post("/{room_id}/end-round")
async def end_round(
    room_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """End a discussion round and trigger report generation"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = Room(**room_data)
    
    if not room.round_in_progress:
        raise HTTPException(status_code=400, detail="No round in progress")
    
    # End round
    await db.rooms.update_one(
        {"id": room_id},
        {"$set": {
            "round_in_progress": False,
            "round_start_time": None
        }}
    )
    
    return {
        "message": "Round ended - reports will be generated",
        "end_time": datetime.utcnow()
    }

@router.post("/{room_id}/jam-topic")
async def get_jam_topic(
    room_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Generate a JAM topic"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = Room(**room_data)
    
    if room.mode != RoomMode.JAM:
        raise HTTPException(status_code=400, detail="JAM topics only available for JAM mode")
    
    # Get conversation history from request body if provided
    conversation_history = []
    if hasattr(request, 'json'):
        try:
            body = await request.json()
            conversation_history = body.get('conversation_history', [])
        except:
            pass
    
    # Generate topic with conversation history
    topic_data = await ai_service.generate_jam_topic(conversation_history)
    
    # The response is now just the topic text
    extracted_topic = topic_data.get("response", "").strip()
    
    # Update room with topic
    await db.rooms.update_one(
        {"id": room_id},
        {"$set": {"current_topic": extracted_topic}}
    )
    
    return topic_data

@router.post("/{room_id}/mediate")
async def mediate_discussion(room_id: str, data: dict):
    """AI mediator comment for group discussion"""
    latest_speech = data.get("latest_speech", "")
    scenario = data.get("scenario", "")
    history = data.get("history", [])
    participant_name = data.get("participant_name", "Participant")

    context = "\n".join(history[-6:]) if history else ""
    prompt = f"""You are an AI facilitator for a group discussion.
Scenario: {scenario}
Recent conversation:
{context}
{participant_name} just said: "{latest_speech}"

Give a SHORT (1-2 sentence) facilitation comment: ask a follow-up question, highlight a key point, or invite another perspective. Be concise and encouraging.
Respond with just the comment text, no JSON."""

    try:
        response = await ai_service.generate_simple_response(prompt)
        return {"comment": response}
    except Exception as e:
        logger.error(f"Mediation failed: {e}")
        return {"comment": "Interesting point! Can anyone build on that?"}


@router.post("/{room_id}/debate-judge")
async def judge_debate(room_id: str, data: dict):
    """AI judge comment for debate"""
    speech = data.get("speech", "")
    speaker_name = data.get("speaker_name", "Speaker")
    topic = data.get("topic", "")
    stance = data.get("stance", "")
    history = data.get("history", [])

    context = "\n".join(history[-6:]) if history else ""
    prompt = f"""You are an AI debate judge.
Topic: "{topic}"
{speaker_name} (arguing {stance}) just said: "{speech}"
Recent debate:
{context}

Give a SHORT (1-2 sentence) judgment: comment on the argument's logic, evidence, or delivery. Be fair and specific.
Respond with just the comment text, no JSON."""

    try:
        response = await ai_service.generate_simple_response(prompt)
        return {"comment": response}
    except Exception as e:
        logger.error(f"Debate judge failed: {e}")
        return {"comment": "Good argument. Make sure to support your points with evidence."}


@router.post("/{room_id}/analyze-body-language")
async def analyze_body_language(
    room_id: str,
    data: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Analyze body language from image snapshots"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"=== BODY LANGUAGE ANALYSIS REQUEST ===")
    logger.info(f"Room ID: {room_id}")
    logger.info(f"Number of images: {len(data.get('images', []))}")
    
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    
    images = data.get("images", [])
    context = data.get("context", "")
    
    if not images:
        raise HTTPException(status_code=400, detail="No images provided for analysis")
    
    # Analyze body language
    analysis = await ai_service.analyze_body_language(images, context)
    
    logger.info(f"=== BODY LANGUAGE ANALYSIS COMPLETE ===")
    
    return analysis


@router.post("/{room_id}/jam-evaluate")
async def evaluate_jam_speech(
    room_id: str,
    data: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Evaluate JAM speech performance with prosody analysis, conversation context, and body language"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"=== JAM EVALUATION REQUEST ===")
    logger.info(f"Room ID: {room_id}")
    logger.info(f"Data received: {data}")
    logger.info(f"Transcript: '{data.get('transcript')}'")
    logger.info(f"Transcript length: {len(data.get('transcript', ''))}")
    logger.info(f"Has webcam photo: {bool(data.get('webcam_photo'))}")
    
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = Room(**room_data)
    
    if room.mode != RoomMode.JAM:
        raise HTTPException(status_code=400, detail="JAM evaluation only available for JAM mode")
    
    # Get session data for prosody metrics
    session_id = data.get("session_id")
    participant_id = data.get("participant_id")
    conversation_history = data.get("conversation_history", [])
    webcam_photo = data.get("webcam_photo")
    prosody_metrics = None
    
    if session_id and participant_id:
        # Fetch prosody metrics from session
        session_data = await db.sessions.find_one({"id": session_id})
        if session_data:
            # Get the latest speech analysis for this participant
            analyses = session_data.get("speech_analyses", [])
            participant_analyses = [a for a in analyses if a.get("participant_id") == participant_id]
            if participant_analyses:
                latest = participant_analyses[-1]
                prosody_metrics = latest.get("prosody_metrics")
    
    # Analyze body language if photo is provided
    body_language_analysis = None
    if webcam_photo:
        try:
            logger.info("🎭 Analyzing body language from webcam photo...")
            body_language_analysis = await ai_service.analyze_body_language(
                image_data=webcam_photo,
                context=f"JAM session speaking about: {data.get('topic')}"
            )
            logger.info(f"Body language analysis: {body_language_analysis}")
        except Exception as e:
            logger.error(f"Body language analysis failed: {e}")
            body_language_analysis = None
    
    # Get evaluation from AI with prosody context, conversation history, and body language
    evaluation = await ai_service.evaluate_jam_performance(
        topic=data.get("topic"),
        transcript=data.get("transcript"),
        duration=data.get("duration", 60),
        prosody_metrics=prosody_metrics,
        conversation_history=conversation_history,
        body_language=body_language_analysis
    )
    
    # Include prosody metrics and body language in response
    evaluation["prosody_metrics"] = prosody_metrics
    evaluation["body_language"] = body_language_analysis
    
    logger.info(f"=== JAM EVALUATION RESPONSE ===")
    logger.info(f"Evaluation: {evaluation}")
    
    return evaluation

@router.post("/{room_id}/jam-topic")
async def get_jam_topic(
    room_id: str,
    data: dict = {},
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Generate a JAM topic for the room with conversation context"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = Room(**room_data)
    
    if room.mode != RoomMode.JAM:
        raise HTTPException(status_code=400, detail="JAM topics only available for JAM mode")
    
    # Get conversation history from request
    conversation_history = data.get("conversation_history", [])
    
    # Generate topic with context
    topic_data = await ai_service.generate_jam_topic(conversation_history)
    
    # Update room with current topic
    await db.rooms.update_one(
        {"id": room_id},
        {"$set": {"current_topic": topic_data["topic"]}}
    )
    
    return topic_data


@router.post("/{room_id}/reading-generate-topic")
async def generate_reading_topic(
    room_id: str,
    data: dict = {},
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Generate a long reading paragraph for the Reading Practice room"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    conversation_history = data.get("conversation_history", [])
    context = ""
    if conversation_history:
        context = "Previous passages used:\n" + "\n".join(conversation_history[-3:])

    prompt = f"""You are a reading practice coach. Generate a rich, engaging paragraph for a speaking/reading practice session.

{context}

Requirements:
- 6-9 sentences long (a proper paragraph, NOT a short snippet)
- Interesting and thought-provoking topic (science, culture, history, technology, nature, philosophy, etc.)
- Varied sentence structure: mix short punchy sentences with longer complex ones
- Rich vocabulary but still readable aloud
- No bullet points, no headers — just a flowing paragraph
- Each time generate a DIFFERENT topic/theme from previous ones

Respond in valid JSON: {{"response": "<the full paragraph text only>"}}"""

    try:
        await ai_service.rate_limiter.acquire()
        import asyncio as _asyncio
        loop = _asyncio.get_event_loop()
        response = await _asyncio.wait_for(
            loop.run_in_executor(None, ai_service.model.generate_content, prompt),
            timeout=30.0
        )
        text = response.text.strip()

        import json as _json
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            parsed = _json.loads(text[start:end])
            paragraph = parsed.get("response", "").strip()
        else:
            paragraph = text.strip()

        if not paragraph:
            raise ValueError("Empty paragraph")

        return {"response": paragraph}

    except Exception as e:
        logger.error(f"Reading topic generation failed: {e}")
        # Fallback paragraph
        return {
            "response": "The ocean covers more than seventy percent of our planet's surface, yet it remains one of the least explored frontiers known to humanity. Beneath its shimmering waves lies a world of extraordinary complexity — vast mountain ranges taller than the Himalayas, trenches deeper than any canyon on land, and ecosystems teeming with creatures that produce their own light in the perpetual darkness. Scientists estimate that we have mapped less than twenty percent of the ocean floor in detail, meaning that more is known about the surface of Mars than about the depths of our own seas. Every expedition into the deep returns with discoveries that challenge our understanding of life itself, from heat-loving bacteria thriving near volcanic vents to translucent jellyfish drifting through waters untouched by sunlight. The ocean also regulates our climate, absorbs vast quantities of carbon dioxide, and generates more than half of the oxygen we breathe. To protect it is not merely an environmental concern — it is a matter of planetary survival."
        }


@router.post("/{room_id}/reading-evaluate")
async def evaluate_reading_speech(
    room_id: str,
    data: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Evaluate Reading Practice speech with full prosody + body language analysis"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    passage = data.get("passage", "")
    transcript = data.get("transcript", "")
    duration = data.get("duration", 60)
    session_id = data.get("session_id")
    participant_id = data.get("participant_id")
    webcam_photo = data.get("webcam_photo")

    # Fetch prosody metrics if available
    prosody_metrics = None
    if session_id and participant_id:
        session_data = await db.sessions.find_one({"id": session_id})
        if session_data:
            analyses = session_data.get("speech_analyses", [])
            participant_analyses = [a for a in analyses if a.get("participant_id") == participant_id]
            if participant_analyses:
                prosody_metrics = participant_analyses[-1].get("prosody_metrics")

    # Body language analysis
    body_language_analysis = None
    if webcam_photo:
        try:
            body_language_analysis = await ai_service.analyze_body_language(
                image_data=webcam_photo,
                context=f"Reading practice session"
            )
        except Exception as e:
            logger.error(f"Body language analysis failed: {e}")

    # Build prosody context
    prosody_context = ""
    if prosody_metrics:
        prosody_context = f"""
**Speech Metrics:**
- Average Pitch: {prosody_metrics.get('average_pitch', 'N/A')} Hz
- Pitch Range: {prosody_metrics.get('pitch_range', 'N/A')} Hz
- Speaking Rate: {prosody_metrics.get('speaking_rate', 'N/A')} syllables/second
- Pauses: {prosody_metrics.get('pause_count', 'N/A')} pauses detected
- Average Pause Duration: {prosody_metrics.get('average_pause_duration', 'N/A')} seconds
- Intensity: {prosody_metrics.get('average_intensity', 'N/A')} dB
"""

    # Word-level accuracy
    original_words = passage.lower().split()
    spoken_words = transcript.lower().split()
    correct = sum(1 for i, w in enumerate(spoken_words) if i < len(original_words) and w == original_words[i])
    accuracy_pct = round((correct / len(original_words)) * 100, 1) if original_words else 0
    wpm = round((len(spoken_words) / duration) * 60, 1) if duration > 0 else 0

    prompt = f"""You are an expert reading coach evaluating a reading aloud practice session.

**Original Passage:**
"{passage}"

**What the speaker said (transcript):**
"{transcript}"

**Computed Metrics:**
- Word Accuracy: {accuracy_pct}% ({correct}/{len(original_words)} words matched)
- Speaking Rate: {wpm} words per minute
- Duration: {duration} seconds
{prosody_context}

Provide a thorough, structured evaluation in JSON with these exact keys:
{{
  "overall": "2-3 sentence overall assessment of the reading performance",
  "scores": {{
    "accuracy": <0-100 integer>,
    "fluency": <0-100 integer>,
    "pronunciation": <0-100 integer>,
    "expression": <0-100 integer>
  }},
  "strengths": ["strength 1", "strength 2"],
  "improvements": ["area 1", "area 2"],
  "prosody_feedback": "1-2 sentences specifically about pace, rhythm, and intonation",
  "pronunciation_notes": ["specific word or sound observation"],
  "suggestions": ["actionable tip 1", "actionable tip 2", "actionable tip 3"]
}}

Be encouraging but specific. Reference actual words/phrases from the transcript where possible."""

    import json as _json
    for attempt in range(3):
        try:
            response = await ai_service.generate_response(prompt, mode="reading", max_retries=2)
            text = response.get("text", "")
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                evaluation = _json.loads(text[start:end])
                if evaluation.get("overall"):
                    evaluation["prosody_metrics"] = prosody_metrics
                    evaluation["body_language"] = body_language_analysis
                    evaluation["computed"] = {"accuracy_pct": accuracy_pct, "wpm": wpm}
                    return evaluation
        except Exception as e:
            logger.error(f"Reading evaluation attempt {attempt+1} failed: {e}")
            import asyncio as _asyncio
            await _asyncio.sleep(2)

    return {
        "overall": "Good effort on your reading practice! Keep working on fluency and expression.",
        "scores": {"accuracy": accuracy_pct, "fluency": 70, "pronunciation": 70, "expression": 65},
        "strengths": ["Completed the reading passage", "Showed effort and dedication"],
        "improvements": ["Practice reading aloud daily", "Focus on smooth word transitions"],
        "prosody_feedback": "Work on maintaining a steady pace throughout the passage.",
        "pronunciation_notes": ["Continue practicing difficult words"],
        "suggestions": ["Read aloud for 10 minutes daily", "Record yourself and listen back", "Focus on punctuation pauses"],
        "prosody_metrics": prosody_metrics,
        "body_language": body_language_analysis,
        "computed": {"accuracy_pct": accuracy_pct, "wpm": wpm}
    }


# ── BUSINESS TALKS ──────────────────────────────────────────────────────────

@router.post("/{room_id}/business-scenario")
async def generate_business_scenario(
    room_id: str,
    data: dict = {},
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Generate a business scenario with roles for the user and AI"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    history = data.get("conversation_history", [])
    context = ("Previous scenarios used:\n" + "\n".join(history[-3:])) if history else ""

    prompt = f"""You are a business communication coach. Generate a realistic business roleplay scenario.

{context}

Requirements:
- Create a DIFFERENT scenario from any previous ones
- The scenario should be a real-world business situation (pitch, negotiation, client meeting, performance review, stakeholder update, etc.)
- Assign the USER a clear role (e.g. "Sales Manager", "Product Lead", "Consultant")
- Assign the AI a clear opposing/complementary role (e.g. "Skeptical Investor", "Demanding Client", "Senior Executive")
- Write a 2-3 sentence scene-setting description
- Write the AI's opening line to kick off the conversation IN CHARACTER

Respond in valid JSON:
{{
  "scenario": "<2-3 sentence scene description>",
  "user_role": "<user's role title>",
  "ai_role": "<AI's role title>",
  "opening_line": "<AI's first in-character line to start the conversation>"
}}"""

    try:
        response = await ai_service.generate_simple_response(prompt)
        import json as _json
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            return _json.loads(response[start:end])
    except Exception as e:
        logger.error(f"Business scenario generation failed: {e}")

    return {
        "scenario": "You are presenting a new product roadmap to a key client who has concerns about delivery timelines and budget overruns from the previous quarter.",
        "user_role": "Product Manager",
        "ai_role": "Skeptical Client",
        "opening_line": "Before we begin, I have to be honest — after last quarter's delays, my team is questioning whether we should continue this partnership. What's changed?"
    }


@router.post("/{room_id}/business-chat")
async def business_chat_turn(
    room_id: str,
    data: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Single AI turn in a business conversation"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    user_message = data.get("message", "")
    scenario = data.get("scenario", "")
    ai_role = data.get("ai_role", "Business Partner")
    user_role = data.get("user_role", "Professional")
    history = data.get("history", [])
    turn = data.get("turn", 1)

    context = "\n".join(history[-8:]) if history else ""

    prompt = f"""You are playing the role of: {ai_role}
Scenario: {scenario}
The user is playing: {user_role}

Conversation so far:
{context}

{user_role}: {user_message}

Respond IN CHARACTER as {ai_role}. Be realistic, challenging but fair. Keep your response to 2-4 sentences.
This is turn {turn}. If turn >= 8, naturally wrap up the conversation with a closing remark that signals the meeting is ending.

Respond with ONLY your in-character dialogue. No JSON, no labels."""

    try:
        response = await ai_service.generate_simple_response(prompt)
        return {"response": response.strip()}
    except Exception as e:
        logger.error(f"Business chat turn failed: {e}")
        return {"response": "I see your point. Let me think about that for a moment."}


@router.post("/{room_id}/business-evaluate")
async def evaluate_business_session(
    room_id: str,
    data: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Evaluate the full business conversation"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    scenario = data.get("scenario", "")
    user_role = data.get("user_role", "Professional")
    ai_role = data.get("ai_role", "Business Partner")
    history = data.get("history", [])
    webcam_photo = data.get("webcam_photo")

    body_language = None
    if webcam_photo:
        try:
            body_language = await ai_service.analyze_body_language(
                image_data=webcam_photo,
                context=f"Business meeting: {scenario}"
            )
        except Exception as e:
            logger.error(f"Body language analysis failed: {e}")

    conversation_text = "\n".join(history)

    prompt = f"""You are a business communication coach evaluating a roleplay session.

Scenario: {scenario}
User played: {user_role}
AI played: {ai_role}

Full conversation:
{conversation_text}

Evaluate the user's communication performance. Provide structured JSON feedback:
{{
  "overall_feedback": "2-3 sentence overall assessment",
  "communication_strengths": ["strength 1", "strength 2", "strength 3"],
  "areas_for_improvement": ["area 1", "area 2"],
  "professional_language_score": <0-100>,
  "persuasiveness_score": <0-100>,
  "clarity_score": <0-100>,
  "actionable_suggestions": ["tip 1", "tip 2", "tip 3"]
}}"""

    import json as _json
    for attempt in range(3):
        try:
            response = await ai_service.generate_response(prompt, mode="business-talks", max_retries=2)
            text = response.get("text", "")
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                result = _json.loads(text[start:end])
                if result.get("overall_feedback"):
                    result["body_language"] = body_language
                    return result
        except Exception as e:
            logger.error(f"Business evaluation attempt {attempt+1} failed: {e}")
            import asyncio as _asyncio
            await _asyncio.sleep(2)

    return {
        "overall_feedback": "Good effort in the business roleplay! You engaged professionally with the scenario.",
        "communication_strengths": ["Engaged with the scenario", "Maintained professional tone"],
        "areas_for_improvement": ["Be more specific with data and examples", "Practice handling objections"],
        "professional_language_score": 70,
        "persuasiveness_score": 65,
        "clarity_score": 72,
        "actionable_suggestions": ["Use the STAR method for responses", "Prepare data points in advance", "Practice active listening"],
        "body_language": body_language
    }


# ── SOCIALISING / SOCIAL CONFIDENCE ─────────────────────────────────────────

@router.post("/{room_id}/social-scenario")
async def generate_social_scenario(
    room_id: str,
    data: dict = {},
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Generate a social confidence scenario"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    history = data.get("conversation_history", [])
    context = ("Previous scenarios:\n" + "\n".join(history[-3:])) if history else ""

    prompt = f"""You are a social confidence coach. Generate a friendly, low-stakes social scenario for practice.

{context}

Requirements:
- Common everyday social situation (meeting someone new at a party, asking for help, joining a group conversation, small talk with a neighbour, etc.)
- Warm and approachable — NOT intimidating
- Give the AI a friendly persona/role (e.g. "Friendly Neighbour", "New Colleague", "Person at a coffee shop")
- Write a natural, warm opening line to start the conversation

Respond in valid JSON:
{{
  "scenario": "<1-2 sentence scene description>",
  "ai_persona": "<AI's friendly persona>",
  "opening_line": "<AI's warm opening line to start the chat>"
}}"""

    try:
        response = await ai_service.generate_simple_response(prompt)
        import json as _json
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            return _json.loads(response[start:end])
    except Exception as e:
        logger.error(f"Social scenario generation failed: {e}")

    return {
        "scenario": "You're at a community event and someone friendly approaches you near the snack table.",
        "ai_persona": "Friendly Stranger at an Event",
        "opening_line": "Hi! These little sandwiches are amazing, right? Have you been to one of these events before?"
    }


@router.post("/{room_id}/social-chat")
async def social_chat_turn(
    room_id: str,
    data: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Single AI turn in a social conversation"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    user_message = data.get("message", "")
    scenario = data.get("scenario", "")
    ai_persona = data.get("ai_persona", "Friendly Person")
    history = data.get("history", [])
    turn = data.get("turn", 1)

    context = "\n".join(history[-8:]) if history else ""

    prompt = f"""You are playing: {ai_persona}
Scenario: {scenario}

Conversation so far:
{context}

User: {user_message}

Respond as {ai_persona} — warm, natural, encouraging. Keep it to 1-3 sentences like real casual conversation.
If turn {turn} >= 7, naturally wrap up the chat in a friendly way.

Respond with ONLY your natural dialogue. No labels, no JSON."""

    try:
        response = await ai_service.generate_simple_response(prompt)
        return {"response": response.strip()}
    except Exception as e:
        logger.error(f"Social chat turn failed: {e}")
        return {"response": "That's really interesting! Tell me more."}


@router.post("/{room_id}/social-evaluate")
async def evaluate_social_session(
    room_id: str,
    data: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Evaluate the social confidence conversation"""
    room_data = await db.rooms.find_one({"id": room_id})
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    scenario = data.get("scenario", "")
    ai_persona = data.get("ai_persona", "Friendly Person")
    history = data.get("history", [])

    conversation_text = "\n".join(history)

    prompt = f"""You are a warm, encouraging social confidence coach evaluating a practice conversation.

Scenario: {scenario}
AI played: {ai_persona}

Conversation:
{conversation_text}

Give warm, supportive feedback. JSON format:
{{
  "positive_summary": "2-3 encouraging sentences about what went well",
  "moments_to_celebrate": ["specific good moment 1", "specific good moment 2"],
  "gentle_suggestions_for_growth": ["gentle tip 1", "gentle tip 2"],
  "confidence_score": <0-100>,
  "engagement_score": <0-100>,
  "motivational_takeaway": "One powerful encouraging sentence to end on"
}}"""

    import json as _json
    for attempt in range(3):
        try:
            response = await ai_service.generate_response(prompt, mode="socialising", max_retries=2)
            text = response.get("text", "")
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                result = _json.loads(text[start:end])
                if result.get("positive_summary"):
                    return result
        except Exception as e:
            logger.error(f"Social evaluation attempt {attempt+1} failed: {e}")
            import asyncio as _asyncio
            await _asyncio.sleep(2)

    return {
        "positive_summary": "You did a wonderful job engaging in this social practice! Every conversation you have builds your confidence.",
        "moments_to_celebrate": ["You kept the conversation going", "You responded naturally"],
        "gentle_suggestions_for_growth": ["Try asking follow-up questions", "Share a little about yourself too"],
        "confidence_score": 75,
        "engagement_score": 78,
        "motivational_takeaway": "Every conversation is a step forward — you're doing great!"
    }
