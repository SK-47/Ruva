"""
Debate Mode Implementation
Handles 2-player debate with AI judge, round-based structure, and scoring.
"""

from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DebatePhase(str, Enum):
    SETUP = "setup"
    OPENING = "opening"
    REBUTTAL = "rebuttal"
    JUDGMENT = "judgment"
    COMPLETED = "completed"


class DebateStance(str, Enum):
    FOR = "for"
    AGAINST = "against"


class DebateArgument(BaseModel):
    participant_id: str
    participant_name: str
    round_number: int
    argument_text: str
    timestamp: datetime
    is_opening: bool = False


class DebateScore(BaseModel):
    participant_id: str
    participant_name: str
    logic_score: float  # 0-10
    evidence_score: float  # 0-10
    delivery_score: float  # 0-10
    rebuttal_score: float  # 0-10
    total_score: float


class DebateJudgment(BaseModel):
    winner_id: str
    winner_name: str
    verdict_summary: str
    user_performance: str
    ai_performance: str
    key_moment: str
    scores: List[DebateScore]
    timestamp: datetime


class DebateState(BaseModel):
    room_id: str
    session_id: str
    topic: str
    phase: DebatePhase
    current_round: int
    max_rounds: int = 6  # 1 opening + 5 rebuttals
    participant1_id: str
    participant1_name: str
    participant1_stance: Optional[DebateStance] = None
    participant2_id: str
    participant2_name: str
    participant2_stance: Optional[DebateStance] = None
    ai_judge_id: str
    arguments: List[DebateArgument] = []
    current_speaker_id: Optional[str] = None
    judgment: Optional[DebateJudgment] = None
    stance_chooser_id: Optional[str] = None  # Who gets to choose the stance
    created_at: datetime
    updated_at: datetime


