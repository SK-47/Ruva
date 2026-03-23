import socketio
import logging
from typing import Dict, List, Any, Optional
import json
from datetime import datetime
import uuid

from app.core.redis_client import redis_client
from app.core.config import settings
from app.services.speech_service import SpeechService
from app.services.ai_service import AIService
from app.core.database import db
from app.models.room import Room, Participant, ConnectionStatus

logger = logging.getLogger(__name__)

# Create Socket.IO server with Redis manager for scaling
# Cloud Run scales to multiple instances, so we need a common message broker
mgr = None
if settings.REDIS_URL:
    try:
        mgr = socketio.AsyncRedisManager(settings.REDIS_URL)
        logger.info(f"Socket.IO using Redis manager at {settings.REDIS_URL}")
    except Exception as e:
        logger.error(f"Failed to initialize Socket.IO Redis manager: {e}")

sio = socketio.AsyncServer(
    async_mode='asgi',
    client_manager=mgr,
    cors_allowed_origins=["*"], # Allow all origins for production, controlled by FastAPI CORS
    logger=True,
    engineio_logger=True
)

# Store active connections
active_connections: Dict[str, Dict[str, Any]] = {}
room_participants: Dict[str, List[str]] = {}

# Import group discussion service
from app.services.modes.group_discussion_mode import group_discussion_service

class RoomManager:
    """Enhanced room management with state synchronization"""
    
    @staticmethod
    async def get_room_from_db(room_id: str) -> Optional[Room]:
        """Get room data from database"""
        try:
            room_data = await db.database.rooms.find_one({"id": room_id})
            if room_data:
                return Room(**room_data)
            return None
        except Exception as e:
            logger.error(f"Error fetching room {room_id} from database: {e}")
            return None
    
    @staticmethod
    async def update_room_in_db(room: Room):
        """Update room data in database"""
        try:
            await db.database.rooms.update_one(
                {"id": room.id},
                {"$set": room.model_dump(mode='json')}
            )
        except Exception as e:
            logger.error(f"Error updating room {room.id} in database: {e}")
    
    @staticmethod
    async def add_participant_to_room(room_id: str, participant_name: str, participant_id: str, sid: str) -> Optional[Participant]:
        """Add participant to room with proper state management"""
        try:
            # Get room from database
            room = await RoomManager.get_room_from_db(room_id)
            if not room:
                logger.error(f"Room {room_id} not found")
                return None
            
            if not room.is_active:
                logger.error(f"Room {room_id} is not active")
                return None
            
            # Check if participant with same ID already exists (rejoin scenario)
            existing_participant = next((p for p in room.participants if p.id == participant_id), None)
            
            if existing_participant:
                logger.info(f"Participant {participant_name} (ID: {participant_id}) rejoining room {room_id}")
                # Update connection status
                existing_participant.connection_status = ConnectionStatus.CONNECTED
                await RoomManager.update_room_in_db(room)
                await redis_client.set_room_state(room_id, room.model_dump(mode='json'))
                return existing_participant
            
            # Check if room is full (only for new participants)
            if len(room.participants) >= room.max_participants:
                logger.error(f"Room {room_id} is full: {len(room.participants)}/{room.max_participants} participants")
                logger.error(f"Current participants: {[p.name + ' (' + p.id + ')' for p in room.participants]}")
                return None
            
            # Create new participant with the actual participant ID from matchmaking
            participant = Participant(
                id=participant_id,  # Use actual participant ID, not random UUID
                name=participant_name,
                joined_at=datetime.utcnow(),
                connection_status=ConnectionStatus.CONNECTED
            )
            
            logger.info(f"Adding new participant to room: {participant_name} (ID: {participant_id})")
            
            # Add participant to room
            room.participants.append(participant)
            
            # Update database
            await RoomManager.update_room_in_db(room)
            
            # Update Redis cache with JSON-serializable data
            await redis_client.set_room_state(room_id, room.model_dump(mode='json'))
            
            return participant
            
        except Exception as e:
            logger.error(f"Error adding participant to room {room_id}: {e}")
            return None
    
    @staticmethod
    async def remove_participant_from_room(room_id: str, participant_id: str):
        """Remove participant from room with proper state management"""
        try:
            # Get room from database
            room = await RoomManager.get_room_from_db(room_id)
            if not room:
                return
            
            # Remove participant
            room.participants = [p for p in room.participants if p.id != participant_id]
            
            # Update database
            await RoomManager.update_room_in_db(room)
            
            # Update Redis cache with JSON-serializable data
            await redis_client.set_room_state(room_id, room.model_dump(mode='json'))
            
        except Exception as e:
            logger.error(f"Error removing participant {participant_id} from room {room_id}: {e}")
    
    @staticmethod
    async def update_participant_status(room_id: str, participant_id: str, is_speaking: bool = None, connection_status: ConnectionStatus = None):
        """Update participant status in room"""
        try:
            # Get room from database
            room = await RoomManager.get_room_from_db(room_id)
            if not room:
                return
            
            # Find and update participant
            for participant in room.participants:
                if participant.id == participant_id:
                    if is_speaking is not None:
                        participant.is_speaking = is_speaking
                    if connection_status is not None:
                        participant.connection_status = connection_status
                    break
            
            # Update database
            await RoomManager.update_room_in_db(room)
            
            # Update Redis cache with JSON-serializable data
            await redis_client.set_room_state(room_id, room.model_dump(mode='json'))
            
        except Exception as e:
            logger.error(f"Error updating participant {participant_id} status in room {room_id}: {e}")
    
    @staticmethod
    async def get_room_participants(room_id: str) -> List[Participant]:
        """Get all participants in a room"""
        try:
            room = await RoomManager.get_room_from_db(room_id)
            if room:
                return room.participants
            return []
        except Exception as e:
            logger.error(f"Error getting participants for room {room_id}: {e}")
            return []
    
    @staticmethod
    async def synchronize_room_state(room_id: str):
        """Synchronize room state across all participants"""
        try:
            room = await RoomManager.get_room_from_db(room_id)
            if not room:
                return
            
            # Broadcast current room state to all participants
            await sio.emit('room-state-update', {
                'room_id': room_id,
                'participants': [p.model_dump(mode='json') for p in room.participants],
                'is_active': room.is_active,
                'current_topic': room.current_topic,
                'participant_count': len(room.participants)
            }, room=room_id)
            
        except Exception as e:
            logger.error(f"Error synchronizing room state for {room_id}: {e}")

# Add connection logging
@sio.event
async def connect(sid, environ):
    """Handle client connection"""
    logger.info(f"Client {sid} connected")
    logger.info(f"Connection environ: {environ.get('HTTP_ORIGIN', 'No origin')}")
    active_connections[sid] = {
        "connected_at": datetime.utcnow(),
        "room_id": None,
        "participant_id": None,
        "participant_name": None
    }
    logger.info(f"Active connections count: {len(active_connections)}")

@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    logger.info(f"Client {sid} disconnected")
    
    # Remove from room if they were in one
    if sid in active_connections:
        room_id = active_connections[sid].get("room_id")
        participant_id = active_connections[sid].get("participant_id")
        
        if room_id and participant_id:
            # Update participant status to disconnected
            await RoomManager.update_participant_status(
                room_id, 
                participant_id, 
                connection_status=ConnectionStatus.DISCONNECTED
            )
            
            # Remove from local tracking
            if room_id in room_participants and sid in room_participants[room_id]:
                room_participants[room_id].remove(sid)
                
                # Notify other participants
                await sio.emit('participant-left', {
                    'participant_id': participant_id,
                    'room_id': room_id,
                    'participant_name': active_connections[sid].get("participant_name")
                }, room=room_id, skip_sid=sid)
                
                # Synchronize room state
                await RoomManager.synchronize_room_state(room_id)
        
        del active_connections[sid]
    
    logger.info(f"Active connections count: {len(active_connections)}")

