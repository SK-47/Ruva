from fastapi import APIRouter, HTTPException, Depends
from app.models.matchmaking import JoinQueueRequest, MatchmakingMode, MatchStatus
from app.services.matchmaking_service import matchmaking_service
from app.api.routes.auth import get_current_user
import asyncio

router = APIRouter()

@router.post("/queue/join")
async def join_queue(request: JoinQueueRequest, current_user = Depends(get_current_user)):
    """Join matchmaking queue"""
    try:
        from app.models.matchmaking import RoomPreferences
        
        preferences = RoomPreferences(
            mode=request.mode,
            max_players=request.max_players,
            include_ai=request.include_ai,
            ai_only=request.ai_only,
            skill_level=request.skill_level or current_user.skill_level
        )
        
        queue_entry = await matchmaking_service.join_queue(current_user.id, preferences)
        
        # IMMEDIATE PROCESSING: Process queues right after joining
        import asyncio
        asyncio.create_task(process_queues_after_delay())
        
        return {
            "success": True,
            "message": f"Joined {request.mode.value} queue",
            "queue_entry": {
                "mode": queue_entry.preferences.mode.value,
                "max_players": queue_entry.preferences.max_players,
                "include_ai": queue_entry.preferences.include_ai,
                "ai_only": queue_entry.preferences.ai_only,
                "skill_level": queue_entry.preferences.skill_level,
                "joined_at": queue_entry.joined_at.isoformat(),
                "status": queue_entry.status.value
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to join queue: {str(e)}")

async def process_queues_after_delay():
    """Process queues after a short delay"""
    await asyncio.sleep(1)  # Wait 1 second
    try:
        await matchmaking_service.process_queues()
    except Exception as e:
        print(f"Error processing queues: {e}")

@router.post("/queue/leave")
async def leave_queue(current_user = Depends(get_current_user)):
    """Leave matchmaking queue"""
    try:
        success = await matchmaking_service.leave_queue(current_user.id)
        
        if not success:
            raise HTTPException(status_code=400, detail="User not in queue")
        
        return {
            "success": True,
            "message": "Left queue successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to leave queue: {str(e)}")

@router.get("/queue/status")
async def get_queue_status(current_user = Depends(get_current_user)):
    """Get current queue status"""
    try:
        status = await matchmaking_service.get_queue_status(current_user.id)
        
        if not status:
            return {
                "in_queue": False,
                "message": "Not in queue"
            }
        
        return {
            "in_queue": True,
            "status": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get queue status: {str(e)}")

@router.post("/match/{match_id}/accept")
async def accept_match(match_id: str, current_user = Depends(get_current_user)):
    """Accept a match"""
    try:
        success = await matchmaking_service.accept_match(current_user.id, match_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Invalid match or user not in match")
        
        return {
            "success": True,
            "message": "Match accepted"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept match: {str(e)}")

@router.post("/match/{match_id}/decline")
async def decline_match(match_id: str, current_user = Depends(get_current_user)):
    """Decline a match"""
    try:
        success = await matchmaking_service.decline_match(current_user.id, match_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Invalid match or user not in match")
        
        return {
            "success": True,
            "message": "Match declined"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decline match: {str(e)}")

@router.get("/match/{match_id}")
async def get_match(match_id: str, current_user = Depends(get_current_user)):
    """Get match details"""
    try:
        match = await matchmaking_service.get_match(match_id)
        
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        
        if current_user.id not in match.participants:
            raise HTTPException(status_code=403, detail="Not authorized to view this match")
        
        return {
            "match_id": match.id,
            "mode": match.mode.value,
            "participants": [
                {"user_id": uid, "display_name": match.participant_names[uid]}
                for uid in match.participants
            ],
            "session_id": match.session_id,
            "status": match.status.value,
            "expires_at": match.expires_at.isoformat(),
            "accepted_by": match.accepted_by
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get match: {str(e)}")

@router.get("/user/room")
async def get_user_room(current_user = Depends(get_current_user)):
    """Get the room ID for the current user if they're in a match"""
    try:
        # Check if user has an active match
        for match_id, match in matchmaking_service.active_matches.items():
            if current_user.id in match.participants and match.status == MatchStatus.ACCEPTED:
                return {
                    "has_room": True,
                    "room_id": match.room_id,
                    "match_id": match.id,
                    "mode": match.mode.value
                }
        
        return {
            "has_room": False,
            "message": "No active room found"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user room: {str(e)}")

@router.post("/cleanup/user")
async def cleanup_user_matchmaking(current_user = Depends(get_current_user)):
    """Clean up any stale matchmaking state for the current user"""
    try:
        from app.services.matchmaking_service import matchmaking_service
        cleaned = await matchmaking_service.cleanup_user_match(current_user.id)
        
        return {
            "success": True,
            "cleaned": cleaned,
            "message": "User matchmaking state cleaned up"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup user state: {str(e)}")

@router.post("/test/process-queues")
async def test_process_queues():
    """Test endpoint to manually trigger queue processing"""
    try:
        from app.services.matchmaking_service import matchmaking_service
        
        # Ensure background task is running
        matchmaking_service._ensure_background_task()
        
        # Manually process queues once
        await matchmaking_service.process_queues()
        
        return {
            "success": True,
            "message": "Queue processing triggered",
            "queue_count": len(matchmaking_service.queue),
            "active_matches": len(matchmaking_service.active_matches)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process queues: {str(e)}")

@router.get("/modes")
async def get_available_modes():
    """Get available matchmaking modes"""
    return {
        "modes": [
            {
                "id": "group-discussion",
                "name": "Group Discussion",
                "description": "Participate in structured group discussions with voting and role assignments",
                "min_players": 1,
                "max_players": 4,
                "supports_ai": True
            },
            {
                "id": "jam",
                "name": "JAM Session",
                "description": "Practice speaking with AI coaching and real-time feedback",
                "min_players": 1,
                "max_players": 1,
                "supports_ai": True
            },
            {
                "id": "debate",
                "name": "Debate",
                "description": "Engage in structured debates with opponents",
                "min_players": 1,
                "max_players": 2,
                "supports_ai": True
            },
            {
                "id": "reading",
                "name": "Reading Practice",
                "description": "Improve reading fluency and comprehension with AI analysis",
                "min_players": 1,
                "max_players": 1,
                "supports_ai": True
            },
            {
                "id": "interview",
                "name": "Interview Practice",
                "description": "Practice job interviews with AI interviewer Gemini Recruit",
                "min_players": 1,
                "max_players": 1,
                "supports_ai": True
            },
            {
                "id": "business-talks",
                "name": "Business Talks",
                "description": "Practice professional communication in realistic business scenarios",
                "min_players": 1,
                "max_players": 1,
                "supports_ai": True
            },
            {
                "id": "socialising",
                "name": "Social Confidence",
                "description": "Build social confidence with friendly, judgment-free practice",
                "min_players": 1,
                "max_players": 1,
                "supports_ai": True
            }
        ]
    }