class DebateModeService:
    """Service for managing debate mode sessions"""
    
    def __init__(self):
        self.active_debates: Dict[str, DebateState] = {}
    
    def create_debate(
        self,
        room_id: str,
        session_id: str,
        participant1_id: str,
        participant1_name: str,
        participant2_id: str,
        participant2_name: str,
        ai_judge_id: str,
        topic: Optional[str] = None
    ) -> DebateState:
        """Create a new debate session"""
        
        # Randomly decide who gets to choose the stance (server-side to ensure consistency)
        import random
        stance_chooser_id = random.choice([participant1_id, participant2_id])
        
        logger.info(f"🎲 Randomly selected stance chooser: {stance_chooser_id}")
        logger.info(f"👤 Participant 1: {participant1_name} ({participant1_id})")
        logger.info(f"👤 Participant 2: {participant2_name} ({participant2_id})")
        
        debate_state = DebateState(
            room_id=room_id,
            session_id=session_id,
            topic=topic or "To be determined",
            phase=DebatePhase.SETUP,
            current_round=0,
            participant1_id=participant1_id,
            participant1_name=participant1_name,
            participant2_id=participant2_id,
            participant2_name=participant2_name,
            ai_judge_id=ai_judge_id,
            stance_chooser_id=stance_chooser_id,  # Add the randomly selected chooser
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.active_debates[session_id] = debate_state
        return debate_state
    
    def set_topic(self, session_id: str, topic: str) -> DebateState:
        """Set the debate topic"""
        logger.info(f"🎯 Setting debate topic for session {session_id}: {topic}")
        
        if session_id not in self.active_debates:
            raise ValueError(f"Debate session {session_id} not found")
        
        debate = self.active_debates[session_id]
        debate.topic = topic
        debate.updated_at = datetime.utcnow()
        
        logger.info(f"✅ Topic set successfully for debate {session_id}")
        return debate
    
    async def set_stances(
        self,
        session_id: str,
        participant1_stance: DebateStance,
        participant2_stance: DebateStance
    ) -> DebateState:
        """Set the stances for both participants"""
        if session_id not in self.active_debates:
            # Try to load from database if not in memory
            from app.core.database import get_database
            db = await get_database()
            debate_doc = await db.debate_sessions.find_one({"session_id": session_id})
            
            if not debate_doc:
                raise ValueError(f"Debate session {session_id} not found")
            
            # Reconstruct DebateState from database document
            debate_state = DebateState(**debate_doc)
            self.active_debates[session_id] = debate_state
        
        debate = self.active_debates[session_id]
        
        # Ensure stances are opposite
        if participant1_stance == participant2_stance:
            raise ValueError("Participants must take opposite stances")
        
        debate.participant1_stance = participant1_stance
        debate.participant2_stance = participant2_stance
        debate.phase = DebatePhase.OPENING
        debate.current_round = 1
        
        # Set the first speaker - typically the person arguing FOR goes first
        if participant1_stance == DebateStance.FOR:
            debate.current_speaker_id = debate.participant1_id
        else:
            debate.current_speaker_id = debate.participant2_id
            
        debate.updated_at = datetime.utcnow()
        
        return debate
    
    async def generate_ai_argument(self, session_id: str) -> Optional[str]:
        """Generate an AI argument for the current debate state"""
        if session_id not in self.active_debates:
            return None
            
        debate = self.active_debates[session_id]
        
        # Check if current speaker is AI (participant2 is typically AI)
        if debate.current_speaker_id != debate.participant2_id:
            return None
            
        # Import AI service
        from app.services.ai_service import AIService
        ai_service = AIService()
        
        # Build context for AI
        ai_stance = debate.participant2_stance
        human_stance = debate.participant1_stance
        topic = debate.topic
        
        # Get previous arguments for context
        previous_args = []
        for arg in debate.arguments:
            speaker = "You" if arg.participant_id == debate.participant2_id else "Opponent"
            previous_args.append(f"{speaker}: {arg.argument_text}")
        
        context = "\n".join(previous_args) if previous_args else "This is the start of the debate."
        
        # Create prompt based on debate phase
        if debate.phase == DebatePhase.OPENING:
            prompt = f"""You are participating in a formal debate. 

Topic: "{topic}"
Your stance: {ai_stance.upper()}
Opponent's stance: {human_stance.upper()}

This is your opening statement. You have 2 minutes to present your main arguments supporting the {ai_stance.upper()} position. 

Be persuasive, logical, and provide strong evidence. Structure your argument clearly with:
1. A clear thesis statement
2. 2-3 main supporting points
3. Evidence or examples
4. A strong conclusion

Previous context: {context}

Provide your opening statement:"""
        else:  # REBUTTAL phase
            prompt = f"""You are participating in a formal debate. 

Topic: "{topic}"
Your stance: {ai_stance.upper()}
Opponent's stance: {human_stance.upper()}

This is round {debate.current_round - 1} of rebuttals. You have 1 minute to:
1. Address your opponent's previous arguments
2. Reinforce your position
3. Present new evidence if needed

Previous arguments:
{context}

Provide your rebuttal:"""
        
        try:
            # Generate AI response
            response = await ai_service.generate_response(
                prompt=prompt,
                context=context,
                mode="debate"
            )
            
            return response.get("text", "").strip()
            
        except Exception as e:
            logger.error(f"Failed to generate AI argument: {e}")
            return None
    
    def add_argument(
        self,
        session_id: str,
        participant_id: str,
        participant_name: str,
        argument_text: str
    ) -> DebateState:
        """Add an argument to the debate"""
        if session_id not in self.active_debates:
            raise ValueError(f"Debate session {session_id} not found")
        
        debate = self.active_debates[session_id]
        
        # Validate it's the correct speaker's turn
        if debate.current_speaker_id and debate.current_speaker_id != participant_id:
            raise ValueError(f"It's not {participant_name}'s turn to speak")
        
        # Create argument
        is_opening = debate.phase == DebatePhase.OPENING
        argument = DebateArgument(
            participant_id=participant_id,
            participant_name=participant_name,
            round_number=debate.current_round,
            argument_text=argument_text,
            timestamp=datetime.utcnow(),
            is_opening=is_opening
        )
        
        debate.arguments.append(argument)
        debate.updated_at = datetime.utcnow()
        
        # Advance the debate state
        self._advance_debate(debate)
        
        return debate
    
    def _advance_debate(self, debate: DebateState):
        """Advance the debate to the next state"""
        
        # Count arguments in current round
        current_round_args = [
            arg for arg in debate.arguments 
            if arg.round_number == debate.current_round
        ]
        
        # If both participants have spoken in this round
        if len(current_round_args) >= 2:
            # Move to next round
            if debate.current_round < debate.max_rounds:
                debate.current_round += 1
                
                # Transition from opening to rebuttal after round 1
                if debate.current_round == 2:
                    debate.phase = DebatePhase.REBUTTAL
                
                debate.current_speaker_id = None
            else:
                # Debate is complete, move to judgment
                debate.phase = DebatePhase.JUDGMENT
                debate.current_speaker_id = None
        else:
            # Switch to the other speaker
            last_speaker = current_round_args[-1].participant_id if current_round_args else None
            
            if last_speaker == debate.participant1_id:
                debate.current_speaker_id = debate.participant2_id
            else:
                debate.current_speaker_id = debate.participant1_id
    
    def get_next_speaker(self, session_id: str) -> Optional[Dict[str, str]]:
        """Get the next speaker in the debate"""
        if session_id not in self.active_debates:
            return None
        
        debate = self.active_debates[session_id]
        
        if not debate.current_speaker_id:
            return None
        
        if debate.current_speaker_id == debate.participant1_id:
            return {
                "id": debate.participant1_id,
                "name": debate.participant1_name,
                "stance": debate.participant1_stance
            }
        else:
            return {
                "id": debate.participant2_id,
                "name": debate.participant2_name,
                "stance": debate.participant2_stance
            }
    
    def submit_judgment(
        self,
        session_id: str,
        winner_id: str,
        winner_name: str,
        verdict_summary: str,
        user_performance: str,
        ai_performance: str,
        key_moment: str,
        scores: List[DebateScore]
    ) -> DebateState:
        """Submit the final judgment for the debate"""
        if session_id not in self.active_debates:
            raise ValueError(f"Debate session {session_id} not found")
        
        debate = self.active_debates[session_id]
        
        if debate.phase != DebatePhase.JUDGMENT:
            raise ValueError("Debate is not in judgment phase")
        
        judgment = DebateJudgment(
            winner_id=winner_id,
            winner_name=winner_name,
            verdict_summary=verdict_summary,
            user_performance=user_performance,
            ai_performance=ai_performance,
            key_moment=key_moment,
            scores=scores,
            timestamp=datetime.utcnow()
        )
        
        debate.judgment = judgment
        debate.phase = DebatePhase.COMPLETED
        debate.updated_at = datetime.utcnow()
        
        return debate
    
    def get_debate_state(self, session_id: str) -> Optional[DebateState]:
        """Get the current state of a debate"""
        return self.active_debates.get(session_id)
    
    def get_debate_summary(self, session_id: str) -> Optional[Dict]:
        """Get a summary of the debate"""
        if session_id not in self.active_debates:
            return None
        
        debate = self.active_debates[session_id]
        
        return {
            "topic": debate.topic,
            "phase": debate.phase,
            "current_round": debate.current_round,
            "max_rounds": debate.max_rounds,
            "total_arguments": len(debate.arguments),
            "participant1": {
                "id": debate.participant1_id,
                "name": debate.participant1_name,
                "stance": debate.participant1_stance,
                "arguments_count": len([
                    arg for arg in debate.arguments 
                    if arg.participant_id == debate.participant1_id
                ])
            },
            "participant2": {
                "id": debate.participant2_id,
                "name": debate.participant2_name,
                "stance": debate.participant2_stance,
                "arguments_count": len([
                    arg for arg in debate.arguments 
                    if arg.participant_id == debate.participant2_id
                ])
            },
            "judgment": debate.judgment.model_dump() if debate.judgment else None
        }
    
    def end_debate(self, session_id: str):
        """End and cleanup a debate session"""
        if session_id in self.active_debates:
            del self.active_debates[session_id]


# Global service instance
debate_service = DebateModeService()