@sio.event
async def join_room(sid, data):
    """Handle room joining with enhanced state management"""
    try:
        logger.info(f"=== JOIN ROOM EVENT ===")
        logger.info(f"SID: {sid}")
        logger.info(f"Data: {data}")
        logger.info(f"Data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        logger.info(f"Active connections count: {len(active_connections)}")
        logger.info(f"Current active connections: {list(active_connections.keys())}")
        
        # Support both camelCase and snake_case
        room_id = data.get('room_id') or data.get('roomId')
        participant_name = data.get('participant_name') or data.get('participantName')
        participant_id = data.get('participant_id') or data.get('participantId')
        
        logger.info(f"Extracted - room_id: {room_id}, participant_name: {participant_name}, participant_id: {participant_id}")
        
        if not room_id or not participant_name:
            logger.error(f"Missing required fields - room_id: {room_id}, participant_name: {participant_name}")
            await sio.emit('error', {'message': 'Missing room_id or participant_name'}, room=sid)
            return
        
        logger.info(f"Attempting to add participant {participant_name} (ID: {participant_id}) to room {room_id}")
        
        # Add participant to room using RoomManager
        # Use participant_id if provided, otherwise generate one for backward compatibility
        actual_participant_id = participant_id if participant_id else str(uuid.uuid4())
        participant = await RoomManager.add_participant_to_room(room_id, participant_name, actual_participant_id, sid)
        
        if not participant:
            logger.error(f"Failed to add participant to room {room_id}")
            await sio.emit('error', {'message': 'Failed to join room. Room may be full or name taken.'}, room=sid)
            return
        
        logger.info(f"✅ Participant added to room: {participant.id}")
        
        # Join Socket.IO room
        sio.enter_room(sid, room_id)
        logger.info(f"✅ Entered Socket.IO room: {room_id}")
        
        # Update connection info
        active_connections[sid].update({
            'room_id': room_id,
            'participant_id': participant.id,
            'participant_name': participant_name
        })
        
        logger.info(f"✅ Updated active_connections for {sid}: {active_connections[sid]}")
        
        # Add to local room participants tracking
        if room_id not in room_participants:
            room_participants[room_id] = []
        room_participants[room_id].append(sid)
        
        # Get current room participants for the joining user
        participants = await RoomManager.get_room_participants(room_id)
        
        logger.info(f"Current participants in room: {len(participants)}")
        
        # Send confirmation to joining participant
        await sio.emit('room-joined', {
            'room_id': room_id,
            'participant_id': participant.id,
            'participant_count': len(participants),
            'participants': [p.model_dump(mode='json') for p in participants],
            'current_topic': room.current_topic if 'room' in locals() and room else None,
            'scenario': room.scenario if 'room' in locals() and room else None
        }, room=sid)
        
        logger.info(f"✅ Sent room-joined confirmation to {sid}")
        
        # Broadcast room_update to ALL participants (including the one who just joined)
        updated_participants = await RoomManager.get_room_participants(room_id)
        logger.info(f"🔄 Broadcasting room_update with {len(updated_participants)} participants")
        for i, p in enumerate(updated_participants):
            logger.info(f"  Participant {i+1}: {p.name} ({p.id}) - AI: {p.is_ai}")
        
        room = await RoomManager.get_room_from_db(room_id)
        await sio.emit('room_update', {
            'participants': [p.model_dump(mode='json') for p in updated_participants],
            'room_id': room_id,
            'current_topic': room.current_topic if room else None,
            'scenario': room.scenario if room else None
        }, room=room_id)
        
        # Also send individual participant-joined events to ensure all clients are notified
        await sio.emit('participant-joined', {
            'participant_id': participant.id,
            'participant_name': participant_name,
            'room_id': room_id,
            'joined_at': participant.joined_at.isoformat(),
            'total_participants': len(updated_participants)
        }, room=room_id, skip_sid=sid)
        
        # Synchronize room state
        await RoomManager.synchronize_room_state(room_id)
        
        # Additional synchronization - broadcast room state after a short delay to ensure all clients are ready
        import asyncio
        async def delayed_sync():
            await asyncio.sleep(1)  # Wait 1 second
            try:
                final_participants = await RoomManager.get_room_participants(room_id)
                logger.info(f"🔄 DELAYED SYNC: Broadcasting final room state with {len(final_participants)} participants")
                await sio.emit('room_update', {
                    'participants': [p.model_dump(mode='json') for p in final_participants],
                    'room_id': room_id,
                    'sync_type': 'delayed'
                }, room=room_id)
            except Exception as e:
                logger.error(f"Error in delayed sync: {e}")
        
        # Schedule delayed sync
        asyncio.create_task(delayed_sync())
        
        logger.info(f"✅✅✅ Participant {participant.id} ({participant_name}) successfully joined room {room_id}")
        
    except Exception as e:
        logger.error(f"❌ Error joining room: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to join room: {str(e)}'}, room=sid)

@sio.event
async def leave_room(sid, data):
    """Handle room leaving with enhanced state management"""
    try:
        room_id = data.get('room_id')
        
        if sid in active_connections:
            participant_id = active_connections[sid].get('participant_id')
            participant_name = active_connections[sid].get('participant_name')
            
            if room_id and participant_id:
                # Leave Socket.IO room
                sio.leave_room(sid, room_id)
                
                # Remove participant from room using RoomManager
                await RoomManager.remove_participant_from_room(room_id, participant_id)
                
                # Remove from local tracking
                if room_id in room_participants and sid in room_participants[room_id]:
                    room_participants[room_id].remove(sid)
                
                # Notify other participants
                await sio.emit('participant-left', {
                    'participant_id': participant_id,
                    'participant_name': participant_name,
                    'room_id': room_id
                }, room=room_id)
                
                # Update connection info
                active_connections[sid].update({
                    'room_id': None,
                    'participant_id': None,
                    'participant_name': None
                })
                
                # Synchronize room state
                await RoomManager.synchronize_room_state(room_id)
                
                # Send confirmation to leaving participant
                await sio.emit('room-left', {
                    'room_id': room_id,
                    'message': 'Successfully left room'
                }, room=sid)
                
                logger.info(f"Participant {participant_id} ({participant_name}) left room {room_id}")
        
    except Exception as e:
        logger.error(f"Error leaving room: {e}")
        await sio.emit('error', {'message': f'Failed to leave room: {str(e)}'}, room=sid)

@sio.event
async def start_voting(sid, data):
    """Start category voting for group discussion"""
    try:
        logger.info(f"=== START VOTING EVENT ===")
        logger.info(f"SID: {sid}")
        logger.info(f"Data: {data}")
        
        room_id = active_connections[sid].get('room_id')
        session_id = data.get('session_id')
        
        if not room_id or not session_id:
            await sio.emit('error', {'message': 'Missing room_id or session_id'}, room=sid)
            return
        
        # Start voting
        discussion_state = group_discussion_service.start_voting(session_id)
        
        # Broadcast voting start to all participants
        await sio.emit('voting-started', {
            'session_id': session_id,
            'voting_duration': discussion_state.voting_duration,
            'categories': [
                {'id': 'formal', 'name': 'Formal Discussion', 'description': 'Academic/professional discussion'},
                {'id': 'informal', 'name': 'Informal Chat', 'description': 'Casual conversation between friends'},
                {'id': 'business', 'name': 'Business Meeting', 'description': 'Corporate/workplace discussion'}
            ]
        }, room=room_id)
        
        logger.info(f"✅ Voting started for session {session_id}")
        
    except Exception as e:
        logger.error(f"❌ Error starting voting: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to start voting: {str(e)}'}, room=sid)

@sio.event
async def cast_vote(sid, data):
    """Handle category vote from participant"""
    try:
        logger.info(f"=== CAST VOTE EVENT ===")
        logger.info(f"SID: {sid}")
        logger.info(f"Data: {data}")
        
        room_id = active_connections[sid].get('room_id')
        session_id = data.get('session_id')
        category = data.get('category')
        participant_id = active_connections[sid].get('participant_id')
        participant_name = active_connections[sid].get('participant_name')
        
        if not all([room_id, session_id, category, participant_id]):
            await sio.emit('error', {'message': 'Missing required voting data'}, room=sid)
            return
        
        from app.services.modes.group_discussion_mode import DiscussionCategory
        
        # Cast vote
        discussion_state = group_discussion_service.cast_vote(
            session_id, participant_id, participant_name, DiscussionCategory(category)
        )
        
        # Broadcast vote update to all participants
        await sio.emit('vote-cast', {
            'session_id': session_id,
            'participant_name': participant_name,
            'category': category,
            'vote_counts': discussion_state.voting_results.vote_counts,
            'total_votes': len(discussion_state.voting_results.votes)
        }, room=room_id)
        
        logger.info(f"✅ Vote cast by {participant_name} for {category}")
        
    except Exception as e:
        logger.error(f"❌ Error casting vote: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to cast vote: {str(e)}'}, room=sid)

@sio.event
async def end_voting(sid, data):
    """End voting and generate topic/roles"""
    try:
        logger.info(f"=== END VOTING EVENT ===")
        
        room_id = active_connections[sid].get('room_id')
        session_id = data.get('session_id')
        
        if not room_id or not session_id:
            await sio.emit('error', {'message': 'Missing room_id or session_id'}, room=sid)
            return
        
        # End voting and get winning category
        discussion_state = group_discussion_service.end_voting(session_id)
        winning_category = discussion_state.voting_results.winning_category
        
        # Get room participants for role generation
        participants = await RoomManager.get_room_participants(room_id)
        total_participants = len(participants) + 1  # +1 for AI
        
        # Generate topic, scenario, and roles based on winning category
        content_data = group_discussion_service.generate_roles_and_scenario(
            session_id, winning_category, total_participants
        )
        
        # Update discussion with generated content
        discussion_state.topic = content_data['topic']
        discussion_state.scenario = content_data['scenario']
        
        # Assign roles to human participants and AI
        roles_assignment = {}
        ai_participant_id = f"ai_participant_{session_id}"
        
        # Assign roles to human participants
        for i, participant in enumerate(participants):
            if i < len(content_data['roles']) - 1:  # Reserve last role for AI
                role_info = content_data['roles'][i]
                roles_assignment[participant.id] = {
                    "role": role_info['role'],
                    "description": role_info['description']
                }
        
        # Assign role to AI participant
        if content_data['roles']:
            ai_role = content_data['roles'][-1]  # Last role goes to AI
            roles_assignment[ai_participant_id] = {
                "role": ai_role['role'],
                "description": ai_role['description']
            }
        
        # Update discussion state with roles
        group_discussion_service.assign_roles(session_id, roles_assignment)
        
        # Update room participants with roles and add AI
        room = await RoomManager.get_room_from_db(room_id)
        if room:
            for participant in room.participants:
                if participant.id in roles_assignment:
                    participant.role = roles_assignment[participant.id]['role']
                    participant.role_description = roles_assignment[participant.id]['description']
            
            # Add AI participant to room
            from app.models.room import Participant, ConnectionStatus
            ai_participant = Participant(
                id=ai_participant_id,
                name="AI Participant",
                is_ai=True,
                joined_at=datetime.utcnow(),
                connection_status=ConnectionStatus.CONNECTED,
                role=roles_assignment[ai_participant_id]['role'],
                role_description=roles_assignment[ai_participant_id]['description']
            )
            room.participants.append(ai_participant)
            room.current_topic = content_data['topic']
            
            await RoomManager.update_room_in_db(room)
        
        # Broadcast voting results and role assignments
        await sio.emit('voting-ended', {
            'session_id': session_id,
            'winning_category': winning_category.value,
            'vote_counts': discussion_state.voting_results.vote_counts,
            'topic': content_data['topic'],
            'scenario': content_data['scenario'],
            'roles': roles_assignment,
            'ai_participant_id': ai_participant_id
        }, room=room_id)
        
        # Broadcast updated participant list
        updated_participants = await RoomManager.get_room_participants(room_id)
        await sio.emit('room_update', {
            'participants': [p.model_dump(mode='json') for p in updated_participants],
            'room_id': room_id
        }, room=room_id)
        
        logger.info(f"✅ Voting ended, {winning_category.value} won, roles assigned for session {session_id}")
        
    except Exception as e:
        logger.error(f"❌ Error ending voting: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to end voting: {str(e)}'}, room=sid)
    """Handle role assignment for group discussions"""
    try:
        logger.info(f"=== ASSIGN ROLES EVENT ===")
        logger.info(f"SID: {sid}")
        logger.info(f"Data: {data}")
        
        room_id = active_connections[sid].get('room_id')
        session_id = data.get('session_id')
        topic = data.get('topic', 'General Discussion')
        
        if not room_id or not session_id:
            await sio.emit('error', {'message': 'Missing room_id or session_id'}, room=sid)
            return
        
        # Get room participants
        participants = await RoomManager.get_room_participants(room_id)
        if len(participants) < 1:  # Allow single participant + AI
            await sio.emit('error', {'message': 'Need at least 1 participant for role assignment'}, room=sid)
            return
        
        # Generate roles and scenario (including AI participant)
        total_participants = len(participants) + 1  # +1 for AI
        role_data = group_discussion_service.generate_roles_and_scenario(
            session_id, topic, total_participants
        )
        
        # Assign roles to human participants and AI
        roles_assignment = {}
        ai_participant_id = f"ai_participant_{session_id}"
        
        # Assign roles to human participants
        for i, participant in enumerate(participants):
            if i < len(role_data['roles']) - 1:  # Reserve last role for AI
                role_info = role_data['roles'][i]
                roles_assignment[participant.id] = {
                    "role": role_info['role'],
                    "description": role_info['description']
                }
        
        # Assign role to AI participant
        if role_data['roles']:
            ai_role = role_data['roles'][-1]  # Last role goes to AI
            roles_assignment[ai_participant_id] = {
                "role": ai_role['role'],
                "description": ai_role['description']
            }
        
        # Update discussion state
        discussion_state = group_discussion_service.assign_roles(session_id, roles_assignment)
        
        # Update room participants with roles
        room = await RoomManager.get_room_from_db(room_id)
        if room:
            for participant in room.participants:
                if participant.id in roles_assignment:
                    participant.role = roles_assignment[participant.id]['role']
                    participant.role_description = roles_assignment[participant.id]['description']
            
            # Add AI participant to room
            from app.models.room import Participant, ConnectionStatus
            ai_participant = Participant(
                id=ai_participant_id,
                name="AI Participant",
                is_ai=True,
                joined_at=datetime.utcnow(),
                connection_status=ConnectionStatus.CONNECTED,
                role=roles_assignment[ai_participant_id]['role'],
                role_description=roles_assignment[ai_participant_id]['description']
            )
            room.participants.append(ai_participant)
            
            await RoomManager.update_room_in_db(room)
        
        # Broadcast role assignments to all participants
        await sio.emit('roles-assigned', {
            'session_id': session_id,
            'scenario': role_data['scenario'],
            'topic': topic,
            'roles': roles_assignment,
            'category': role_data['category'],
            'ai_participant_id': ai_participant_id
        }, room=room_id)
        
        # Broadcast updated participant list
        updated_participants = await RoomManager.get_room_participants(room_id)
        await sio.emit('room_update', {
            'participants': [p.model_dump(mode='json') for p in updated_participants],
            'room_id': room_id
        }, room=room_id)
        
        logger.info(f"✅ Roles assigned for session {session_id} in room {room_id} (including AI participant)")
        
    except Exception as e:
        logger.error(f"❌ Error assigning roles: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to assign roles: {str(e)}'}, room=sid)

@sio.event
async def generate_scenario(sid, data):
    """Generate scenario for group discussion (especially for AI rooms)"""
    try:
        logger.info(f"=== GENERATE SCENARIO EVENT ===")
        logger.info(f"SID: {sid}")
        logger.info(f"Data: {data}")
        
        room_id = data.get('room_id')
        discussion_mode = data.get('discussion_mode', 'business')
        
        if not room_id:
            await sio.emit('error', {'message': 'Missing room_id'}, room=sid)
            return
        
        # Get room participants - allow solo sessions (user may not be in DB yet)
        participants = await RoomManager.get_room_participants(room_id)
        logger.info(f"Found {len(participants)} participants in room {room_id}")
        
        # If no participants found in DB, use the requesting SID as a fallback human participant
        if not any(not p.is_ai for p in participants):
            from app.models.room import Participant
            fallback = Participant(id=sid, name="User", is_ai=False, joined_at=datetime.utcnow())
            participants = [p for p in participants if p.is_ai] + [fallback]
            logger.info(f"No human participants in DB yet, added fallback participant for sid={sid}")
        
        # Create session ID if not provided
        session_id = f"session_{room_id}_{int(datetime.utcnow().timestamp())}"
        
        # Map discussion mode to category
        from app.services.modes.group_discussion_mode import DiscussionCategory
        category_mapping = {
            'business': DiscussionCategory.BUSINESS,
            'casual': DiscussionCategory.INFORMAL,
            'formal': DiscussionCategory.FORMAL
        }
        category = category_mapping.get(discussion_mode, DiscussionCategory.BUSINESS)
        
        # Generate roles and scenario for role selection
        total_participants = 2  # Always generate for 2 participants (user + AI)
        content_data = group_discussion_service.generate_roles_and_scenario(
            session_id, category, total_participants
        )
        
        # Create discussion session but don't assign roles yet
        participant_names = {p.id: p.name for p in participants}
        
        # Check if AI participants already exist in the room
        ai_participants_in_room = [p for p in participants if p.is_ai]
        
        if ai_participants_in_room:
            # Use existing AI participants from matchmaking
            logger.info(f"✅ Using existing AI participants: {[p.name for p in ai_participants_in_room]}")
            # Add existing AI participants to the discussion
            for ai_p in ai_participants_in_room:
                participant_names[ai_p.id] = ai_p.name
            
            discussion_state = group_discussion_service.create_discussion(
                room_id=room_id,
                session_id=session_id,
                participant_ids=[p.id for p in participants],  # Include all existing participants
                participant_names=participant_names,
                include_ai_participant=False  # Don't create new AI, use existing ones
            )
        else:
            # No AI participants exist, create new ones (fallback)
            logger.info(f"⚠️ No existing AI participants found, creating new ones")
            discussion_state = group_discussion_service.create_discussion(
                room_id=room_id,
                session_id=session_id,
                participant_ids=[p.id for p in participants],
                participant_names=participant_names,
                include_ai_participant=True
            )
        
        # Send role selection to user instead of auto-assigning
        await sio.emit('role_selection_required', {
            'session_id': session_id,
            'topic': content_data['topic'],
            'scenario': content_data['scenario'],
            'roles': content_data['roles'],  # 2 roles for user to choose from
            'category': content_data['category'],
            'discussion_mode': discussion_mode,
            'room_id': room_id
        }, room=room_id)
        
        logger.info(f"✅ Role selection sent for room {room_id} with {discussion_mode} mode")
        
    except Exception as e:
        logger.error(f"❌ Error generating scenario: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to generate scenario: {str(e)}'}, room=sid)

@sio.event
async def select_role(sid, data):
    """Handle user role selection"""
    try:
        logger.info(f"=== SELECT ROLE EVENT ===")
        logger.info(f"SID: {sid}")
        logger.info(f"Data: {data}")
        
        room_id = data.get('room_id')
        session_id = data.get('session_id')
        selected_role_index = data.get('selected_role_index')  # 0 or 1
        roles = data.get('roles')  # The 2 roles from role selection
        topic = data.get('topic')
        scenario = data.get('scenario')
        
        if not all([room_id, session_id, selected_role_index is not None, roles, topic, scenario]):
            await sio.emit('error', {'message': 'Missing required role selection data'}, room=sid)
            return
        
        # Get room participants
        participants = await RoomManager.get_room_participants(room_id)
        
        logger.info(f"🔍 Room participants for role assignment:")
        for p in participants:
            logger.info(f"  - {p.name} ({p.id}) AI: {p.is_ai}")
        
        # Find existing AI participant in the room
        existing_ai = next((p for p in participants if p.is_ai), None)
        human_participants = [p for p in participants if not p.is_ai]
        
        logger.info(f"👤 Human participants: {len(human_participants)}")
        logger.info(f"🤖 AI participants: {1 if existing_ai else 0}")
        
        # For human-human discussions, we need at least 2 humans
        # For human-AI discussions, we need 1 human and 1 AI
        if len(human_participants) >= 2:
            # Human-human discussion
            logger.info("👥 Human-human discussion detected")
            if len(roles) != 2:
                await sio.emit('error', {'message': 'Expected exactly 2 roles for role assignment'}, room=sid)
                return
                
            # Assign roles to the 2 humans
            roles_assignment = {}
            
            # User gets selected role (first human)
            user_role = roles[selected_role_index]
            roles_assignment[human_participants[0].id] = {
                "role": user_role['role'],
                "description": user_role['description']
            }
            
            # Second human gets the other role
            other_role_index = 1 - selected_role_index
            other_role = roles[other_role_index]
            roles_assignment[human_participants[1].id] = {
                "role": other_role['role'],
                "description": other_role['description']
            }
            
            logger.info(f"✅ Assigned roles to 2 humans:")
            logger.info(f"  - {human_participants[0].name}: {user_role['role']}")
            logger.info(f"  - {human_participants[1].name}: {other_role['role']}")
            
        elif len(human_participants) >= 1 and existing_ai:
            # Human-AI discussion
            logger.info("🤖 Human-AI discussion detected")
            
            # Assign roles based on user selection
            roles_assignment = {}
            
            # User gets selected role
            user_role = roles[selected_role_index]
            roles_assignment[human_participants[0].id] = {
                "role": user_role['role'],
                "description": user_role['description']
            }
            
            # AI gets the other role
            ai_role_index = 1 - selected_role_index
            ai_role = roles[ai_role_index]
            roles_assignment[existing_ai.id] = {
                "role": ai_role['role'],
                "description": ai_role['description']
            }
            
            logger.info(f"✅ Assigned roles to human and AI:")
            logger.info(f"  - {human_participants[0].name}: {user_role['role']}")
            logger.info(f"  - {existing_ai.name}: {ai_role['role']}")
            
        else:
            # Solo mode: 1 human, no AI in DB — assign roles using a virtual AI participant
            logger.info("🤖 Solo mode: assigning roles with virtual AI participant")
            user_role = roles[selected_role_index]
            ai_role_index = 1 - selected_role_index
            ai_role = roles[ai_role_index]
            virtual_ai_id = f"ai_participant_{session_id}"
            roles_assignment = {
                human_participants[0].id: {"role": user_role['role'], "description": user_role['description']},
                virtual_ai_id: {"role": ai_role['role'], "description": ai_role['description']},
            }
            from app.models.room import Participant as RoomParticipant
            from datetime import datetime as _dt
            existing_ai = RoomParticipant(id=virtual_ai_id, name="AI Participant", is_ai=True, joined_at=_dt.utcnow())
            logger.info(f"✅ Solo mode roles: User={user_role['role']}, AI={ai_role['role']}")
        
        # Update discussion state with roles
        group_discussion_service.assign_roles(session_id, roles_assignment)
        
        # Update room participants with roles
        room = await RoomManager.get_room_from_db(room_id)
        if room:
            # Update existing participants with roles
            for participant in room.participants:
                if participant.id in roles_assignment:
                    participant.role = roles_assignment[participant.id]['role']
                    participant.role_description = roles_assignment[participant.id]['description']
                    participant.is_ready = True  # Auto-ready for AI rooms
                    logger.info(f"✅ Updated participant {participant.name} with role: {participant.role}")
            
            room.current_topic = topic
            room.scenario = scenario
            
            await RoomManager.update_room_in_db(room)
        
        # Broadcast scenario and role assignments
        broadcast_data = {
            'session_id': session_id,
            'topic': topic,
            'scenario': scenario,
            'roles': roles_assignment,
            'user_role': user_role
        }
        
        # Add AI-specific data if there's an AI participant
        if existing_ai:
            ai_role_index = 1 - selected_role_index
            ai_role = roles[ai_role_index]
            broadcast_data['ai_role'] = ai_role
            broadcast_data['ai_participant_id'] = existing_ai.id
        else:
            # For human-human discussions, the "other" role goes to the second human
            other_role_index = 1 - selected_role_index
            other_role = roles[other_role_index]
            broadcast_data['other_human_role'] = other_role
            broadcast_data['other_human_id'] = human_participants[1].id if len(human_participants) >= 2 else None
        
        await sio.emit('scenario_generated', broadcast_data, room=room_id)
        
        # Broadcast updated participant list with roles
        updated_participants = await RoomManager.get_room_participants(room_id)
        await sio.emit('room_update', {
            'participants': [p.model_dump(mode='json') for p in updated_participants],
            'room_id': room_id,
            'scenario': scenario
        }, room=room_id)
        
        logger.info(f"✅ Role selection completed for room {room_id}")
        if existing_ai:
            ai_role_index = 1 - selected_role_index
            ai_role = roles[ai_role_index]
            logger.info(f"  User: {user_role['role']}, AI: {ai_role['role']}")
        else:
            other_role_index = 1 - selected_role_index
            other_role = roles[other_role_index]
            logger.info(f"  User: {user_role['role']}, Other Human: {other_role['role']}")
        
    except Exception as e:
        logger.error(f"❌ Error handling role selection: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to select role: {str(e)}'}, room=sid)

@sio.event
async def start_group_discussion(sid, data):
    """Start a group discussion with roles"""
    try:
        logger.info(f"=== START GROUP DISCUSSION EVENT ===")
        
        room_id = active_connections[sid].get('room_id')
        session_id = data.get('session_id')
        topic = data.get('topic', 'General Discussion')
        
        if not room_id or not session_id:
            await sio.emit('error', {'message': 'Missing room_id or session_id'}, room=sid)
            return
        
        # Start the discussion
        discussion_state = group_discussion_service.start_discussion(session_id)
        
        # Broadcast discussion start
        await sio.emit('discussion-started', {
            'session_id': session_id,
            'topic': topic,
            'phase': discussion_state.phase,
            'current_turn': discussion_state.current_turn
        }, room=room_id)
        
        logger.info(f"✅ Group discussion started for session {session_id}")
        
    except Exception as e:
        logger.error(f"❌ Error starting group discussion: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to start discussion: {str(e)}'}, room=sid)

@sio.event
async def end_group_discussion(sid, data):
    """Handle ending group discussion and generate final analysis"""
    try:
        logger.info(f"🏁 Ending group discussion from {sid}")
        
        session_id = data.get('session_id')
        room_id = data.get('room_id')
        
        if not session_id or not room_id:
            await sio.emit('error', {'message': 'Missing session_id or room_id'}, room=sid)
            return
        
        # Mark discussion as completed
        discussion_state = group_discussion_service.complete_discussion(session_id)
        
        if not discussion_state:
            await sio.emit('error', {'message': 'Discussion session not found'}, room=sid)
            return
        
        logger.info(f"📊 Generating final analysis for session {session_id}")
        
        # Generate comprehensive AI analysis
        final_analysis = await group_discussion_service.generate_final_analysis(session_id)
        
        if final_analysis:
            # Broadcast final analysis to all participants in the room
            await sio.emit('discussion_analysis', {
                'session_id': session_id,
                'analysis': final_analysis,
                'discussion_summary': {
                    'topic': discussion_state.topic,
                    'category': discussion_state.category.value if discussion_state.category else None,
                    'total_contributions': len([c for c in discussion_state.contributions if c.participant_id != discussion_state.ai_facilitator_id]),
                    'duration_minutes': ((discussion_state.updated_at - discussion_state.created_at).total_seconds() / 60),
                    'participants': [discussion_state.participant_names.get(pid, 'Unknown') for pid in discussion_state.participants if pid != discussion_state.ai_facilitator_id]
                }
            }, room=room_id)
            
            logger.info(f"✅ Final analysis sent to room {room_id}")
        else:
            await sio.emit('error', {'message': 'Failed to generate discussion analysis'}, room=room_id)
        
    except Exception as e:
        logger.error(f"❌ Error ending group discussion: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to end discussion: {str(e)}'}, room=sid)

@sio.event
async def set_coaching_mode(sid, data):
    """Set coaching mode for JAM session"""
    try:
        logger.info(f"=== SET COACHING MODE EVENT ===")
        
        session_id = data.get('session_id')
        mode = data.get('mode')
        
        if not session_id or not mode:
            await sio.emit('error', {'message': 'Missing session_id or mode'}, room=sid)
            return
        
        # Import JAM service
        from app.services.modes.jam_mode import jam_service, JAMCoachingMode
        
        # Set coaching mode
        coaching_mode = JAMCoachingMode(mode)
        jam_state = jam_service.set_coaching_mode(session_id, coaching_mode)
        
        # Confirm to user
        await sio.emit('coaching-mode-set', {
            'session_id': session_id,
            'mode': mode
        }, room=sid)
        
        logger.info(f"✅ Coaching mode set to {mode} for session {session_id}")
        
    except Exception as e:
        logger.error(f"❌ Error setting coaching mode: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to set coaching mode: {str(e)}'}, room=sid)

@sio.event
async def set_difficulty_level(sid, data):
    """Set difficulty level for JAM session"""
    try:
        logger.info(f"=== SET DIFFICULTY LEVEL EVENT ===")
        
        session_id = data.get('session_id')
        level = data.get('level')
        
        if not session_id or level is None:
            await sio.emit('error', {'message': 'Missing session_id or level'}, room=sid)
            return
        
        from app.services.modes.jam_mode import jam_service
        
        # Update difficulty level
        jam_state = jam_service.active_sessions.get(session_id)
        if jam_state:
            jam_state.difficulty_level = level
            jam_state.updated_at = datetime.utcnow()
        
        # Confirm to user
        await sio.emit('difficulty-level-set', {
            'session_id': session_id,
            'level': level
        }, room=sid)
        
        logger.info(f"✅ Difficulty level set to {level} for session {session_id}")
        
    except Exception as e:
        logger.error(f"❌ Error setting difficulty level: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to set difficulty level: {str(e)}'}, room=sid)

@sio.event
async def generate_adaptive_topic(sid, data):
    """Generate adaptive topic for JAM session"""
    try:
        logger.info(f"=== GENERATE ADAPTIVE TOPIC EVENT ===")
        
        session_id = data.get('session_id')
        difficulty_level = data.get('difficulty_level')
        
        if not session_id:
            await sio.emit('error', {'message': 'Missing session_id'}, room=sid)
            return
        
        from app.services.modes.jam_mode import jam_service
        
        # Generate topic
        topic = jam_service.generate_adaptive_topic(session_id, difficulty_level)
        
        # Set the topic
        jam_state = jam_service.set_topic(session_id, topic)
        
        # Send topic to user
        await sio.emit('topic-generated', {
            'session_id': session_id,
            'topic': topic,
            'difficulty_level': jam_state.difficulty_level
        }, room=sid)
        
        logger.info(f"✅ Generated topic '{topic}' for session {session_id}")
        
    except Exception as e:
        logger.error(f"Error generating topic: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to generate topic: {str(e)}'}, room=sid)

# ===== READING MODE EVENTS =====

@sio.event
async def create_reading_session(sid, data):
    """Create a new reading session"""
    try:
        logger.info(f"=== CREATE READING SESSION EVENT ===")
        
        room_id = active_connections[sid].get('room_id')
        participant_id = active_connections[sid].get('participant_id')
        participant_name = active_connections[sid].get('participant_name')
        difficulty_level = data.get('difficulty_level', 'beginner')
        
        if not room_id or not participant_id:
            await sio.emit('error', {'message': 'Missing room_id or participant_id'}, room=sid)
            return
        
        from app.services.modes.reading_mode import reading_service, ReadingDifficulty
        
        # Create session
        import uuid
        session_id = f"reading_{room_id}_{int(datetime.utcnow().timestamp())}"
        
        reading_state = reading_service.create_session(
            room_id=room_id,
            session_id=session_id,
            participant_id=participant_id,
            participant_name=participant_name,
            difficulty_level=ReadingDifficulty(difficulty_level)
        )
        
        # Send confirmation
        await sio.emit('reading-session-created', {
            'session_id': session_id,
            'reading_state': reading_state.model_dump()
        }, room=sid)
        
        logger.info(f"Reading session created: {session_id}")
        
    except Exception as e:
        logger.error(f"Error creating reading session: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to create reading session: {str(e)}'}, room=sid)

@sio.event
async def generate_reading_passage(sid, data):
    """Generate adaptive reading passage"""
    try:
        logger.info(f"=== GENERATE READING PASSAGE EVENT ===")
        
        session_id = data.get('session_id')
        
        if not session_id:
            await sio.emit('error', {'message': 'Missing session_id'}, room=sid)
            return
        
        from app.services.modes.reading_mode import reading_service, ReadingGenre
        
        # Generate passage
        passage = reading_service.generate_adaptive_passage(session_id)
        
        # Set the passage
        reading_state = reading_service.set_passage(
            session_id,
            passage,
            ReadingGenre.NON_FICTION
        )
        
        # Send passage to user
        await sio.emit('reading-passage-generated', {
            'session_id': session_id,
            'passage': passage,
            'reading_state': reading_state.model_dump()
        }, room=sid)
        
        logger.info(f"Generated reading passage for session {session_id}")
        
    except Exception as e:
        logger.error(f"Error generating reading passage: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to generate passage: {str(e)}'}, room=sid)

@sio.event
async def start_reading_attempt(sid, data):
    """Start a reading attempt"""
    try:
        logger.info(f"=== START READING ATTEMPT EVENT ===")
        
        session_id = data.get('session_id')
        
        if not session_id:
            await sio.emit('error', {'message': 'Missing session_id'}, room=sid)
            return
        
        from app.services.modes.reading_mode import reading_service
        
        # Start attempt
        reading_state = reading_service.start_reading_attempt(session_id)
        
        # Send confirmation
        await sio.emit('reading-attempt-started', {
            'session_id': session_id,
            'attempt_number': reading_state.current_attempt.attempt_number,
            'passage': reading_state.current_attempt.passage,
            'word_count': reading_state.current_attempt.word_count,
            'reading_state': reading_state.model_dump()
        }, room=sid)
        
        logger.info(f"Started reading attempt for session {session_id}")
        
    except Exception as e:
        logger.error(f"Error starting reading attempt: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to start attempt: {str(e)}'}, room=sid)

@sio.event
async def complete_reading_attempt(sid, data):
    """Complete reading attempt and get analysis"""
    try:
        logger.info(f"=== COMPLETE READING ATTEMPT EVENT ===")
        
        session_id = data.get('session_id')
        transcript = data.get('transcript', '')
        reading_duration = data.get('reading_duration', 0)
        
        if not session_id:
            await sio.emit('error', {'message': 'Missing session_id'}, room=sid)
            return
        
        from app.services.modes.reading_mode import reading_service
        
        # Complete attempt
        reading_state = reading_service.complete_reading_attempt(
            session_id,
            transcript,
            reading_duration
        )
        
        # Generate feedback
        feedback = reading_service.analyze_reading_performance(session_id)
        
        # Send results
        await sio.emit('reading-attempt-completed', {
            'session_id': session_id,
            'reading_state': reading_state.model_dump(),
            'feedback': feedback.model_dump() if feedback else None
        }, room=sid)
        
        logger.info(f"Completed reading attempt for session {session_id}")
        
    except Exception as e:
        logger.error(f"Error completing reading attempt: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to complete attempt: {str(e)}'}, room=sid)

@sio.event
async def reset_reading_session(sid, data):
    """Reset reading session for new passage"""
    try:
        logger.info(f"=== RESET READING SESSION EVENT ===")
        
        session_id = data.get('session_id')
        
        if not session_id:
            await sio.emit('error', {'message': 'Missing session_id'}, room=sid)
            return
        
        from app.services.modes.reading_mode import reading_service, ReadingPhase
        
        # Reset session
        reading_state = reading_service.get_session_state(session_id)
        if reading_state:
            reading_state.phase = ReadingPhase.SETUP
            reading_state.current_passage = None
            reading_state.current_attempt = None
            reading_state.session_feedback = None
            reading_state.updated_at = datetime.utcnow()
        
        # Send confirmation
        await sio.emit('reading-session-reset', {
            'session_id': session_id,
            'reading_state': reading_state.model_dump() if reading_state else None
        }, room=sid)
        
        logger.info(f"Reset reading session {session_id}")
        
    except Exception as e:
        logger.error(f"Error resetting reading session: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to reset session: {str(e)}'}, room=sid)

@sio.event
async def start_jam_attempt(sid, data):
    """Start a JAM speaking attempt"""
    try:
        logger.info(f"=== START JAM ATTEMPT EVENT ===")
        
        session_id = data.get('session_id')
        
        if not session_id:
            await sio.emit('error', {'message': 'Missing session_id'}, room=sid)
            return
        
        from app.services.modes.jam_mode import jam_service
        
        # Start attempt
        jam_state = jam_service.start_attempt(session_id)
        
        # Notify user
        await sio.emit('jam-phase-change', {
            'session_id': session_id,
            'phase': jam_state.phase,
            'attempt_number': jam_state.current_attempt.attempt_number if jam_state.current_attempt else 0
        }, room=sid)
        
        logger.info(f"✅ Started JAM attempt for session {session_id}")
        
    except Exception as e:
        logger.error(f"❌ Error starting JAM attempt: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to start attempt: {str(e)}'}, room=sid)

@sio.event
async def end_jam_attempt(sid, data):
    """End a JAM speaking attempt"""
    try:
        logger.info(f"=== END JAM ATTEMPT EVENT ===")
        
        session_id = data.get('session_id')
        duration = data.get('duration', 0)
        transcript = data.get('transcript', '')
        
        if not session_id:
            await sio.emit('error', {'message': 'Missing session_id'}, room=sid)
            return
        
        from app.services.modes.jam_mode import jam_service
        
        # End attempt
        jam_state = jam_service.end_attempt(session_id, transcript, duration)
        
        # Generate feedback
        feedback = jam_service.generate_feedback(session_id)
        
        # Send results
        await sio.emit('jam-attempt-completed', {
            'session_id': session_id,
            'phase': jam_state.phase,
            'attempt': jam_state.attempts[-1].model_dump(mode='json') if jam_state.attempts else None,
            'feedback': feedback.model_dump(mode='json')
        }, room=sid)
        
        logger.info(f"✅ Completed JAM attempt for session {session_id}")
        
    except Exception as e:
        logger.error(f"❌ Error ending JAM attempt: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to end attempt: {str(e)}'}, room=sid)

@sio.event
async def speech_start(sid, data):
    """Handle speech start event with participant status update"""
    try:
        logger.info(f"=== SPEECH START EVENT ===")
        logger.info(f"SID: {sid}")
        logger.info(f"Data: {data}")
        
        room_id = active_connections[sid].get('room_id')
        participant_id = active_connections[sid].get('participant_id')
        
        logger.info(f"Room ID: {room_id}, Participant ID: {participant_id}")
        
        if room_id and participant_id:
            # Update participant speaking status
            await RoomManager.update_participant_status(room_id, participant_id, is_speaking=True)
            
            # Notify other participants that this user started speaking
            await sio.emit('participant-speaking', {
                'participant_id': participant_id,
                'is_speaking': True,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room_id, skip_sid=sid)
            
            logger.info(f"✅ Participant {participant_id} started speaking in room {room_id}")
        else:
            logger.warning("Cannot start speech - no room_id or participant_id")
    
    except Exception as e:
        logger.error(f"Error handling speech start: {e}", exc_info=True)

# Also register with hyphenated name
@sio.on('speech-start')
async def speech_start_hyphen(sid, data):
    """Handle speech-start event (hyphenated version)"""
    logger.info(f"=== SPEECH START EVENT (via hyphen handler) ===")
    logger.info(f"SID: {sid}")
    logger.info(f"Data: {data}")
    logger.info(f"Active connections: {sid in active_connections}")
    if sid in active_connections:
        logger.info(f"Connection data: {active_connections[sid]}")
    await speech_start(sid, data)

async def check_and_trigger_ai_response(room_id: str, participant_id: str, transcript_text: str):
    """Check if AI response should be triggered and generate it"""
    try:
        logger.info(f"Checking if AI response needed for room {room_id}")
        
        # Get room data to check if there are AI participants
        room = await RoomManager.get_room_from_db(room_id)
        if not room:
            logger.warning(f"Room {room_id} not found for AI response check")
            return
        
        # Check if there are AI participants in the room
        ai_participants = [p for p in room.participants if p.is_ai]
        if not ai_participants:
            logger.info(f"No AI participants in room {room_id}, skipping AI response")
            return
        
        # Check if the speaker is human (not AI)
        if participant_id.startswith('ai_') or next((p for p in room.participants if p.id == participant_id and p.is_ai), None):
            logger.info(f"Speaker {participant_id} is AI, skipping AI response")
            return
        
        # Check if transcript is meaningful
        if len(transcript_text.strip()) < 5:
            logger.info(f"Transcript too short for AI response: '{transcript_text}'")
            return
        
        logger.info(f"Triggering AI response for transcript: '{transcript_text[:50]}...' (Mode: {room.mode})")
        
        if room.mode == RoomMode.DEBATE:
            # Handle AI opponent in debate
            try:
                from app.api.routes.modes.debate import active_debates, debate_service
                session_id = next((sid for sid, d in active_debates.items() if d.room_id == room_id), None)
                
                if not session_id:
                    logger.info("Debate session not found, skipping AI response")
                    return
                
                ai_arg = await debate_service.generate_ai_argument(session_id)
                if ai_arg:
                    ai_player = next((p for p in room.participants if p.is_ai and not p.id.startswith('ai_judge')), ai_participants[0])
                    ai_response_data = {
                        'participant_id': ai_player.id,
                        'participant_name': ai_player.name,
                        'text': ai_arg.strip(),
                        'timestamp': datetime.utcnow().isoformat(),
                        'is_ai_response': True,
                        'room_mode': 'debate'
                    }
                    await sio.emit('transcript', ai_response_data, room=room_id)
                    await sio.emit('ai-response', ai_response_data, room=room_id)
                    logger.info(f"✅ AI Debate argument sent: '{ai_arg[:100]}...'")
            except Exception as e:
                logger.error(f"Error in AI debate response: {e}")

        elif room.mode == RoomMode.GROUP_DISCUSSION:
            # Handle AI participant in group discussion
            try:
                active_sessions = group_discussion_service.active_discussions
                matching_session_id = next((sid for sid in active_sessions.keys() if room_id in sid), None)
                
                if not matching_session_id:
                    logger.warning(f"No matching session found for room {room_id}")
                    return
                
                ai_response = group_discussion_service.generate_ai_participant_response(
                    session_id=matching_session_id,
                    context=transcript_text,
                    trigger_type="response"
                )
                
                if ai_response and ai_response.strip():
                    ai_participant = next((p for p in room.participants if p.is_ai), ai_participants[0])
                    ai_response_data = {
                        'participant_id': ai_participant.id,
                        'participant_name': ai_participant.name,
                        'text': ai_response.strip(),
                        'confidence': 1.0,
                        'processing_time': 0.5,
                        'timestamp': datetime.utcnow().isoformat(),
                        'is_ai_response': True
                    }
                    await sio.emit('transcript', ai_response_data, room=room_id)
                    await sio.emit('ai-response', ai_response_data, room=room_id)
                    logger.info(f"AI response sent: '{ai_response[:50]}...'")
            except Exception as ai_error:
                logger.error(f"Failed to generate AI response: {ai_error}")
                
    except Exception as e:
        logger.error(f"Error in check_and_trigger_ai_response: {e}")

@sio.event
async def speech_data(sid, data):
    """Handle real-time speech data with live streaming"""
    try:
        logger.info(f"=== LIVE SPEECH DATA EVENT ===")
        logger.info(f"SID: {sid}")
        logger.info(f"Data keys: {data.keys() if isinstance(data, dict) else 'Not a dict'}")
        
        # Try to get room_id and participant_id from data first, then fallback to active_connections
        room_id = data.get('room_id') or active_connections[sid].get('room_id')
        participant_id = data.get('participant_id') or active_connections[sid].get('participant_id')
        
        logger.info(f"Room ID: {room_id}, Participant ID: {participant_id}")
        
        if not room_id or not participant_id:
            logger.warning("No room_id or participant_id found")
            logger.warning(f"Available data keys: {list(data.keys()) if isinstance(data, dict) else 'No keys'}")
            logger.warning(f"Active connection info: {active_connections.get(sid, 'No connection info')}")
            return
        
        # Try multiple keys for audio data
        audio_data = None
        for key in ['audio_data', 'audioData', 'data', 'audio']:
            if key in data:
                audio_data = data[key]
                logger.info(f"Found audio data with key: {key}")
                break
        
        if not audio_data:
            logger.warning("No audio data found in event")
            logger.warning(f"Available keys: {list(data.keys()) if isinstance(data, dict) else 'No keys'}")
            return

        # Convert to bytes if needed
        if not isinstance(audio_data, bytes):
            if isinstance(audio_data, list):
                try:
                    # Ensure all elements are integers in valid byte range (0-255)
                    if all(isinstance(x, int) and 0 <= x <= 255 for x in audio_data):
                        audio_data = bytes(audio_data)
                        logger.info(f"Converted list to bytes: {len(audio_data)} bytes")
                    else:
                        logger.error("Audio data list contains invalid byte values")
                        return
                except Exception as e:
                    logger.error(f"Failed to convert list to bytes: {e}")
                    return
            elif isinstance(audio_data, str):
                try:
                    # Try base64 decode
                    import base64
                    audio_data = base64.b64decode(audio_data)
                    logger.info(f"Decoded base64 string to bytes: {len(audio_data)} bytes")
                except Exception as e:
                    logger.error(f"Failed to decode base64 string: {e}")
                    return
            else:
                logger.warning(f"Unexpected audio data type: {type(audio_data)}")
                return
        
        logger.info(f"Live audio chunk size: {len(audio_data)} bytes")
        
        # LIVE STREAMING: Broadcast audio chunks immediately to other participants
        if room_id and participant_id:
            try:
                participants = await RoomManager.get_room_participants(room_id)
                other_participants = [p for p in participants if p.id != participant_id]
                
                if other_participants:
                    # Get participant name and audio format from data
                    participant_name = (data.get('participant_name') or 
                                      active_connections[sid].get('participant_name') or 
                                      'Unknown')
                    audio_format = data.get('audio_format', 'audio/webm')  # Default to webm if not specified
                    
                    # Broadcast live audio chunk to other participants immediately
                    live_audio_data = {
                        'participant_id': participant_id,
                        'participant_name': participant_name,
                        'audio_data': list(audio_data) if isinstance(audio_data, bytes) else audio_data,  # Convert bytes to list for JSON serialization
                        'audio_format': audio_format,  # Include the original format
                        'timestamp': datetime.utcnow().isoformat(),
                        'chunk_index': data.get('chunk_index', 0),
                        'is_live_chunk': True  # Flag to indicate this is a live streaming chunk
                    }
                    
                    logger.info(f"🔴 LIVE: Broadcasting audio chunk with format {audio_format}, size: {len(audio_data)} bytes")
                    
                    # Send to each other participant individually by finding their socket IDs
                    for participant in other_participants:
                        # Find socket IDs for this participant by checking active_connections
                        participant_sockets = [sid for sid, info in active_connections.items() 
                                             if info.get('participant_id') == participant.id]
                        
                        for participant_sid in participant_sockets:
                            await sio.emit('live_audio_chunk', live_audio_data, room=participant_sid)
                    
                    logger.info(f"🔴 LIVE: Broadcasted audio chunk from {participant_id} ({participant_name}) to {len(other_participants)} participants")
                    
            except Exception as e:
                logger.error(f"Failed to broadcast live audio: {e}")
        
        # For transcription, only process larger chunks to avoid too much processing
        if len(audio_data) > 5000:  # Only process chunks > 5KB for transcription
            logger.info("Processing audio chunk for transcription...")
            
            # Initialize speech service
            from app.services.speech_service import SpeechService
            speech_service = SpeechService()
            
            # Do transcription for larger chunks
            transcription_result = await speech_service.transcribe_audio(audio_data)
            
            logger.info(f"Transcription result: {transcription_result}")
            
            # If we got a transcript, broadcast it
            if transcription_result.get('has_speech') and transcription_result.get('text'):
                transcript_data = {
                    'participant_id': participant_id,
                    'participant_name': active_connections[sid].get('participant_name'),
                    'text': transcription_result['text'],
                    'confidence': transcription_result.get('confidence', 0.0),
                    'processing_time': transcription_result.get('processing_time', 0),
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                # Broadcast transcript to all room participants
                await sio.emit('transcript', transcript_data, room=room_id)
                
                logger.info(f"✅ Transcript from {participant_id} in room {room_id}: {transcription_result['text']}")
                
                # Trigger AI response for group discussions
                await check_and_trigger_ai_response(room_id, participant_id, transcription_result['text'])
        
    except Exception as e:
        logger.error(f"❌ Error processing live speech data: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to process speech data: {str(e)}'}, room=sid)


# Also register with hyphenated name for compatibility
@sio.on('speech-data')
async def speech_data_hyphen(sid, data):
    """Handle speech-data event (hyphenated version)"""
    await speech_data(sid, data)

# Also register with underscore name for compatibility
@sio.on('speech_data')
async def speech_data_underscore(sid, data):
    """Handle speech_data event (underscore version)"""
    await speech_data(sid, data)


@sio.event
async def live_voice_data(sid, data):
    """Handle live voice communication data - no transcription, just real-time audio streaming"""
    try:
        logger.info(f"=== LIVE VOICE DATA EVENT ===")
        logger.info(f"SID: {sid}")
        
        # Try to get room_id and participant_id from data first, then fallback to active_connections
        room_id = data.get('room_id') or active_connections[sid].get('room_id')
        participant_id = data.get('participant_id') or active_connections[sid].get('participant_id')
        
        logger.info(f"Room ID: {room_id}, Participant ID: {participant_id}")
        
        if not room_id or not participant_id:
            logger.warning("No room_id or participant_id found for live voice")
            return
        
        # Try multiple keys for audio data
        audio_data = None
        for key in ['audio_data', 'audioData', 'data', 'audio']:
            if key in data:
                audio_data = data[key]
                logger.info(f"Found audio data with key: {key}")
                break
        
        if not audio_data:
            logger.warning("No audio data found in live voice event")
            return

        # Convert to bytes if needed
        if not isinstance(audio_data, bytes):
            if isinstance(audio_data, list):
                try:
                    # Ensure all elements are integers in valid byte range (0-255)
                    if all(isinstance(x, int) and 0 <= x <= 255 for x in audio_data):
                        audio_data = bytes(audio_data)
                        logger.info(f"Converted list to bytes: {len(audio_data)} bytes")
                    else:
                        logger.error("Audio data list contains invalid byte values")
                        return
                except Exception as e:
                    logger.error(f"Failed to convert list to bytes: {e}")
                    return
            else:
                logger.warning(f"Unexpected audio data type: {type(audio_data)}")
                return
        
        logger.info(f"🔴 LIVE VOICE: Audio chunk size: {len(audio_data)} bytes")
        
        # LIVE VOICE STREAMING: Broadcast audio chunks immediately to other participants (NO TRANSCRIPTION)
        if room_id and participant_id:
            try:
                participants = await RoomManager.get_room_participants(room_id)
                other_participants = [p for p in participants if p.id != participant_id]
                
                if other_participants:
                    # Get participant name and audio format from data
                    participant_name = (data.get('participant_name') or 
                                      active_connections[sid].get('participant_name') or 
                                      'Unknown')
                    audio_format = data.get('audio_format', 'audio/webm')  # Default to webm if not specified
                    
                    # Broadcast live voice audio chunk to other participants immediately
                    live_voice_data = {
                        'participant_id': participant_id,
                        'participant_name': participant_name,
                        'audio_data': list(audio_data) if isinstance(audio_data, bytes) else audio_data,  # Convert bytes to list for JSON serialization
                        'audio_format': audio_format,  # Include the original format
                        'timestamp': datetime.utcnow().isoformat(),
                        'chunk_index': data.get('chunk_index', 0),
                        'is_live_voice': True  # Flag to indicate this is live voice communication
                    }
                    
                    logger.info(f"🔴 LIVE VOICE: Broadcasting audio chunk with format {audio_format}, size: {len(audio_data)} bytes")
                    
                    # Send to each other participant individually by finding their socket IDs
                    for participant in other_participants:
                        # Find socket IDs for this participant by checking active_connections
                        participant_sockets = [sid for sid, info in active_connections.items() 
                                             if info.get('participant_id') == participant.id]
                        
                        for participant_sid in participant_sockets:
                            await sio.emit('live_voice_chunk', live_voice_data, room=participant_sid)
                    
                    logger.info(f"🔴 LIVE VOICE: Broadcasted voice chunk from {participant_id} ({participant_name}) to {len(other_participants)} participants")
                    
            except Exception as e:
                logger.error(f"Failed to broadcast live voice: {e}")
        
        # NO TRANSCRIPTION FOR LIVE VOICE - this is purely for real-time communication
        
    except Exception as e:
        logger.error(f"❌ Error processing live voice data: {e}", exc_info=True)
        await sio.emit('error', {'message': f'Failed to process live voice data: {str(e)}'}, room=sid)


@sio.event
async def speech_end(sid, data):
    """Handle speech end event with participant status update"""
    try:
        logger.info(f"=== SPEECH END EVENT ===")
        logger.info(f"SID: {sid}")
        logger.info(f"Data: {data}")
        
        room_id = active_connections[sid].get('room_id')
        participant_id = active_connections[sid].get('participant_id')
        
        logger.info(f"Room ID: {room_id}, Participant ID: {participant_id}")
        
        if room_id and participant_id:
            # Update participant speaking status
            await RoomManager.update_participant_status(room_id, participant_id, is_speaking=False)
            
            # Notify other participants that this user stopped speaking
            await sio.emit('participant-speaking', {
                'participant_id': participant_id,
                'is_speaking': False,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room_id, skip_sid=sid)
            
            logger.info(f"✅ Participant {participant_id} stopped speaking in room {room_id}")
        else:
            logger.warning("Cannot end speech - no room_id or participant_id")
    
    except Exception as e:
        logger.error(f"Error handling speech end: {e}", exc_info=True)


# Also register with hyphenated name
@sio.on('speech-end')
async def speech_end_hyphen(sid, data):
    """Handle speech-end event (hyphenated version)"""
    await speech_end(sid, data)


@sio.event
async def transcript(sid, data):
    """Handle transcript sharing with enhanced room management"""
    try:
        room_id = active_connections[sid].get('room_id')
        participant_id = active_connections[sid].get('participant_id')
        participant_name = active_connections[sid].get('participant_name')
        
        transcript_data = {
            'participant_id': participant_id,
            'participant_name': participant_name,
            'text': data.get('text', ''),
            'confidence': data.get('confidence', 0.0),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if room_id:
            # Broadcast transcript to all room participants
            await sio.emit('transcript', transcript_data, room=room_id)
            
            logger.info(f"Transcript from {participant_id} ({participant_name}) in room {room_id}: {transcript_data['text'][:50]}...")
    
    except Exception as e:
        logger.error(f"Error handling transcript: {e}")


@sio.event
async def ai_response(sid, data):
    """Handle AI response generation request"""
    try:
        room_id = active_connections[sid].get('room_id')
        
        # Initialize AI service
        ai_service = AIService()
        
        # Generate AI response
        response = await ai_service.generate_response(
            prompt=data.get('prompt', ''),
            context=data.get('context', ''),
            mode=data.get('mode', 'general')
        )
        
        ai_response_data = {
            'participant_id': 'ai_host',
            'participant_name': 'AI Host',
            'text': response['text'],
            'timestamp': datetime.utcnow().isoformat(),
            'response_time': response['response_time']
        }
        
        if room_id:
            # Broadcast AI response to room
            await sio.emit('ai-response', ai_response_data, room=room_id)
            
            logger.info(f"AI response sent to room {room_id}")
    
    except Exception as e:
        logger.error(f"Error generating AI response: {e}")
        await sio.emit('error', {'message': f'AI response failed: {str(e)}'}, room=sid)


@sio.event
async def room_state_update(sid, data):
    """Handle room state updates with enhanced synchronization"""
    try:
        room_id = data.get('room_id')
        state_update = data.get('state', {})
        
        if room_id:
            # Get current room from database
            room = await RoomManager.get_room_from_db(room_id)
            if not room:
                await sio.emit('error', {'message': 'Room not found'}, room=sid)
                return
            
            # Update specific fields if provided
            if 'current_topic' in state_update:
                room.current_topic = state_update['current_topic']
            if 'current_round' in state_update:
                room.current_round = state_update['current_round']
            if 'is_active' in state_update:
                room.is_active = state_update['is_active']
            
            # Update database
            await RoomManager.update_room_in_db(room)
            
            # Update Redis cache with JSON-serializable data
            await redis_client.set_room_state(room_id, room.model_dump(mode='json'))
            
            # Synchronize room state across all participants
            await RoomManager.synchronize_room_state(room_id)
    
    except Exception as e:
        logger.error(f"Error updating room state: {e}")
        await sio.emit('error', {'message': f'Failed to update room state: {str(e)}'}, room=sid)


# Helper function to get participant info
async def get_participant_info(sid: str) -> Optional[Dict[str, Any]]:
    """Get participant information by socket ID"""
    return active_connections.get(sid)




@sio.event
async def start_streaming_transcription(sid, data):
    """Start a streaming transcription session for a participant"""
    try:
        room_id = active_connections[sid].get('room_id')
        participant_id = active_connections[sid].get('participant_id')
        
        if not room_id or not participant_id:
            await sio.emit('error', {'message': 'Not in a room'}, room=sid)
            return
        
        # Initialize speech service and create streaming pipeline
        speech_service = SpeechService()
        pipeline = await speech_service.create_streaming_pipeline(participant_id, room_id)
        
        # Store pipeline in connection data
        active_connections[sid]['streaming_pipeline'] = pipeline
        
        await sio.emit('streaming-transcription-started', {
            'participant_id': participant_id,
            'room_id': room_id,
            'status': 'ready',
            'timestamp': datetime.utcnow().isoformat()
        }, room=sid)
        
        logger.info(f"Started streaming transcription for participant {participant_id} in room {room_id}")
        
    except Exception as e:
        logger.error(f"Error starting streaming transcription: {e}")
        await sio.emit('error', {'message': f'Failed to start streaming transcription: {str(e)}'}, room=sid)

@sio.event
async def stop_streaming_transcription(sid, data):
    """Stop streaming transcription session and finalize any remaining audio"""
    try:
        room_id = active_connections[sid].get('room_id')
        participant_id = active_connections[sid].get('participant_id')
        pipeline = active_connections[sid].get('streaming_pipeline')
        
        if pipeline:
            # Finalize any remaining audio
            final_result = await pipeline.finalize()
            
            if final_result and final_result.get('text'):
                # Send final transcript
                transcript_data = {
                    'participant_id': participant_id,
                    'participant_name': active_connections[sid].get('participant_name'),
                    'text': final_result['text'],
                    'confidence': final_result.get('confidence', 0.0),
                    'is_final': True,
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                await sio.emit('transcript', transcript_data, room=room_id)
            
            # Remove pipeline from connection data
            del active_connections[sid]['streaming_pipeline']
        
        await sio.emit('streaming-transcription-stopped', {
            'participant_id': participant_id,
            'room_id': room_id,
            'timestamp': datetime.utcnow().isoformat()
        }, room=sid)
        
        logger.info(f"Stopped streaming transcription for participant {participant_id}")
        
    except Exception as e:
        logger.error(f"Error stopping streaming transcription: {e}")

@sio.event
async def streaming_audio_chunk(sid, data):
    """Handle streaming audio chunks for real-time transcription"""
    try:
        pipeline = active_connections[sid].get('streaming_pipeline')
        
        if not pipeline:
            await sio.emit('error', {'message': 'No active streaming session'}, room=sid)
            return
        
        audio_data = data.get('audio_data')
        if not audio_data:
            return
        
        # Process audio chunk through streaming pipeline
        result = await pipeline.process_audio_chunk(
            audio_data if isinstance(audio_data, bytes) else audio_data.encode()
        )
        
        # If we got a transcript, broadcast it
        if result and result.get('text'):
            room_id = active_connections[sid].get('room_id')
            participant_id = active_connections[sid].get('participant_id')
            
            transcript_data = {
                'participant_id': participant_id,
                'participant_name': active_connections[sid].get('participant_name'),
                'text': result['text'],
                'confidence': result.get('confidence', 0.0),
                'processing_time': result.get('processing_time', 0),
                'is_streaming': True,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Broadcast to room
            await sio.emit('transcript', transcript_data, room=room_id)
            
            # Send confirmation to sender
            await sio.emit('streaming-transcript-sent', {
                'text': result['text'],
                'confidence': result.get('confidence', 0.0),
                'timestamp': datetime.utcnow().isoformat()
            }, room=sid)
    
    except Exception as e:
        logger.error(f"Error processing streaming audio chunk: {e}")
        await sio.emit('error', {'message': f'Streaming audio processing failed: {str(e)}'}, room=sid)

@sio.event
async def analyze_speech_metrics(sid, data):
    """Analyze speech metrics for immediate feedback"""
    try:
        room_id = active_connections[sid].get('room_id')
        participant_id = active_connections[sid].get('participant_id')
        
        if not room_id or not participant_id:
            await sio.emit('error', {'message': 'Not in a room'}, room=sid)
            return
        
        audio_data = data.get('audio_data')
        transcript = data.get('transcript', '')
        
        if not audio_data:
            await sio.emit('error', {'message': 'No audio data provided'}, room=sid)
            return
        
        # Initialize speech service
        speech_service = SpeechService()
        
        # Calculate comprehensive basic metrics
        metrics = await speech_service.calculate_basic_metrics(
            audio_data if isinstance(audio_data, bytes) else audio_data.encode(),
            transcript
        )
        
        # Send metrics back to participant
        await sio.emit('speech-metrics', {
            'participant_id': participant_id,
            'metrics': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }, room=sid)
        
        # Optionally broadcast summary to room (for group feedback)
        if data.get('share_with_room', False):
            summary = {
                'participant_id': participant_id,
                'participant_name': active_connections[sid].get('participant_name'),
                'overall_score': metrics.get('immediate_feedback', {}).get('overall_score', 0.0),
                'speaking_rate': metrics.get('speaking_rate', {}).get('words_per_minute', 0),
                'volume_level': metrics.get('volume', {}).get('average_volume_db', -60),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            await sio.emit('participant-metrics-summary', summary, room=room_id, skip_sid=sid)
        
        logger.info(f"Speech metrics analyzed for participant {participant_id} in room {room_id}")
        
    except Exception as e:
        logger.error(f"Error analyzing speech metrics: {e}")
        await sio.emit('error', {'message': f'Speech metrics analysis failed: {str(e)}'}, room=sid)

@sio.event
async def get_room_info(sid, data):
    """Get current room information"""
    try:
        room_id = data.get('room_id')
        
        if not room_id:
            await sio.emit('error', {'message': 'Missing room_id'}, room=sid)
            return
        
        room = await RoomManager.get_room_from_db(room_id)
        if not room:
            await sio.emit('error', {'message': 'Room not found'}, room=sid)
            return
        
        # Send room information
        await sio.emit('room-info', {
            'room_id': room_id,
            'name': room.name,
            'mode': room.mode,
            'participants': [p.model_dump(mode='json') for p in room.participants],
            'participant_count': len(room.participants),
            'max_participants': room.max_participants,
            'is_active': room.is_active,
            'current_topic': room.current_topic,
            'ai_judge_enabled': room.ai_judge_enabled,
            'ai_facilitator_enabled': room.ai_facilitator_enabled
        }, room=sid)
        
    except Exception as e:
        logger.error(f"Error getting room info: {e}")
        await sio.emit('error', {'message': f'Failed to get room info: {str(e)}'}, room=sid)

@sio.event
async def speech_start(sid, data):
    """Handle speech start event"""
    try:
        room_id = data.get('room_id')
        participant_id = data.get('participant_id')
        
        if room_id and participant_id:
            logger.info(f"🎤 Speech started: {participant_id} in room {room_id}")
            
            # Broadcast to all participants in the room
            await sio.emit('speech_start', {
                'participant_id': participant_id,
                'room_id': room_id
            }, room=room_id)
            
    except Exception as e:
        logger.error(f"Error handling speech start: {e}")

@sio.event
async def speech_end(sid, data):
    """Handle speech end event"""
    try:
        room_id = data.get('room_id')
        participant_id = data.get('participant_id')
        
        if room_id and participant_id:
            logger.info(f"🔇 Speech ended: {participant_id} in room {room_id}")
            
            # Broadcast to all participants in the room
            await sio.emit('speech_end', {
                'participant_id': participant_id,
                'room_id': room_id
            }, room=room_id)
            
    except Exception as e:
        logger.error(f"Error handling speech end: {e}")
        await sio.emit('error', {'message': f'Failed to get room info: {str(e)}'}, room=sid)

@sio.event
async def participant_ready(sid, data):
    """Handle participant ready status for group discussions"""
    try:
        room_id = data.get('room_id')
        participant_id = data.get('participant_id')
        is_ready = data.get('is_ready', False)
        
        if not room_id or not participant_id:
            logger.error("Missing room_id or participant_id in participant_ready")
            return
        
        logger.info(f"Participant {participant_id} ready status: {is_ready} in room {room_id}")
        
        # Get room from database
        room = await RoomManager.get_room_from_db(room_id)
        if not room:
            logger.error(f"Room {room_id} not found")
            return
        
        logger.info(f"Room participants: {[p.id + ' (' + p.name + ')' for p in room.participants]}")
        
        # Update participant ready status
        participant = next((p for p in room.participants if p.id == participant_id), None)
        
        # If not found by ID, try to find by name (fallback for ID mismatches)
        if not participant:
            # Try to find human participant by name
            participant = next((p for p in room.participants if p.name == "User" and not p.is_ai), None)
            if participant:
                logger.info(f"✅ Found participant by name fallback: {participant.name} ({participant.id})")
                # Update the frontend's participant ID to match the actual one
                logger.info(f"🔄 Frontend should use participant ID: {participant.id}")
        
        if participant:
            logger.info(f"✅ Found participant {participant.name}, updating ready status to {is_ready}")
            participant.is_ready = is_ready
            
            # Update database
            await RoomManager.update_room_in_db(room)
            
            # Update Redis cache
            await redis_client.set_room_state(room_id, room.model_dump(mode='json'))
            
            # Broadcast updated participant list to room
            await sio.emit('room_update', {
                'participants': [p.model_dump(mode='json') for p in room.participants],
                'room_id': room_id
            }, room=room_id)
            
            # Send corrected participant ID back to the client if it was found by fallback
            if participant.id != participant_id:
                await sio.emit('participant_id_correction', {
                    'correct_participant_id': participant.id,
                    'room_id': room_id
                }, room=sid)
            
            logger.info(f"✅ Updated ready status for {participant.name} and broadcasted to room")
            
            # Check if all participants are ready for auto-start
            all_ready = all(p.is_ready for p in room.participants) and len(room.participants) > 1
            if all_ready:
                logger.info(f"🚀 All participants ready in room {room_id}, checking for auto-start")
                # Emit auto-start signal
                await sio.emit('all_participants_ready', {
                    'room_id': room_id,
                    'message': 'All participants are ready!'
                }, room=room_id)
        else:
            logger.error(f"❌ Participant {participant_id} not found in room {room_id}")
            logger.error(f"Available participants: {[p.id + ' (' + p.name + ')' for p in room.participants]}")
            
            # Send error back to client
            await sio.emit('participant_not_found', {
                'message': f'Participant {participant_id} not found in room',
                'available_participants': [{'id': p.id, 'name': p.name} for p in room.participants],
                'room_id': room_id
            }, room=sid)
            
            all_ready = False  # participant not found, can't be all ready
            if all_ready and not room.scenario:
                logger.info(f"All participants ready in room {room_id}, generating scenario")
                # Generate scenario automatically
                try:
                    from app.services.ai_service import AIService
                    ai_service = AIService()
                    
                    discussion_mode = room.discussion_mode or 'business'
                    scenario_data = await ai_service.generate_discussion_scenario(
                        discussion_mode, 
                        len(room.participants)
                    )
                    
                    # Assign roles to participants
                    roles = scenario_data.get('roles', [])
                    for i, participant in enumerate(room.participants):
                        if i < len(roles):
                            participant.role = roles[i]
                    
                    # Update room with scenario
                    room.scenario = scenario_data.get('scenario', '')
                    
                    # Update database
                    await RoomManager.update_room_in_db(room)
                    
                    # Update Redis cache
                    await redis_client.set_room_state(room_id, room.model_dump(mode='json'))
                    
                    # Broadcast scenario to all participants
                    await sio.emit('room_update', {
                        'scenario': room.scenario,
                        'participants': [p.model_dump(mode='json') for p in room.participants]
                    }, room=room_id)
                    
                    logger.info(f"Scenario generated and broadcast to room {room_id}")
                    
                except Exception as e:
                    logger.error(f"Error generating scenario: {e}")
        
    except Exception as e:
        logger.error(f"Error handling participant ready: {e}")
        await sio.emit('error', {'message': f'Failed to update ready status: {str(e)}'}, room=sid)

@sio.event
async def set_discussion_mode(sid, data):
    """Handle discussion mode selection for group discussions"""
    try:
        room_id = data.get('room_id')
        discussion_mode = data.get('discussion_mode', 'business')
        
        if not room_id:
            logger.error("Missing room_id in set_discussion_mode")
            return
        
        logger.info(f"Setting discussion mode to {discussion_mode} in room {room_id}")
        
        # Get room from database
        room = await RoomManager.get_room_from_db(room_id)
        if not room:
            logger.error(f"Room {room_id} not found")
            return
        
        # Update discussion mode
        room.discussion_mode = discussion_mode
        
        # Update database
        await RoomManager.update_room_in_db(room)
        
        # Update Redis cache
        await redis_client.set_room_state(room_id, room.model_dump(mode='json'))
        
        # Broadcast updated mode to room
        await sio.emit('room_update', {
            'discussion_mode': discussion_mode
        }, room=room_id)
        
        logger.info(f"Discussion mode updated to {discussion_mode} in room {room_id}")
        
    except Exception as e:
        logger.error(f"Error setting discussion mode: {e}")
        await sio.emit('error', {'message': f'Failed to set discussion mode: {str(e)}'}, room=sid)

# Enhanced utility functions
async def get_room_participants_count(room_id: str) -> int:
    """Get number of participants in a room"""
    participants = await RoomManager.get_room_participants(room_id)
    return len(participants)

async def broadcast_to_room(room_id: str, event: str, data: Dict[str, Any]):
    """Broadcast message to all participants in a room"""
    await sio.emit(event, data, room=room_id)

async def send_to_participant(participant_sid: str, event: str, data: Dict[str, Any]):
    """Send message to specific participant"""
    await sio.emit(event, data, room=participant_sid)

async def get_active_rooms() -> List[str]:
    """Get list of active room IDs"""
    return list(room_participants.keys())

async def get_participant_info(sid: str) -> Optional[Dict[str, Any]]:
    """Get participant information by socket ID"""
    return active_connections.get(sid)

async def is_participant_in_room(room_id: str, participant_id: str) -> bool:
    """Check if participant is in a specific room"""
    participants = await RoomManager.get_room_participants(room_id)
    return any(p.id == participant_id for p in participants)

async def cleanup_inactive_rooms():
    """Clean up rooms with no active participants"""
    try:
        for room_id in list(room_participants.keys()):
            if not room_participants[room_id]:  # No active socket connections
                # Check if room has any participants in database
                participants = await RoomManager.get_room_participants(room_id)
                if not participants:
                    # Remove from local tracking
                    del room_participants[room_id]
                    logger.info(f"Cleaned up inactive room {room_id}")
    except Exception as e:
        logger.error(f"Error cleaning up inactive rooms: {e}")

# Periodic cleanup task (can be called by a scheduler)
async def periodic_cleanup():
    """Periodic cleanup of inactive rooms and connections"""
    await cleanup_inactive_rooms()
    logger.info("Periodic cleanup completed")

@sio.event
async def webrtc_offer(sid, data):
    """Handle WebRTC offer signaling"""
    try:
        room_id = active_connections[sid].get('room_id')
        participant_id = active_connections[sid].get('participant_id')
        target_participant = data.get('targetParticipant')
        offer = data.get('offer')
        
        if not room_id or not target_participant or not offer:
            await sio.emit('error', {'message': 'Missing required WebRTC offer data'}, room=sid)
            return
        
        logger.info(f"📤 Forwarding WebRTC offer from {participant_id} to {target_participant}")
        
        # Find target participant's socket ID
        target_sockets = [s for s, info in active_connections.items() 
                         if info.get('participant_id') == target_participant and info.get('room_id') == room_id]
        
        for target_sid in target_sockets:
            await sio.emit('webrtc-offer', {
                'offer': offer,
                'fromParticipant': participant_id
            }, room=target_sid)
        
    except Exception as e:
        logger.error(f"❌ Error handling WebRTC offer: {e}")
        await sio.emit('error', {'message': f'WebRTC offer failed: {str(e)}'}, room=sid)

@sio.event
async def webrtc_answer(sid, data):
    """Handle WebRTC answer signaling"""
    try:
        room_id = active_connections[sid].get('room_id')
        participant_id = active_connections[sid].get('participant_id')
        target_participant = data.get('targetParticipant')
        answer = data.get('answer')
        
        if not room_id or not target_participant or not answer:
            await sio.emit('error', {'message': 'Missing required WebRTC answer data'}, room=sid)
            return
        
        logger.info(f"📤 Forwarding WebRTC answer from {participant_id} to {target_participant}")
        
        # Find target participant's socket ID
        target_sockets = [s for s, info in active_connections.items() 
                         if info.get('participant_id') == target_participant and info.get('room_id') == room_id]
        
        for target_sid in target_sockets:
            await sio.emit('webrtc-answer', {
                'answer': answer,
                'fromParticipant': participant_id
            }, room=target_sid)
        
    except Exception as e:
        logger.error(f"❌ Error handling WebRTC answer: {e}")
        await sio.emit('error', {'message': f'WebRTC answer failed: {str(e)}'}, room=sid)

@sio.event
async def ice_candidate(sid, data):
    """Handle ICE candidate signaling"""
    try:
        room_id = active_connections[sid].get('room_id')
        participant_id = active_connections[sid].get('participant_id')
        target_participant = data.get('targetParticipant')
        candidate = data.get('candidate')
        
        if not room_id or not target_participant or not candidate:
            await sio.emit('error', {'message': 'Missing required ICE candidate data'}, room=sid)
            return
        
        logger.info(f"📡 Forwarding ICE candidate from {participant_id} to {target_participant}")
        
        # Find target participant's socket ID
        target_sockets = [s for s, info in active_connections.items() 
                         if info.get('participant_id') == target_participant and info.get('room_id') == room_id]
        
        for target_sid in target_sockets:
            await sio.emit('ice-candidate', {
                'candidate': candidate,
                'fromParticipant': participant_id
            }, room=target_sid)
        
    except Exception as e:
        logger.error(f"❌ Error handling ICE candidate: {e}")
        await sio.emit('error', {'message': f'ICE candidate failed: {str(e)}'}, room=sid)