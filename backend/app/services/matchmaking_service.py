from typing import Dict, List, Optional
from datetime import datetime, timedelta
import uuid
import asyncio
from app.models.matchmaking import (
    QueueEntry, Match, MatchmakingMode, QueueStatus, MatchStatus, MatchResponse, RoomPreferences
)
from app.models.user import UserStatus
from app.services.auth_service import auth_service
from app.core.database import db
import logging

logger = logging.getLogger(__name__)

class MatchmakingService:
    def __init__(self):
        self.queue: Dict[str, List[QueueEntry]] = {}  # queue_key -> entries
        self.active_matches: Dict[str, Match] = {}
        self.user_to_queue: Dict[str, str] = {}  # user_id -> queue_key
        self._background_task = None
        
        # Start background matchmaking task when first used
        self._ensure_background_task()

    def _ensure_background_task(self):
        """Ensure the background matchmaking task is running"""
        if self._background_task is None or self._background_task.done():
            try:
                self._background_task = asyncio.create_task(self.matchmaking_loop())
                logger.info("🚀 Started matchmaking background task")
            except RuntimeError:
                # No event loop running yet, will start later
                logger.info("⏳ Event loop not ready, will start matchmaking task later")
                pass

    def _get_queue_key(self, preferences: RoomPreferences) -> str:
        """Generate queue key based on preferences"""
        return f"{preferences.mode.value}_{preferences.max_players}_{preferences.include_ai}_{preferences.skill_level}"

    async def join_queue(self, user_id: str, preferences: RoomPreferences) -> QueueEntry:
        """Add user to matchmaking queue"""
        # Ensure background task is running
        self._ensure_background_task()
        
        # Check if user is already in a queue
        if user_id in self.user_to_queue:
            raise ValueError("User is already in a queue")

        # Get user info
        user = await auth_service.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        # If AI only, create instant match
        if preferences.ai_only:
            return await self._create_ai_only_match(user, preferences)

        # Update user status
        await auth_service.update_user_status(user_id, UserStatus.IN_QUEUE)

        # Create queue entry
        queue_entry = QueueEntry(
            user_id=user_id,
            username=user.username,
            display_name=user.display_name or user.username,
            preferences=preferences,
            joined_at=datetime.utcnow()
        )

        # Add to appropriate queue
        queue_key = self._get_queue_key(preferences)
        if queue_key not in self.queue:
            self.queue[queue_key] = []
        
        self.queue[queue_key].append(queue_entry)
        self.user_to_queue[user_id] = queue_key

        logger.info(f"User {user.username} joined queue: {queue_key}")
        return queue_entry

    async def _create_ai_only_match(self, user, preferences: RoomPreferences) -> QueueEntry:
        """Create instant match with AI only (only for 2-player rooms)"""
        # AI-only matches are only allowed for 2-player rooms
        if preferences.max_players != 2:
            raise ValueError("AI-only matches are only available for 2-player rooms")
            
        match_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        room_id = str(uuid.uuid4())
        
        # Create 1 AI opponent for 2-player room
        ai_id = f"ai_{match_id}_0"
        ai_participants = [ai_id]
        
        participants = [user.id]
        participant_names = {
            user.id: user.display_name or user.username,
            ai_id: "AI Opponent"
        }
        
        match = Match(
            id=match_id,
            mode=preferences.mode,
            participants=participants,
            participant_names=participant_names,
            ai_participants=ai_participants,
            session_id=session_id,
            room_id=room_id,
            status=MatchStatus.ACCEPTED,  # Auto-accept AI matches
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=30),
            accepted_by=[user.id],
            preferences=preferences
        )
        
        self.active_matches[match_id] = match
        
        # Update user status
        await auth_service.update_user_status(user.id, UserStatus.IN_SESSION)
        
        logger.info(f"Created AI-only match {match_id} for {user.username}")
        
        # Create room and start session immediately
        await self._start_match_session(match)
        
        # Return a queue entry for consistency
        return QueueEntry(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name or user.username,
            preferences=preferences,
            joined_at=datetime.utcnow(),
            status=QueueStatus.MATCHED
        )

    async def leave_queue(self, user_id: str) -> bool:
        """Remove user from queue"""
        if user_id not in self.user_to_queue:
            return False

        queue_key = self.user_to_queue[user_id]
        
        # Remove from queue
        if queue_key in self.queue:
            self.queue[queue_key] = [entry for entry in self.queue[queue_key] if entry.user_id != user_id]
        
        del self.user_to_queue[user_id]

        # Update user status
        await auth_service.update_user_status(user_id, UserStatus.ONLINE)

        logger.info(f"User {user_id} left queue: {queue_key}")
        return True

    async def get_queue_status(self, user_id: str) -> Optional[dict]:
        """Get user's queue status"""
        if user_id not in self.user_to_queue:
            return None

        queue_key = self.user_to_queue[user_id]
        
        if queue_key not in self.queue:
            return None
            
        queue_entry = next((entry for entry in self.queue[queue_key] if entry.user_id == user_id), None)
        
        if not queue_entry:
            return None

        # Calculate position and estimated wait time
        position = self.queue[queue_key].index(queue_entry) + 1
        queue_length = len(self.queue[queue_key])
        estimated_wait = max(30, position * 15)  # Rough estimate

        return {
            "mode": queue_entry.preferences.mode.value,
            "max_players": queue_entry.preferences.max_players,
            "include_ai": queue_entry.preferences.include_ai,
            "position": position,
            "queue_length": queue_length,
            "estimated_wait_time": estimated_wait,
            "joined_at": queue_entry.joined_at.isoformat()
        }

    async def matchmaking_loop(self):
        """Background task to create matches"""
        logger.info("🔄 Matchmaking loop started")
        while True:
            try:
                logger.info("🔍 Processing queues...")
                await self.process_queues()
                await asyncio.sleep(2)  # Check every 2 seconds
            except Exception as e:
                logger.error(f"❌ Error in matchmaking loop: {e}")
                await asyncio.sleep(5)

    async def process_queues(self):
        """Process all queues and create matches"""
        logger.info(f"📊 Processing {len(self.queue)} queue groups")
        
        for queue_key, queue in self.queue.items():
            if not queue:
                continue
                
            logger.info(f"🔍 Processing queue '{queue_key}' with {len(queue)} entries")
            
            # Group by preferences to find compatible players
            preferences_groups = {}
            for entry in queue:
                prefs_key = f"{entry.preferences.mode.value}_{entry.preferences.max_players}_{entry.preferences.include_ai}"
                if prefs_key not in preferences_groups:
                    preferences_groups[prefs_key] = []
                preferences_groups[prefs_key].append(entry)
            
            logger.info(f"📋 Found {len(preferences_groups)} preference groups")
            
            # Try to create matches for each group
            for prefs_key, entries in preferences_groups.items():
                logger.info(f"🎯 Processing group '{prefs_key}' with {len(entries)} entries")
                if len(entries) >= 1:  # At least 1 player needed
                    logger.info(f"✅ Creating match for {len(entries)} players")
                    await self._create_human_match(entries)
                else:
                    logger.info(f"⏳ Not enough players in group '{prefs_key}'")
        
        logger.info("✅ Queue processing completed")

    async def _create_human_match(self, entries: List[QueueEntry]):
        """Create match with human players (and AI only for 2-player rooms)"""
        if not entries:
            logger.warning("❌ No entries provided to _create_human_match")
            return
            
        # Take the first entry to get preferences
        preferences = entries[0].preferences
        max_players = preferences.max_players
        
        logger.info(f"🎯 Creating match for {len(entries)} players, max_players: {max_players}")
        
        # For single-player rooms (like JAM): instant match
        if max_players == 1:
            if len(entries) >= 1:
                logger.info("🚀 Creating instant single-player match (JAM)")
                # Create instant single-player match
                await self._create_mixed_match([entries[0]], preferences)
            else:
                logger.warning("❌ Not enough entries for single-player match")
        
        # For 2-player rooms: prioritize human-human matches, only add AI if explicitly requested
        elif max_players == 2:
            if len(entries) >= 2:
                logger.info("👥 Creating match with 2 humans (no AI needed)")
                # Create match with 2 humans - no AI needed
                await self._create_mixed_match(entries[:2], preferences)
            elif len(entries) >= 1 and preferences.include_ai:
                logger.info("🤖 Creating match with 1 human + 1 AI (AI explicitly requested)")
                # Only add AI if explicitly requested
                await self._create_mixed_match([entries[0]], preferences)
            else:
                logger.info("⏳ Waiting for more players for 2-player human-only match")
                # Don't create match yet, wait for more players
        
        # For 3+ player rooms: can fill with AI if enabled
        else:
            if preferences.include_ai and len(entries) >= 1:
                # Can create match with available humans + AI to fill
                logger.info(f"🤖 Creating match with {len(entries)} humans + AI to fill {max_players} slots")
                await self._create_mixed_match(entries[:max_players], preferences)
            elif len(entries) >= max_players:
                logger.info(f"👥 Creating match with {max_players} humans")
                # Create match with exact number of humans
                selected_players = entries[:max_players]
                await self._create_mixed_match(selected_players, preferences)
            else:
                logger.info(f"⏳ Waiting for more players ({len(entries)}/{max_players}) for multi-player match")

    async def _create_mixed_match(self, human_entries: List[QueueEntry], preferences: RoomPreferences):
        """Create match with humans and AI"""
        match_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        room_id = str(uuid.uuid4())
        
        # Human participants
        participants = [entry.user_id for entry in human_entries]
        participant_names = {entry.user_id: entry.display_name for entry in human_entries}
        
        # AI participants - only add AI if explicitly requested AND we don't have enough humans
        ai_participants = []
        
        # CRITICAL FIX: For 2-player matches, NEVER add AI if we have 2 humans
        if preferences.max_players == 2 and len(human_entries) >= 2:
            logger.info(f"👥 2-player match with 2 humans - NO AI needed")
            # Don't add any AI participants
        elif preferences.include_ai and len(human_entries) < preferences.max_players:
            # Calculate how many AI participants to add
            ai_needed = preferences.max_players - len(human_entries)
            
            logger.info(f"🤖 Adding {ai_needed} AI participants (include_ai={preferences.include_ai}, humans={len(human_entries)}, max={preferences.max_players})")
            
            for i in range(ai_needed):
                ai_id = f"ai_{match_id}_{i}"
                ai_participants.append(ai_id)
                
                # Set appropriate AI names based on mode
                if preferences.mode == MatchmakingMode.DEBATE:
                    participant_names[ai_id] = "AI Opponent"
                elif preferences.mode == MatchmakingMode.GROUP_DISCUSSION:
                    participant_names[ai_id] = "AI Participant"
                else:
                    participant_names[ai_id] = "AI Coach"
        else:
            logger.info(f"🚫 No AI participants added (include_ai={preferences.include_ai}, humans={len(human_entries)}/{preferences.max_players})")
        
        match = Match(
            id=match_id,
            mode=preferences.mode,
            participants=participants,
            participant_names=participant_names,
            ai_participants=ai_participants,
            session_id=session_id,
            room_id=room_id,
            status=MatchStatus.ACCEPTED,  # Auto-accept single-player matches
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=30),
            accepted_by=participants.copy(),  # Auto-accept for all participants
            preferences=preferences
        )
        
        self.active_matches[match_id] = match
        
        # Remove players from queue
        for entry in human_entries:
            queue_key = self._get_queue_key(entry.preferences)
            if queue_key in self.queue:
                self.queue[queue_key] = [e for e in self.queue[queue_key] if e.user_id != entry.user_id]
            
            if entry.user_id in self.user_to_queue:
                del self.user_to_queue[entry.user_id]
            
            await auth_service.update_user_status(entry.user_id, UserStatus.IN_SESSION)
        
        logger.info(f"Created match {match_id} with {len(participants)} humans + {len(ai_participants)} AI")
        
        # Start session immediately for single-player and 2-player matches
        if preferences.max_players <= 2:
            logger.info(f"🚀 Starting session immediately for {preferences.max_players}-player match")
            await self._start_match_session(match)
        else:
            # For 3+ player matches, notify all players first
            await self.notify_match_found(match)

    async def _start_match_session(self, match: Match):
        """Start the actual game session"""
        logger.info(f"🚀 Starting match session for match {match.id}")
        logger.info(f"📊 Match details: mode={match.mode}, participants={len(match.participants)}, AI={len(match.ai_participants)}")
        
        from app.core.database import get_database
        from app.models.room import Room, RoomMode, Participant, ConnectionStatus
        import uuid
        from datetime import datetime
        
        # Create room based on match
        room_id = match.room_id
        logger.info(f"📝 Creating room with ID: {room_id}")
        
        # Map matchmaking mode to room mode
        mode_mapping = {
            MatchmakingMode.GROUP_DISCUSSION: RoomMode.GROUP_DISCUSSION,
            MatchmakingMode.JAM: RoomMode.JAM,
            MatchmakingMode.DEBATE: RoomMode.DEBATE,
            MatchmakingMode.READING: RoomMode.READING,
            MatchmakingMode.INTERVIEW: RoomMode.INTERVIEW,
            MatchmakingMode.BUSINESS_TALKS: RoomMode.BUSINESS_TALKS,
            MatchmakingMode.SOCIALISING: RoomMode.SOCIALISING
        }
        
        room_mode = mode_mapping.get(match.mode, RoomMode.GROUP_DISCUSSION)
        logger.info(f"🎯 Room mode: {room_mode}")
        
        # Create participants (only AI participants - humans will join via WebSocket)
        participants = []
        logger.info(f"👥 Creating participants list...")
        
        # DO NOT add human participants here - they will join via WebSocket
        # Only add AI participants during room creation
        for ai_id in match.ai_participants:
            ai_participant = Participant(
                id=ai_id,
                name=match.participant_names[ai_id],
                is_ai=True,
                joined_at=datetime.utcnow(),
                is_ready=True,  # AI participants are always ready
                connection_status=ConnectionStatus.CONNECTED
            )
            participants.append(ai_participant)
            logger.info(f"🤖 Added AI participant: {ai_participant.name} ({ai_participant.id})")
        
        logger.info(f"👥 Room will have {len(participants)} AI participants, humans will join via WebSocket")
        logger.info(f"🏠 Room max_participants: {match.preferences.max_players}")
        logger.info(f"🎯 Expected human participants: {len(match.participants)}")
        logger.info(f"🤖 AI participants being added: {len(match.ai_participants)}")
        for ai_id in match.ai_participants:
            logger.info(f"  - AI: {ai_id} ({match.participant_names[ai_id]})")
        
        # Create room
        room = Room(
            id=room_id,
            name=f"{match.mode.value.title()} Room",
            mode=room_mode,
            max_participants=match.preferences.max_players,
            participants=participants,
            ai_judge_enabled=match.preferences.include_ai and room_mode == RoomMode.DEBATE,
            ai_facilitator_enabled=match.preferences.include_ai and room_mode == RoomMode.GROUP_DISCUSSION,
            created_at=datetime.utcnow(),
            is_active=True,
            match_id=match.id
        )
        
        logger.info(f"🏠 Created room object: {room.name}")
        
        # Store room in database
        try:
            logger.info(f"🔌 Getting database connection...")
            db = await get_database()
            logger.info(f"✅ Database connection obtained: {db is not None}")
            
            room_dict = room.model_dump()
            logger.info(f"💾 Storing room in database with ID: {room_id}")
            logger.info(f"📋 Room data keys: {list(room_dict.keys())}")
            logger.info(f"📋 Room ID in data: {room_dict.get('id')}")
            
            # Check if room already exists
            existing_room = await db.rooms.find_one({"id": room_id})
            if existing_room:
                logger.warning(f"⚠️ Room {room_id} already exists in database")
            else:
                logger.info(f"✅ Room {room_id} does not exist yet, proceeding with creation")
            
            result = await db.rooms.insert_one(room_dict)
            logger.info(f"✅ Room stored successfully in database with _id: {result.inserted_id}")
            
            # Verify the room was actually stored
            verification = await db.rooms.find_one({"id": room_id})
            if verification:
                logger.info(f"✅ Room verification successful: Room {room_id} exists in database")
                logger.info(f"📋 Verified room data keys: {list(verification.keys())}")
            else:
                logger.error(f"❌ Room verification failed: Room {room_id} not found after insertion")
                
                # Check what rooms do exist
                all_rooms = await db.rooms.find({}).to_list(10)
                logger.error(f"📋 Available rooms in database: {[r.get('id', 'no-id') for r in all_rooms]}")
                
        except Exception as e:
            logger.error(f"❌ Failed to store room in database: {e}")
            logger.error(f"❌ Exception type: {type(e).__name__}")
            logger.error(f"❌ Exception details: {str(e)}")
            if hasattr(e, '__dict__'):
                logger.error(f"❌ Exception attributes: {e.__dict__}")
            raise
        
        logger.info(f"🎉 Room {room_id} created successfully for match {match.id}")
        
        # Notify players via WebSocket that room is ready
        await self.notify_room_ready(match, room_id)

    async def notify_match_found(self, match: Match):
        """Notify players that a match was found (placeholder for WebSocket)"""
        # This would be implemented with WebSocket notifications
        logger.info(f"Match {match.id} found for mode {match.mode.value}")
        pass

    async def notify_room_ready(self, match: Match, room_id: str):
        """Notify players that room is ready"""
        # This would send WebSocket notifications to all participants
        # For now, just log it
        logger.info(f"Room {room_id} ready for match {match.id}")
        pass

    async def accept_match(self, user_id: str, match_id: str) -> bool:
        """Accept a match"""
        if match_id not in self.active_matches:
            return False

        match = self.active_matches[match_id]
        
        if user_id not in match.participants:
            return False

        if user_id not in match.accepted_by:
            match.accepted_by.append(user_id)

        # Check if all players accepted
        if len(match.accepted_by) == len(match.participants):
            match.status = MatchStatus.ACCEPTED
            logger.info(f"Match {match_id} fully accepted, starting session")
            # Start the actual session
            await self._start_match_session(match)
            return True

        return True

    async def decline_match(self, user_id: str, match_id: str) -> bool:
        """Decline a match"""
        if match_id not in self.active_matches:
            return False

        match = self.active_matches[match_id]
        
        if user_id not in match.participants:
            return False

        match.status = MatchStatus.DECLINED
        
        # Put all players back in queue except the one who declined
        for participant_id in match.participants:
            if participant_id != user_id:
                # Re-queue the player
                user = await auth_service.get_user_by_id(participant_id)
                if user:
                    await self.join_queue(participant_id, match.mode, user.skill_level)

        # Remove match
        del self.active_matches[match_id]
        
        # Set declining user back to online
        await auth_service.update_user_status(user_id, UserStatus.ONLINE)
        
        logger.info(f"Match {match_id} declined by {user_id}")
        return True

    async def get_match(self, match_id: str) -> Optional[Match]:
        """Get match by ID"""
        return self.active_matches.get(match_id)

    async def cleanup_user_match(self, user_id: str) -> bool:
        """Clean up any active match for a user (called when they leave a room)"""
        matches_to_remove = []
        
        for match_id, match in self.active_matches.items():
            if user_id in match.participants:
                matches_to_remove.append(match_id)
        
        for match_id in matches_to_remove:
            match = self.active_matches[match_id]
            logger.info(f"Cleaning up match {match_id} for user {user_id}")
            
            # Update user status back to online
            await auth_service.update_user_status(user_id, UserStatus.ONLINE)
            
            # Remove the match
            del self.active_matches[match_id]
        
        return len(matches_to_remove) > 0

    async def cleanup_expired_matches(self):
        """Remove expired matches"""
        now = datetime.utcnow()
        expired_matches = [
            match_id for match_id, match in self.active_matches.items()
            if match.expires_at < now and match.status == MatchStatus.PENDING
        ]
        
        for match_id in expired_matches:
            match = self.active_matches[match_id]
            
            # Put players back in queue
            for participant_id in match.participants:
                user = await auth_service.get_user_by_id(participant_id)
                if user:
                    await self.join_queue(participant_id, match.mode, user.skill_level)
            
            del self.active_matches[match_id]
            logger.info(f"Expired match {match_id} cleaned up")

# Global service instance
matchmaking_service = MatchmakingService()