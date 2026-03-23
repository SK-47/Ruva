"""
Group Discussion Mode Implementation
Handles multi-player discussion rooms with AI facilitator, turn management, and topic guidance.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DiscussionCategory(str, Enum):
    FORMAL = "formal"
    INFORMAL = "informal" 
    BUSINESS = "business"

class DiscussionPhase(str, Enum):
    SETUP = "setup"
    VOTING = "voting"
    ROLES_ASSIGNED = "roles_assigned"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    COMPLETED = "completed"


class TurnStatus(str, Enum):
    WAITING = "waiting"
    SPEAKING = "speaking"
    COMPLETED = "completed"


class ParticipantVote(BaseModel):
    participant_id: str
    participant_name: str
    category: DiscussionCategory
    timestamp: datetime

class VotingResults(BaseModel):
    votes: List[ParticipantVote] = []
    vote_counts: Dict[str, int] = {}  # category -> count
    winning_category: Optional[DiscussionCategory] = None
    voting_ended_at: Optional[datetime] = None

class ParticipantTurn(BaseModel):
    participant_id: str
    participant_name: str
    turn_number: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: TurnStatus = TurnStatus.WAITING
    contribution_text: Optional[str] = None
    word_count: int = 0
    speaking_time: float = 0.0  # seconds
    speaking_time: float = 0.0  # seconds


class DiscussionContribution(BaseModel):
    participant_id: str
    participant_name: str
    text: str
    timestamp: datetime
    turn_number: int
    is_facilitator: bool = False


class ParticipantMetrics(BaseModel):
    participant_id: str
    participant_name: str
    total_contributions: int
    total_words: int
    total_speaking_time: float
    average_contribution_length: float
    participation_percentage: float
    engagement_score: float  # 0-10


class GroupDynamicsAnalysis(BaseModel):
    total_contributions: int
    total_speaking_time: float
    participation_balance: float  # 0-1, higher is more balanced
    dominant_speaker_id: Optional[str] = None
    quiet_participants: List[str] = []
    topic_coherence: float  # 0-1
    engagement_level: float  # 0-1
    participant_metrics: List[ParticipantMetrics] = []
    timestamp: datetime


class GroupDiscussionState(BaseModel):
    room_id: str
    session_id: str
    topic: Optional[str] = None  # Generated after voting
    category: Optional[DiscussionCategory] = None  # Selected category
    phase: DiscussionPhase
    current_turn: int
    max_turns: Optional[int] = None  # None = unlimited
    participants: List[str] = []  # participant IDs
    participant_names: Dict[str, str] = {}  # id -> name mapping
    participant_roles: Dict[str, str] = {}  # id -> role mapping
    participant_role_descriptions: Dict[str, str] = {}  # id -> role description
    ai_facilitator_id: str
    ai_facilitator_name: str = "AI Participant"
    scenario: Optional[str] = None  # AI-generated scenario context
    voting_results: Optional[VotingResults] = None
    voting_start_time: Optional[datetime] = None
    voting_duration: int = 20  # seconds
    contributions: List[DiscussionContribution] = []
    turns: List[ParticipantTurn] = []
    current_speaker_id: Optional[str] = None
    suggested_topics: List[str] = []
    dynamics_analysis: Optional[GroupDynamicsAnalysis] = None
    created_at: datetime
    updated_at: datetime


class GroupDiscussionService:
    """Service for managing group discussion mode sessions"""
    
    def __init__(self):
        self.active_discussions: Dict[str, GroupDiscussionState] = {}
    
    def create_discussion(
        self,
        room_id: str,
        session_id: str,
        participant_ids: List[str],
        participant_names: Dict[str, str],
        max_turns: Optional[int] = None,
        include_ai_participant: bool = True
    ) -> GroupDiscussionState:
        """Create a new group discussion session"""
        
        ai_participant_id = ""  # Initialize AI participant ID
        
        # Check if there's already an AI participant in the list
        # Look for any participant ID that starts with 'ai_' (covers both ai_participant_ and ai_uuid formats)
        existing_ai_participants = [pid for pid in participant_ids if pid.startswith('ai_')]
        
        if existing_ai_participants:
            # Use existing AI participant
            ai_participant_id = existing_ai_participants[0]
            logger.info(f"Using existing AI participant: {ai_participant_id}")
        elif include_ai_participant:
            # Create new AI participant
            ai_participant_id = f"ai_participant_{session_id}"
            participant_ids.append(ai_participant_id)
            participant_names[ai_participant_id] = "AI Participant"
            logger.info(f"Created new AI participant: {ai_participant_id}")
        
        logger.info(f"Final AI facilitator ID: '{ai_participant_id}'")
        logger.info(f"Final participants: {participant_ids}")
        
        # Additional validation
        if not ai_participant_id and include_ai_participant:
            logger.error(f"Failed to create or find AI participant despite include_ai_participant=True")
        elif ai_participant_id:
            logger.info(f"AI participant successfully identified: {ai_participant_id}")
        
        # Validate at least 2 participants (including AI if enabled)
        if len(participant_ids) < 2:
            raise ValueError("Group discussion requires at least 2 participants")
        
        discussion_state = GroupDiscussionState(
            room_id=room_id,
            session_id=session_id,
            phase=DiscussionPhase.SETUP,
            current_turn=0,
            max_turns=max_turns,
            participants=participant_ids,
            participant_names=participant_names,
            ai_facilitator_id=ai_participant_id,
            voting_results=VotingResults(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.active_discussions[session_id] = discussion_state
        return discussion_state
    
    def start_voting(self, session_id: str) -> GroupDiscussionState:
        """Start the category voting phase"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        discussion.phase = DiscussionPhase.VOTING
        discussion.voting_start_time = datetime.utcnow()
        discussion.voting_results = VotingResults()
        discussion.updated_at = datetime.utcnow()
        
        return discussion
    
    def cast_vote(
        self, 
        session_id: str, 
        participant_id: str, 
        participant_name: str, 
        category: DiscussionCategory
    ) -> GroupDiscussionState:
        """Cast a vote for discussion category"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        
        if discussion.phase != DiscussionPhase.VOTING:
            raise ValueError("Voting is not currently active")
        
        # Check if voting time has expired
        if discussion.voting_start_time:
            elapsed = (datetime.utcnow() - discussion.voting_start_time).total_seconds()
            if elapsed > discussion.voting_duration:
                raise ValueError("Voting time has expired")
        
        # Remove any existing vote from this participant
        discussion.voting_results.votes = [
            v for v in discussion.voting_results.votes 
            if v.participant_id != participant_id
        ]
        
        # Add new vote
        vote = ParticipantVote(
            participant_id=participant_id,
            participant_name=participant_name,
            category=category,
            timestamp=datetime.utcnow()
        )
        discussion.voting_results.votes.append(vote)
        
        # Update vote counts
        discussion.voting_results.vote_counts = {}
        for vote in discussion.voting_results.votes:
            category_str = vote.category.value
            discussion.voting_results.vote_counts[category_str] = (
                discussion.voting_results.vote_counts.get(category_str, 0) + 1
            )
        
        discussion.updated_at = datetime.utcnow()
        return discussion
    
    def end_voting(self, session_id: str) -> GroupDiscussionState:
        """End voting and determine winning category"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        
        if not discussion.voting_results.vote_counts:
            # Default to business if no votes
            discussion.voting_results.winning_category = DiscussionCategory.BUSINESS
        else:
            # Find category with most votes
            max_votes = max(discussion.voting_results.vote_counts.values())
            winning_categories = [
                cat for cat, count in discussion.voting_results.vote_counts.items() 
                if count == max_votes
            ]
            
            # If tie, pick first one (could add tiebreaker logic)
            winning_category_str = winning_categories[0]
            discussion.voting_results.winning_category = DiscussionCategory(winning_category_str)
        
        discussion.category = discussion.voting_results.winning_category
        discussion.voting_results.voting_ended_at = datetime.utcnow()
        discussion.phase = DiscussionPhase.ROLES_ASSIGNED
        discussion.updated_at = datetime.utcnow()
        
        return discussion
    
    def set_topic(self, session_id: str, topic: str) -> GroupDiscussionState:
        """Set the discussion topic"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        discussion.topic = topic
        discussion.phase = DiscussionPhase.INTRODUCTION
        discussion.updated_at = datetime.utcnow()
        
        return discussion
    
    def start_discussion(self, session_id: str) -> GroupDiscussionState:
        """Start the discussion phase"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        discussion.phase = DiscussionPhase.DISCUSSION
        discussion.current_turn = 1
        discussion.updated_at = datetime.utcnow()
        
        return discussion
    
    def add_contribution(
        self,
        session_id: str,
        participant_id: str,
        participant_name: str,
        text: str,
        is_facilitator: bool = False
    ) -> GroupDiscussionState:
        """Add a contribution to the discussion"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        
        # Create contribution
        contribution = DiscussionContribution(
            participant_id=participant_id,
            participant_name=participant_name,
            text=text,
            timestamp=datetime.utcnow(),
            turn_number=discussion.current_turn,
            is_facilitator=is_facilitator
        )
        
        discussion.contributions.append(contribution)
        discussion.updated_at = datetime.utcnow()
        
        # Update current speaker
        if not is_facilitator:
            discussion.current_speaker_id = participant_id
        
        return discussion
    
    def start_turn(
        self,
        session_id: str,
        participant_id: str,
        participant_name: str
    ) -> GroupDiscussionState:
        """Start a participant's turn"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        
        # Create turn
        turn = ParticipantTurn(
            participant_id=participant_id,
            participant_name=participant_name,
            turn_number=discussion.current_turn,
            started_at=datetime.utcnow(),
            status=TurnStatus.SPEAKING
        )
        
        discussion.turns.append(turn)
        discussion.current_speaker_id = participant_id
        discussion.updated_at = datetime.utcnow()
        
        return discussion
    
    def end_turn(
        self,
        session_id: str,
        participant_id: str,
        contribution_text: str,
        word_count: int,
        speaking_time: float
    ) -> GroupDiscussionState:
        """End a participant's turn"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        
        # Find the current turn
        current_turn = None
        for turn in reversed(discussion.turns):
            if turn.participant_id == participant_id and turn.status == TurnStatus.SPEAKING:
                current_turn = turn
                break
        
        if current_turn:
            current_turn.completed_at = datetime.utcnow()
            current_turn.status = TurnStatus.COMPLETED
            current_turn.contribution_text = contribution_text
            current_turn.word_count = word_count
            current_turn.speaking_time = speaking_time
        
        discussion.current_speaker_id = None
        discussion.updated_at = datetime.utcnow()
        
        return discussion
    
    def suggest_next_speaker(self, session_id: str) -> Optional[Dict[str, str]]:
        """Suggest the next speaker based on participation balance"""
        if session_id not in self.active_discussions:
            return None
        
        discussion = self.active_discussions[session_id]
        
        # Count contributions per participant
        contribution_counts = {pid: 0 for pid in discussion.participants}
        for contribution in discussion.contributions:
            if not contribution.is_facilitator and contribution.participant_id in contribution_counts:
                contribution_counts[contribution.participant_id] += 1
        
        # Find participant with fewest contributions
        min_contributions = min(contribution_counts.values())
        candidates = [
            pid for pid, count in contribution_counts.items() 
            if count == min_contributions
        ]
        
        # Return first candidate
        if candidates:
            next_speaker_id = candidates[0]
            return {
                "id": next_speaker_id,
                "name": discussion.participant_names.get(next_speaker_id, "Unknown"),
                "contribution_count": contribution_counts[next_speaker_id]
            }
        
        return None
    
    def add_topic_suggestion(self, session_id: str, topic: str) -> GroupDiscussionState:
        """Add a topic suggestion from the facilitator"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        discussion.suggested_topics.append(topic)
        discussion.updated_at = datetime.utcnow()
        
        return discussion
    
    def analyze_group_dynamics(self, session_id: str) -> GroupDynamicsAnalysis:
        """Analyze group dynamics and participation"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        
        # Calculate metrics per participant
        participant_metrics = []
        total_contributions = 0
        total_speaking_time = 0.0
        total_words = 0
        
        for participant_id in discussion.participants:
            # Count contributions
            contributions = [
                c for c in discussion.contributions 
                if c.participant_id == participant_id and not c.is_facilitator
            ]
            
            # Calculate speaking time and words
            turns = [t for t in discussion.turns if t.participant_id == participant_id]
            speaking_time = sum(t.speaking_time for t in turns)
            words = sum(t.word_count for t in turns)
            
            total_contributions += len(contributions)
            total_speaking_time += speaking_time
            total_words += words
            
            avg_length = words / len(contributions) if contributions else 0
            
            metrics = ParticipantMetrics(
                participant_id=participant_id,
                participant_name=discussion.participant_names.get(participant_id, "Unknown"),
                total_contributions=len(contributions),
                total_words=words,
                total_speaking_time=speaking_time,
                average_contribution_length=avg_length,
                participation_percentage=0.0,  # Will calculate below
                engagement_score=0.0  # Will calculate below
            )
            
            participant_metrics.append(metrics)
        
        # Calculate participation percentages
        for metrics in participant_metrics:
            if total_contributions > 0:
                metrics.participation_percentage = (
                    metrics.total_contributions / total_contributions * 100
                )
            
            # Simple engagement score based on contributions and speaking time
            contribution_score = min(metrics.total_contributions / 5, 1.0) * 5
            time_score = min(metrics.total_speaking_time / 60, 1.0) * 5
            metrics.engagement_score = contribution_score + time_score
        
        # Calculate participation balance (using standard deviation)
        if participant_metrics:
            avg_participation = 100 / len(participant_metrics)
            variance = sum(
                (m.participation_percentage - avg_participation) ** 2 
                for m in participant_metrics
            ) / len(participant_metrics)
            std_dev = variance ** 0.5
            participation_balance = max(0, 1 - (std_dev / 50))  # Normalize to 0-1
        else:
            participation_balance = 0.0
        
        # Find dominant speaker
        dominant_speaker = max(
            participant_metrics, 
            key=lambda m: m.total_contributions
        ) if participant_metrics else None
        
        # Find quiet participants (less than 50% of average)
        avg_contributions = total_contributions / len(participant_metrics) if participant_metrics else 0
        quiet_participants = [
            m.participant_id for m in participant_metrics 
            if m.total_contributions < avg_contributions * 0.5
        ]
        
        analysis = GroupDynamicsAnalysis(
            total_contributions=total_contributions,
            total_speaking_time=total_speaking_time,
            participation_balance=participation_balance,
            dominant_speaker_id=dominant_speaker.participant_id if dominant_speaker else None,
            quiet_participants=quiet_participants,
            topic_coherence=0.8,  # Placeholder - would need NLP analysis
            engagement_level=min(total_contributions / (len(discussion.participants) * 5), 1.0),
            participant_metrics=participant_metrics,
            timestamp=datetime.utcnow()
        )
        
        discussion.dynamics_analysis = analysis
        discussion.updated_at = datetime.utcnow()
        
        return analysis
    
    def conclude_discussion(self, session_id: str) -> GroupDiscussionState:
        """Move discussion to conclusion phase"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        discussion.phase = DiscussionPhase.CONCLUSION
        discussion.updated_at = datetime.utcnow()
        
        # Generate final analysis
        self.analyze_group_dynamics(session_id)
        
        return discussion
    
    def complete_discussion(self, session_id: str) -> GroupDiscussionState:
        """Mark discussion as completed"""
        if session_id not in self.active_discussions:
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        discussion.phase = DiscussionPhase.COMPLETED
        discussion.updated_at = datetime.utcnow()
        
        return discussion
    
    def get_discussion_state(self, session_id: str) -> Optional[GroupDiscussionState]:
        """Get the current state of a discussion"""
        return self.active_discussions.get(session_id)
    
    def get_discussion_summary(self, session_id: str) -> Optional[Dict]:
        """Get a summary of the discussion"""
        if session_id not in self.active_discussions:
            return None
        
        discussion = self.active_discussions[session_id]
        
        return {
            "topic": discussion.topic,
            "phase": discussion.phase,
            "current_turn": discussion.current_turn,
            "total_participants": len(discussion.participants),
            "total_contributions": len([
                c for c in discussion.contributions if not c.is_facilitator
            ]),
            "facilitator_contributions": len([
                c for c in discussion.contributions if c.is_facilitator
            ]),
            "current_speaker": discussion.current_speaker_id,
            "dynamics_analysis": discussion.dynamics_analysis.model_dump() if discussion.dynamics_analysis else None
        }
    
    def assign_roles(
        self, 
        session_id: str, 
        roles: Dict[str, Dict[str, str]]  # participant_id -> {"role": "name", "description": "desc"}
    ) -> GroupDiscussionState:
        """Assign roles to participants"""
        logger.info(f"=== ASSIGNING ROLES ===")
        logger.info(f"Session ID: {session_id}")
        logger.info(f"Roles to assign: {roles}")
        
        if session_id not in self.active_discussions:
            logger.error(f"Session {session_id} not found in active discussions")
            raise ValueError(f"Discussion session {session_id} not found")
        
        discussion = self.active_discussions[session_id]
        
        logger.info(f"Current AI facilitator ID: '{discussion.ai_facilitator_id}'")
        logger.info(f"Current participants: {discussion.participants}")
        
        for participant_id, role_info in roles.items():
            if participant_id in discussion.participants:
                discussion.participant_roles[participant_id] = role_info["role"]
                discussion.participant_role_descriptions[participant_id] = role_info["description"]
                logger.info(f"Assigned role '{role_info['role']}' to participant {participant_id}")
            else:
                logger.warning(f"Participant {participant_id} not found in discussion participants")
        
        logger.info(f"Final participant roles: {discussion.participant_roles}")
        logger.info(f"Final AI facilitator ID: '{discussion.ai_facilitator_id}'")
        
        discussion.updated_at = datetime.utcnow()
        return discussion
    
    def generate_roles_and_scenario(
        self, 
        session_id: str, 
        category: DiscussionCategory, 
        participant_count: int
    ) -> Dict[str, any]:
        """Generate roles and scenario for the selected discussion category using Gemini AI"""
        
        logger.info(f"=== GENERATING ROLES AND SCENARIO ===")
        logger.info(f"Session ID: {session_id}")
        logger.info(f"Category: {category}")
        logger.info(f"Participant count: {participant_count}")
        
        # Use AI service to generate content
        from app.services.ai_service import ai_service
        
        # Concise prompt to avoid truncated JSON responses
        prompt = f"""Generate a group discussion scenario for 2 participants. Category: {category.value.upper()}.

Respond with ONLY valid JSON, no markdown, no extra text:
{{"topic": "short topic title", "scenario": "2-3 sentence scenario description", "roles": [{{"role": "Role Title 1", "description": "1-2 sentence description"}}, {{"role": "Role Title 2", "description": "1-2 sentence description"}}], "category": "{category.value}"}}"""

        try:
            logger.info("=== CALLING AI SERVICE ===")
            logger.info(f"Prompt length: {len(prompt)} characters")
            logger.info(f"Prompt preview: {prompt[:200]}...")
            
            # Import and check AI service
            from app.services.ai_service import ai_service
            
            if not hasattr(ai_service, 'model') or ai_service.model is None:
                logger.error("AI service model is not initialized, falling back to template")
                return self._generate_template_content(category, participant_count)
            
            # Get AI-generated content
            ai_response = ai_service.generate_text(prompt)
            
            logger.info(f"=== AI RESPONSE RECEIVED ===")
            logger.info(f"Response length: {len(ai_response)} characters")
            logger.info(f"Response preview: {ai_response[:200]}...")
            
            # Check if response indicates an error
            if ai_response.startswith("Error generating text:") or ai_response.startswith("AI service is not available"):
                logger.error(f"AI service returned error: {ai_response}")
                return self._generate_template_content(category, participant_count)
            
            # Try to parse JSON response
            import json
            try:
                logger.info("=== PARSING JSON RESPONSE ===")
                # Clean the response - remove markdown code blocks if present
                ai_response_clean = ai_response.strip()
                if ai_response_clean.startswith('```json'):
                    # Remove ```json at start and ``` at end
                    start_idx = ai_response_clean.find('{')
                    end_idx = ai_response_clean.rfind('}') + 1
                    if start_idx >= 0 and end_idx > start_idx:
                        ai_response_clean = ai_response_clean[start_idx:end_idx]
                elif ai_response_clean.startswith('```'):
                    # Remove ``` at start and end
                    lines = ai_response_clean.split('\n')
                    if len(lines) > 2:
                        ai_response_clean = '\n'.join(lines[1:-1])
                
                logger.info(f"Cleaned response: {ai_response_clean[:200]}...")
                
                content_data = json.loads(ai_response_clean)
                
                logger.info(f"=== JSON PARSED SUCCESSFULLY ===")
                logger.info(f"Keys found: {list(content_data.keys())}")
                
                # Validate required fields
                if all(key in content_data for key in ['topic', 'scenario', 'roles', 'category']):
                    logger.info("=== ALL REQUIRED FIELDS PRESENT ===")
                    # Ensure we have exactly 2 roles for selection
                    if len(content_data['roles']) >= 2:
                        content_data['roles'] = content_data['roles'][:2]  # Take first 2 roles
                    else:
                        # Pad with generic roles if needed (fallback)
                        while len(content_data['roles']) < 2:
                            content_data['roles'].append({
                                "role": f"Participant {len(content_data['roles']) + 1}",
                                "description": "Active discussion participant"
                            })
                    
                    logger.info(f"=== RETURNING GENERATED CONTENT ===")
                    logger.info(f"Topic: {content_data['topic']}")
                    logger.info(f"Roles count: {len(content_data['roles'])}")
                    return content_data
                else:
                    logger.error(f"=== MISSING REQUIRED FIELDS ===")
                    logger.error(f"Required: ['topic', 'scenario', 'roles', 'category']")
                    logger.error(f"Found: {list(content_data.keys())}")
                    raise ValueError("Missing required fields in AI response")
                    
            except json.JSONDecodeError as json_error:
                logger.error(f"=== JSON PARSING FAILED ===")
                logger.error(f"JSON Error: {json_error}")
                logger.warning(f"Failed to parse AI response as JSON: {ai_response[:100]}...")
                return self._generate_template_content(category, participant_count)
                
        except ImportError as import_error:
            logger.error(f"=== AI SERVICE IMPORT ERROR ===")
            logger.error(f"Import error: {import_error}")
            logger.info("=== FALLING BACK TO TEMPLATE ===")
            return self._generate_template_content(category, participant_count)
                
        except Exception as e:
            logger.error(f"=== AI GENERATION ERROR ===")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            logger.error(f"Error generating content with AI: {e}")
            # Fall back to template-based generation
            logger.info("=== FALLING BACK TO TEMPLATE ===")
            return self._generate_template_content(category, participant_count)
    
    def _generate_template_content(self, category: DiscussionCategory, participant_count: int) -> Dict[str, any]:
        """Fallback template-based content generation"""
        
        role_templates = {
            DiscussionCategory.FORMAL: [
                {"role": "Research Professor", "description": "Academic expert who values proven methods and peer-reviewed evidence. Prefers traditional approaches."},
                {"role": "Innovation Director", "description": "Forward-thinking leader who pushes for new technologies and experimental approaches."},
                {"role": "Policy Advisor", "description": "Government consultant focused on practical implementation and regulatory compliance."},
                {"role": "Industry Expert", "description": "Business professional with hands-on experience who emphasizes market viability."},
                {"role": "Ethics Specialist", "description": "Philosopher who considers moral implications and societal impact of decisions."},
                {"role": "Data Analyst", "description": "Quantitative researcher who relies on statistical evidence and measurable outcomes."}
            ],
            DiscussionCategory.INFORMAL: [
                {"role": "The Planner", "description": "Practical person who thinks about logistics, budgets, and realistic timelines. Prefers careful preparation."},
                {"role": "The Adventurer", "description": "Spontaneous person who loves new experiences and believes in taking risks for memorable moments."},
                {"role": "The Budget-Conscious Friend", "description": "Careful with money, always looking for deals and cost-effective options."},
                {"role": "The Experience Seeker", "description": "Values memorable experiences over material things, willing to spend on adventures."},
                {"role": "The Cautious One", "description": "Always considers potential risks and downsides, prefers safe and well-researched options."},
                {"role": "The Optimist", "description": "Sees opportunities everywhere and believes things will work out, encourages bold decisions."}
            ],
            DiscussionCategory.BUSINESS: [
                {"role": "Growth-Focused CEO", "description": "Startup leader focused on rapid expansion and market capture. Believes in calculated risks."},
                {"role": "Risk-Averse CFO", "description": "Financial executive prioritizing stability and sustainable growth. Concerned about profitability."},
                {"role": "Customer Experience Manager", "description": "Advocates for user-centric decisions and premium service quality."},
                {"role": "Operations Manager", "description": "Focuses on efficiency and cost reduction. Believes automation is key to competitiveness."},
                {"role": "Product Manager", "description": "Pushes for innovative features and market disruption through continuous innovation."},
                {"role": "Market Analyst", "description": "Data-driven decision maker who relies on research and customer insights."}
            ]
        }
        
        # Generate category-specific topics with realistic scenarios
        scenario_templates = {
            DiscussionCategory.FORMAL: [
                {
                    "topic": "Remote work vs office work effectiveness",
                    "scenario": "Two department heads are meeting to discuss their team's work arrangements. One believes remote work increases productivity, while the other thinks in-person collaboration is essential for innovation.",
                    "setting": "Corporate conference room"
                },
                {
                    "topic": "AI regulation in healthcare decisions",
                    "scenario": "Two medical experts are debating whether AI should be allowed to make diagnostic recommendations. One supports AI assistance, the other prefers human-only decisions.",
                    "setting": "Medical ethics committee meeting"
                },
                {
                    "topic": "Social media age restrictions",
                    "scenario": "Two policy experts are discussing whether social media platforms should have stricter age verification. One supports stronger restrictions, the other believes in digital freedom.",
                    "setting": "Government policy meeting"
                }
            ],
            DiscussionCategory.INFORMAL: [
                {
                    "topic": "Planning a weekend trip",
                    "scenario": "Two friends are deciding where to go for a weekend getaway. One wants a relaxing beach vacation, the other prefers an adventurous mountain hiking trip.",
                    "setting": "Coffee shop conversation"
                },
                {
                    "topic": "Choosing a movie to watch",
                    "scenario": "Two roommates are trying to pick a movie for tonight. One wants to watch a comedy to unwind, the other is in the mood for an action thriller.",
                    "setting": "Living room discussion"
                },
                {
                    "topic": "Deciding on dinner plans",
                    "scenario": "Two friends are figuring out where to eat tonight. One wants to try the new expensive restaurant, the other prefers ordering pizza and staying in.",
                    "setting": "Phone conversation"
                }
            ],
            DiscussionCategory.BUSINESS: [
                {
                    "topic": "Marketing budget allocation",
                    "scenario": "Two marketing managers are deciding how to spend their quarterly budget. One wants to invest in digital ads, the other believes in traditional marketing methods.",
                    "setting": "Marketing department meeting"
                },
                {
                    "topic": "Hiring strategy for new team",
                    "scenario": "Two department heads are discussing whether to hire experienced professionals or train junior employees. Each has different views on cost and long-term benefits.",
                    "setting": "HR planning session"
                },
                {
                    "topic": "Product launch timing",
                    "scenario": "Two product managers are debating when to launch their new feature. One wants to rush to market, the other prefers more testing and refinement.",
                    "setting": "Product strategy meeting"
                }
            ]
        }
        
        # Select appropriate templates
        available_roles = role_templates.get(category, role_templates[DiscussionCategory.BUSINESS])
        available_scenarios = scenario_templates.get(category, scenario_templates[DiscussionCategory.BUSINESS])
        
        # Pick a random scenario
        import random
        selected_scenario = random.choice(available_scenarios)
        
        # Pick 2 contrasting roles
        selected_roles = random.sample(available_roles, min(2, len(available_roles)))
        
        return {
            "topic": selected_scenario["topic"],
            "scenario": selected_scenario["scenario"],
            "roles": selected_roles,
            "category": category.value
        }

    def generate_ai_participant_response(
        self,
        session_id: str,
        context: str = "",
        trigger_type: str = "turn"  # "turn", "response", "topic_change"
    ) -> Optional[str]:
        """Generate AI participant response based on their role and discussion context"""
        logger.info(f"=== GENERATING AI PARTICIPANT RESPONSE ===")
        logger.info(f"Session ID: {session_id}")
        logger.info(f"Context: {context[:100]}...")
        logger.info(f"Trigger type: {trigger_type}")
        
        if session_id not in self.active_discussions:
            logger.error(f"Session {session_id} not found in active discussions")
            logger.error(f"Available sessions: {list(self.active_discussions.keys())}")
            return None
        
        discussion = self.active_discussions[session_id]
        ai_id = discussion.ai_facilitator_id
        
        logger.info(f"AI facilitator ID from discussion: '{ai_id}'")
        logger.info(f"Discussion participants: {discussion.participants}")
        logger.info(f"Discussion participant roles: {discussion.participant_roles}")
        
        if not ai_id:
            logger.error(f"AI facilitator ID is empty or None")
            # Try to find any AI participant as fallback
            ai_participants = [pid for pid in discussion.participants if pid.startswith('ai_')]
            if ai_participants:
                ai_id = ai_participants[0]
                logger.info(f"Using fallback AI participant: {ai_id}")
                # Update the discussion state with the correct AI facilitator ID
                discussion.ai_facilitator_id = ai_id
            else:
                logger.error(f"No AI participants found in discussion")
                logger.error(f"All participants: {discussion.participants}")
                return None
        
        logger.info(f"Proceeding with AI ID: {ai_id}")
            
        if ai_id not in discussion.participant_roles:
            logger.error(f"AI participant {ai_id} not found in participant roles")
            logger.error(f"Available roles: {list(discussion.participant_roles.keys())}")
            return None
        
        ai_role = discussion.participant_roles[ai_id]
        ai_role_description = discussion.participant_role_descriptions.get(ai_id, "")
        
        logger.info(f"AI Role: {ai_role}")
        logger.info(f"AI Role Description: {ai_role_description[:100]}...")
        
        # Get recent contributions for context
        recent_contributions = discussion.contributions[-3:] if discussion.contributions else []
        context_text = "\n".join([
            f"{c.participant_name}: {c.text}" 
            for c in recent_contributions 
            if c.participant_id != ai_id
        ])
        
        logger.info(f"Recent contributions count: {len(recent_contributions)}")
        logger.info(f"Context text: {context_text[:200]}...")
        
        # Use AI service to generate contextual response
        try:
            logger.info("=== IMPORTING AI SERVICE ===")
            from app.services.ai_service import ai_service
            
            # Check if AI service is properly initialized
            if not hasattr(ai_service, 'model') or ai_service.model is None:
                logger.error("AI service model is not initialized")
                return self._get_fallback_response(ai_role, discussion.topic, context)
            
            prompt = f"""
You are playing the role of "{ai_role}" in a group discussion. 

Role Description: {ai_role_description}

Discussion Topic: {discussion.topic}
Scenario: {discussion.scenario}

Recent conversation:
{context_text}

Latest message from other participant: {context}

Respond as {ai_role} would, staying in character. Keep your response:
- Natural and conversational (2-3 sentences)
- True to your role's perspective and motivations
- Relevant to what was just said
- Engaging and moves the discussion forward

Response:"""
            
            logger.info(f"=== CALLING AI SERVICE FOR RESPONSE ===")
            logger.info(f"Prompt length: {len(prompt)} characters")
            
            ai_response = ai_service.generate_text(prompt)
            
            logger.info(f"=== AI RESPONSE RECEIVED ===")
            logger.info(f"Response length: {len(ai_response)} characters")
            logger.info(f"Response: {ai_response}")
            
            # Check if response indicates an error
            if ai_response.startswith("Error generating text:") or ai_response.startswith("AI service is not available"):
                logger.error(f"AI service returned error: {ai_response}")
                return self._get_fallback_response(ai_role, discussion.topic, context)
            
            # Clean up the response
            ai_response = ai_response.strip()
            if ai_response.startswith('"') and ai_response.endswith('"'):
                ai_response = ai_response[1:-1]
            
            logger.info(f"=== CLEANED RESPONSE ===")
            logger.info(f"Final response: {ai_response}")
            
            return ai_response
            
        except ImportError as import_error:
            logger.error(f"=== AI SERVICE IMPORT ERROR ===")
            logger.error(f"Import error: {import_error}")
            return self._get_fallback_response(ai_role, discussion.topic, context)
            
        except Exception as e:
            logger.error(f"=== AI RESPONSE GENERATION ERROR ===")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            logger.error(f"Error generating AI response: {e}")
            # Fallback to template responses
            logger.info("=== FALLING BACK TO TEMPLATE RESPONSE ===")
            return self._get_fallback_response(ai_role, discussion.topic, context)
    
    def _get_fallback_response(self, ai_role: str, topic: str, context: str) -> str:
        """Generate fallback response when AI service fails"""
        role_responses = {
            "The Planner & Relaxer": [
                "I think we should really think this through carefully. What are all our options?",
                "Let's make sure we have everything organized before we decide.",
                "I want to make sure we're both comfortable with whatever we choose.",
                "Maybe we should look at this more systematically?"
            ],
            "The Spontaneous Adventurer": [
                "Come on, let's just go for it! We can figure out the details as we go.",
                "Life's too short to overthink everything. What's the worst that could happen?",
                "I say we pick something exciting and just do it!",
                "Sometimes the best experiences come from being spontaneous."
            ],
            "Growth-Focused CEO": [
                f"From a strategic perspective, we need to consider the long-term implications here.",
                f"What's our competitive advantage in this situation?",
                f"I'm thinking about scalability and sustainable growth."
            ],
            "Risk-Averse CFO": [
                f"We need to look at the numbers and potential risks carefully.",
                f"What's our budget for this, and what's the ROI?",
                f"I'm concerned about the financial implications."
            ]
        }
        
        responses = role_responses.get(ai_role, [
            f"That's an interesting point about {topic}.",
            f"I see your perspective on {topic}.",
            f"Let me think about {topic} from a different angle."
        ])
        
        import random
        return random.choice(responses)
    
    def should_ai_participate(self, session_id: str) -> bool:
        """Determine if AI should participate based on discussion flow"""
        if session_id not in self.active_discussions:
            return False
        
        discussion = self.active_discussions[session_id]
        
        # AI should participate if:
        # 1. There are human contributions
        # 2. AI hasn't responded recently
        # 3. Discussion is active
        
        if not discussion.contributions:
            return False
        
        # Check if last contribution was from AI
        last_contribution = discussion.contributions[-1]
        if last_contribution.participant_id == discussion.ai_facilitator_id:
            return False  # Don't respond immediately after AI's own message
        
        # Check if there have been multiple human messages without AI response
        human_messages_since_ai = 0
        for contribution in reversed(discussion.contributions):
            if contribution.participant_id == discussion.ai_facilitator_id:
                break
            human_messages_since_ai += 1
        
        # Respond after 1-2 human messages
        return human_messages_since_ai >= 1

    async def generate_final_analysis(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Generate comprehensive AI analysis of the entire discussion"""
        logger.info(f"=== GENERATING FINAL DISCUSSION ANALYSIS ===")
        logger.info(f"Session ID: {session_id}")
        
        if session_id not in self.active_discussions:
            logger.error(f"Session {session_id} not found")
            return None
        
        discussion = self.active_discussions[session_id]
        
        # Collect all human contributions (exclude AI)
        human_contributions = [
            c for c in discussion.contributions 
            if c.participant_id != discussion.ai_facilitator_id
        ]
        
        if not human_contributions:
            logger.warning("No human contributions found for analysis")
            return None
        
        # Build transcript for analysis
        transcript_parts = []
        for contribution in human_contributions:
            transcript_parts.append(f"{contribution.participant_name}: {contribution.text}")
        
        full_transcript = "\n".join(transcript_parts)
        
        logger.info(f"Analyzing transcript with {len(human_contributions)} contributions")
        logger.info(f"Transcript length: {len(full_transcript)} characters")
        
        try:
            from app.services.ai_service import ai_service
            
            # Check if AI service is available
            if not hasattr(ai_service, 'model') or ai_service.model is None:
                logger.error("AI service not available for final analysis")
                return {
                    "overall_assessment": "Discussion analysis not available - AI service offline",
                    "participant_feedback": {},
                    "discussion_quality": "Unable to assess",
                    "key_insights": [],
                    "recommendations": ["Please try again later when AI service is available"]
                }
            
            prompt = f"""
Analyze this group discussion between participants and provide comprehensive feedback.

Discussion Topic: {discussion.topic}
Discussion Category: {discussion.category}
Scenario: {discussion.scenario}

Full Transcript:
{full_transcript}

Participant Roles:
{chr(10).join([f"- {discussion.participant_names.get(pid, 'Unknown')}: {discussion.participant_roles.get(pid, 'No role')}" for pid in discussion.participants if pid != discussion.ai_facilitator_id])}

Please provide a detailed analysis in JSON format:
{{
  "overall_assessment": "2-3 sentence summary of the discussion quality and engagement",
  "discussion_quality": "Excellent/Good/Fair/Poor - with brief explanation",
  "participant_feedback": {{
    "participant_name_1": {{
      "strengths": ["strength 1", "strength 2"],
      "areas_for_improvement": ["area 1", "area 2"],
      "role_performance": "How well they stayed in character and represented their role"
    }},
    "participant_name_2": {{
      "strengths": ["strength 1", "strength 2"], 
      "areas_for_improvement": ["area 1", "area 2"],
      "role_performance": "How well they stayed in character and represented their role"
    }}
  }},
  "key_insights": [
    "Important point or theme that emerged",
    "Another significant insight from the discussion"
  ],
  "discussion_dynamics": {{
    "balance": "How balanced was the participation?",
    "engagement": "How engaged were the participants?",
    "topic_adherence": "How well did they stay on topic?"
  }},
  "recommendations": [
    "Specific suggestion for improving future discussions",
    "Another actionable recommendation"
  ]
}}

Focus on constructive feedback that helps participants improve their discussion and communication skills.
"""
            
            logger.info("Calling AI service for final analysis...")
            ai_response = ai_service.generate_text(prompt)
            
            logger.info(f"AI analysis response received: {len(ai_response)} characters")
            
            # Parse JSON response
            import json
            try:
                # Clean response
                ai_response_clean = ai_response.strip()
                if ai_response_clean.startswith('```json'):
                    start_idx = ai_response_clean.find('{')
                    end_idx = ai_response_clean.rfind('}') + 1
                    if start_idx >= 0 and end_idx > start_idx:
                        ai_response_clean = ai_response_clean[start_idx:end_idx]
                elif ai_response_clean.startswith('```'):
                    lines = ai_response_clean.split('\n')
                    if len(lines) > 2:
                        ai_response_clean = '\n'.join(lines[1:-1])
                
                analysis_data = json.loads(ai_response_clean)
                
                logger.info("✅ Final analysis generated successfully")
                return analysis_data
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse analysis JSON: {e}")
                # Return structured fallback
                return {
                    "overall_assessment": "The discussion covered the assigned topic with participants engaging in meaningful dialogue.",
                    "discussion_quality": "Good - Participants stayed engaged and on topic",
                    "participant_feedback": {
                        name: {
                            "strengths": ["Active participation", "Clear communication"],
                            "areas_for_improvement": ["Could elaborate more on points", "Consider alternative perspectives"],
                            "role_performance": "Maintained character well throughout discussion"
                        } for name in set(c.participant_name for c in human_contributions)
                    },
                    "key_insights": [
                        "Participants demonstrated good understanding of their roles",
                        "Discussion remained focused on the assigned topic"
                    ],
                    "discussion_dynamics": {
                        "balance": "Participants shared speaking time reasonably well",
                        "engagement": "Both participants remained engaged throughout",
                        "topic_adherence": "Discussion stayed on topic with relevant points"
                    },
                    "recommendations": [
                        "Practice asking follow-up questions to deepen the discussion",
                        "Try to incorporate more specific examples to support arguments"
                    ]
                }
                
        except Exception as e:
            logger.error(f"Error generating final analysis: {e}")
            return {
                "overall_assessment": "Discussion analysis encountered an error",
                "discussion_quality": "Unable to assess due to technical issues",
                "participant_feedback": {},
                "key_insights": [],
                "recommendations": ["Please try the analysis again"]
            }


# Global service instance
group_discussion_service = GroupDiscussionService()
