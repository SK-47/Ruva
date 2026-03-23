"""
JAM (Just-A-Minute) Mode Implementation
Handles single-player practice with hesitation, repetition, and deviation detection.
"""

from typing import Dict, List, Optional, Set
from datetime import datetime
from pydantic import BaseModel
from enum import Enum
import re


class JAMPhase(str, Enum):
    SETUP = "setup"
    TOPIC_GIVEN = "topic_given"
    SPEAKING = "speaking"
    ANALYSIS = "analysis"
    COMPLETED = "completed"


class MistakeType(str, Enum):
    HESITATION = "hesitation"
    REPETITION = "repetition"
    DEVIATION = "deviation"


class JAMMistake(BaseModel):
    mistake_type: MistakeType
    description: str
    timestamp: datetime
    word_or_phrase: Optional[str] = None
    severity: int = 1  # 1-3, higher is more severe


class JAMAttempt(BaseModel):
    attempt_number: int
    topic: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    transcript: str = ""
    duration: float = 0.0  # seconds
    word_count: int = 0
    mistakes: List[JAMMistake] = []
    hesitation_count: int = 0
    repetition_count: int = 0
    deviation_count: int = 0
    score: float = 0.0  # 0-100


class JAMFeedback(BaseModel):
    overall_score: float
    strengths: List[str]
    areas_for_improvement: List[str]
    specific_mistakes: List[JAMMistake]
    suggestions: List[str]
    next_topic_suggestion: Optional[str] = None
    timestamp: datetime


class JAMCoachingMode(str, Enum):
    SILENT = "silent"  # No interruptions, feedback after
    GENTLE = "gentle"  # Occasional encouragement
    ACTIVE = "active"  # Real-time coaching and interruptions
    STRICT = "strict"  # Immediate corrections like real JAM

class JAMCoachMessage(BaseModel):
    message_type: str  # "encouragement", "correction", "tip", "challenge"
    content: str
    timestamp: datetime
    should_interrupt: bool = False

class JAMState(BaseModel):
    room_id: str
    session_id: str
    participant_id: str
    participant_name: str
    ai_coach_id: str
    phase: JAMPhase
    coaching_mode: JAMCoachingMode = JAMCoachingMode.GENTLE
    current_topic: Optional[str] = None
    topic_genre: Optional[str] = None
    previous_genres: List[str] = []
    attempts: List[JAMAttempt] = []
    current_attempt: Optional[JAMAttempt] = None
    total_attempts: int = 0
    coach_messages: List[JAMCoachMessage] = []
    difficulty_level: int = 1  # 1-5, affects topic complexity and coaching strictness
    created_at: datetime
    updated_at: datetime


class JAMModeService:
    """Service for managing JAM mode sessions"""
    
    # Common filler words that indicate hesitation
    FILLER_WORDS = {
        "um", "uh", "er", "ah", "like", "you know", "sort of", "kind of",
        "basically", "actually", "literally", "well", "so", "right", "okay"
    }
    
    # Topic genres for variety
    TOPIC_GENRES = [
        "history", "science", "technology", "arts", "sports", "food",
        "travel", "nature", "entertainment", "current_events", "philosophy",
        "literature", "music", "business", "health", "education"
    ]
    
    def __init__(self):
        self.active_sessions: Dict[str, JAMState] = {}
    
    def create_jam_session(
        self,
        room_id: str,
        session_id: str,
        participant_id: str,
        participant_name: str,
        ai_coach_id: str
    ) -> JAMState:
        """Create a new JAM session"""
        
        jam_state = JAMState(
            room_id=room_id,
            session_id=session_id,
            participant_id=participant_id,
            participant_name=participant_name,
            ai_coach_id=ai_coach_id,
            phase=JAMPhase.SETUP,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.active_sessions[session_id] = jam_state
        return jam_state
    
    def set_topic(
        self,
        session_id: str,
        topic: str,
        genre: Optional[str] = None
    ) -> JAMState:
        """Set a new topic for the JAM session"""
        if session_id not in self.active_sessions:
            raise ValueError(f"JAM session {session_id} not found")
        
        jam = self.active_sessions[session_id]
        
        # Validate genre variety
        if genre and genre in jam.previous_genres[-1:]:
            raise ValueError(f"Cannot use same genre '{genre}' consecutively")
        
        jam.current_topic = topic
        jam.topic_genre = genre
        if genre:
            jam.previous_genres.append(genre)
        jam.phase = JAMPhase.TOPIC_GIVEN
        jam.updated_at = datetime.utcnow()
        
        return jam
    
    def start_attempt(self, session_id: str) -> JAMState:
        """Start a new speaking attempt"""
        if session_id not in self.active_sessions:
            raise ValueError(f"JAM session {session_id} not found")
        
        jam = self.active_sessions[session_id]
        
        if not jam.current_topic:
            raise ValueError("No topic set for this session")
        
        # Create new attempt
        attempt = JAMAttempt(
            attempt_number=jam.total_attempts + 1,
            topic=jam.current_topic,
            started_at=datetime.utcnow()
        )
        
        jam.current_attempt = attempt
        jam.phase = JAMPhase.SPEAKING
        jam.updated_at = datetime.utcnow()
        
        return jam
    
    def set_coaching_mode(self, session_id: str, mode: JAMCoachingMode) -> JAMState:
        """Set the coaching mode for the session"""
        if session_id not in self.active_sessions:
            raise ValueError(f"JAM session {session_id} not found")
        
        jam = self.active_sessions[session_id]
        jam.coaching_mode = mode
        jam.updated_at = datetime.utcnow()
        return jam
    
    def add_coach_message(
        self, 
        session_id: str, 
        message_type: str, 
        content: str, 
        should_interrupt: bool = False
    ) -> JAMState:
        """Add a coaching message during the session"""
        if session_id not in self.active_sessions:
            raise ValueError(f"JAM session {session_id} not found")
        
        jam = self.active_sessions[session_id]
        
        message = JAMCoachMessage(
            message_type=message_type,
            content=content,
            timestamp=datetime.utcnow(),
            should_interrupt=should_interrupt
        )
        
        jam.coach_messages.append(message)
        jam.updated_at = datetime.utcnow()
        return jam
    
    def generate_real_time_coaching(
        self, 
        session_id: str, 
        current_transcript: str, 
        speaking_duration: float
    ) -> Optional[JAMCoachMessage]:
        """Generate real-time coaching based on current performance"""
        if session_id not in self.active_sessions:
            return None
        
        jam = self.active_sessions[session_id]
        
        if jam.coaching_mode == JAMCoachingMode.SILENT:
            return None
        
        # Analyze current performance
        words = current_transcript.lower().split()
        recent_words = words[-10:] if len(words) > 10 else words
        
        # Check for excessive hesitation
        filler_count = sum(1 for word in recent_words if word in self.FILLER_WORDS)
        if filler_count >= 3 and jam.coaching_mode in [JAMCoachingMode.ACTIVE, JAMCoachingMode.STRICT]:
            return JAMCoachMessage(
                message_type="correction",
                content="I notice some hesitation. Take a breath and continue with confidence!",
                timestamp=datetime.utcnow(),
                should_interrupt=(jam.coaching_mode == JAMCoachingMode.STRICT)
            )
        
        # Check for repetition
        if len(recent_words) >= 4:
            for i in range(len(recent_words) - 3):
                if recent_words[i] == recent_words[i + 2] and recent_words[i + 1] == recent_words[i + 3]:
                    if jam.coaching_mode in [JAMCoachingMode.ACTIVE, JAMCoachingMode.STRICT]:
                        return JAMCoachMessage(
                            message_type="correction",
                            content=f"You're repeating '{recent_words[i]} {recent_words[i + 1]}'. Try a different approach!",
                            timestamp=datetime.utcnow(),
                            should_interrupt=(jam.coaching_mode == JAMCoachingMode.STRICT)
                        )
        
        # Encouragement at milestones
        if speaking_duration > 30 and len(jam.coach_messages) == 0:
            if jam.coaching_mode in [JAMCoachingMode.GENTLE, JAMCoachingMode.ACTIVE]:
                return JAMCoachMessage(
                    message_type="encouragement",
                    content="Great job! You're halfway there. Keep going!",
                    timestamp=datetime.utcnow(),
                    should_interrupt=False
                )
        
        return None
    
    def generate_adaptive_topic(self, session_id: str, difficulty_level: int = None) -> str:
        """Generate a topic adapted to the user's skill level"""
        if session_id not in self.active_sessions:
            raise ValueError(f"JAM session {session_id} not found")
        
        jam = self.active_sessions[session_id]
        
        if difficulty_level:
            jam.difficulty_level = difficulty_level
        
        # Topic templates by difficulty
        topics_by_level = {
            1: [  # Beginner - concrete, personal topics
                "Your favorite food",
                "A memorable vacation",
                "Your pet or a pet you'd like to have",
                "Your daily routine",
                "A hobby you enjoy"
            ],
            2: [  # Intermediate - broader topics
                "The importance of friendship",
                "Technology in daily life",
                "Environmental conservation",
                "The benefits of exercise",
                "Learning new skills"
            ],
            3: [  # Advanced - abstract concepts
                "The role of social media in society",
                "Work-life balance in modern times",
                "The impact of artificial intelligence",
                "Cultural diversity and understanding",
                "Leadership qualities"
            ],
            4: [  # Expert - complex issues
                "The ethics of genetic engineering",
                "Economic inequality solutions",
                "The future of space exploration",
                "Philosophical perspectives on consciousness",
                "Global governance challenges"
            ],
            5: [  # Master - highly abstract/controversial
                "The nature of reality and perception",
                "Moral relativism vs absolute ethics",
                "The singularity and human obsolescence",
                "Post-scarcity economics",
                "The simulation hypothesis"
            ]
        }
        
        import random
        level_topics = topics_by_level.get(jam.difficulty_level, topics_by_level[1])
        return random.choice(level_topics)

    def end_attempt(
        self,
        session_id: str,
        transcript: str,
        duration: float
    ) -> JAMState:
        """End the current speaking attempt"""
        if session_id not in self.active_sessions:
            raise ValueError(f"JAM session {session_id} not found")
        
        jam = self.active_sessions[session_id]
        
        if not jam.current_attempt:
            raise ValueError("No active attempt to end")
        
        # Update attempt
        jam.current_attempt.ended_at = datetime.utcnow()
        jam.current_attempt.transcript = transcript
        jam.current_attempt.duration = duration
        jam.current_attempt.word_count = len(transcript.split())
        
        # Analyze for mistakes
        self._analyze_mistakes(jam.current_attempt)
        
        # Calculate score
        jam.current_attempt.score = self._calculate_score(jam.current_attempt)
        
        # Save attempt
        jam.attempts.append(jam.current_attempt)
        jam.total_attempts += 1
        jam.phase = JAMPhase.ANALYSIS
        jam.updated_at = datetime.utcnow()
        
        return jam
    
    def _analyze_mistakes(self, attempt: JAMAttempt):
        """Analyze transcript for hesitations, repetitions, and deviations"""
        
        # Detect hesitations (filler words)
        words = attempt.transcript.lower().split()
        word_set = set(words)
        
        for filler in self.FILLER_WORDS:
            if filler in word_set:
                count = words.count(filler)
                if count > 0:
                    mistake = JAMMistake(
                        mistake_type=MistakeType.HESITATION,
                        description=f"Used filler word '{filler}' {count} time(s)",
                        timestamp=datetime.utcnow(),
                        word_or_phrase=filler,
                        severity=min(count, 3)
                    )
                    attempt.mistakes.append(mistake)
                    attempt.hesitation_count += count
        
        # Detect repetitions (words used more than 3 times)
        word_counts = {}
        for word in words:
            # Skip common words
            if len(word) > 3 and word not in self.FILLER_WORDS:
                word_counts[word] = word_counts.get(word, 0) + 1
        
        for word, count in word_counts.items():
            if count > 3:
                mistake = JAMMistake(
                    mistake_type=MistakeType.REPETITION,
                    description=f"Repeated word '{word}' {count} times",
                    timestamp=datetime.utcnow(),
                    word_or_phrase=word,
                    severity=min((count - 3), 3)
                )
                attempt.mistakes.append(mistake)
                attempt.repetition_count += 1
        
        # Detect potential deviations (would need topic analysis - placeholder)
        # This would require NLP to compare transcript to topic
        # For now, we'll use a simple heuristic: if topic keywords are missing
        topic_words = attempt.topic.lower().split()
        topic_mentioned = any(word in attempt.transcript.lower() for word in topic_words if len(word) > 3)
        
        if not topic_mentioned and len(words) > 20:
            mistake = JAMMistake(
                mistake_type=MistakeType.DEVIATION,
                description=f"May have deviated from topic '{attempt.topic}'",
                timestamp=datetime.utcnow(),
                severity=2
            )
            attempt.mistakes.append(mistake)
            attempt.deviation_count += 1
    
    def _calculate_score(self, attempt: JAMAttempt) -> float:
        """Calculate overall score for the attempt (0-100)"""
        base_score = 100.0
        
        # Deduct points for mistakes
        for mistake in attempt.mistakes:
            if mistake.mistake_type == MistakeType.HESITATION:
                base_score -= mistake.severity * 2
            elif mistake.mistake_type == MistakeType.REPETITION:
                base_score -= mistake.severity * 3
            elif mistake.mistake_type == MistakeType.DEVIATION:
                base_score -= mistake.severity * 5
        
        # Bonus for duration (closer to 60 seconds is better)
        duration_bonus = 0
        if 50 <= attempt.duration <= 70:
            duration_bonus = 10
        elif 40 <= attempt.duration <= 80:
            duration_bonus = 5
        
        # Bonus for word count (good pace)
        words_per_minute = (attempt.word_count / attempt.duration) * 60 if attempt.duration > 0 else 0
        pace_bonus = 0
        if 140 <= words_per_minute <= 180:
            pace_bonus = 10
        elif 120 <= words_per_minute <= 200:
            pace_bonus = 5
        
        final_score = max(0, min(100, base_score + duration_bonus + pace_bonus))
        return final_score
    
    def generate_feedback(self, session_id: str) -> JAMFeedback:
        """Generate comprehensive feedback for the session"""
        if session_id not in self.active_sessions:
            raise ValueError(f"JAM session {session_id} not found")
        
        jam = self.active_sessions[session_id]
        
        if not jam.attempts:
            raise ValueError("No attempts to analyze")
        
        latest_attempt = jam.attempts[-1]
        
        # Calculate overall score (average of all attempts)
        overall_score = sum(attempt.score for attempt in jam.attempts) / len(jam.attempts)
        
        # Identify strengths
        strengths = []
        if latest_attempt.duration >= 50:
            strengths.append("Good time management - spoke for nearly the full minute")
        if latest_attempt.hesitation_count <= 2:
            strengths.append("Minimal hesitation - spoke with confidence")
        if latest_attempt.word_count >= 140:
            strengths.append("Good speaking pace and fluency")
        if latest_attempt.deviation_count == 0:
            strengths.append("Stayed on topic throughout")
        
        # Identify areas for improvement
        improvements = []
        if latest_attempt.hesitation_count > 5:
            improvements.append("Reduce filler words - practice speaking more deliberately")
        if latest_attempt.repetition_count > 2:
            improvements.append("Expand vocabulary to avoid repetition")
        if latest_attempt.duration < 40:
            improvements.append("Work on developing ideas more fully")
        if latest_attempt.deviation_count > 0:
            improvements.append("Stay focused on the given topic")
        
        # Generate suggestions
        suggestions = []
        if jam.difficulty_level < 3:
            suggestions.append("Try a higher difficulty level for more challenging topics")
        if len(jam.attempts) < 3:
            suggestions.append("Practice more attempts to build consistency")
        suggestions.append("Focus on structure: introduction, main points, conclusion")
        
        # Suggest next topic
        next_topic = self.generate_adaptive_topic(session_id)
        
        feedback = JAMFeedback(
            overall_score=overall_score,
            strengths=strengths,
            areas_for_improvement=improvements,
            specific_mistakes=latest_attempt.mistakes,
            suggestions=suggestions,
            next_topic_suggestion=next_topic,
            timestamp=datetime.utcnow()
        )
        
        return feedback
    
    def get_session_state(self, session_id: str) -> Optional[JAMState]:
        """Get the current state of a JAM session"""
        return self.active_sessions.get(session_id)
    
    def get_session_summary(self, session_id: str) -> Optional[Dict]:
        """Get a summary of the JAM session"""
        if session_id not in self.active_sessions:
            return None
        
        jam = self.active_sessions[session_id]
        
        return {
            "participant_name": jam.participant_name,
            "current_topic": jam.current_topic,
            "phase": jam.phase,
            "total_attempts": jam.total_attempts,
            "difficulty_level": jam.difficulty_level,
            "coaching_mode": jam.coaching_mode,
            "average_score": sum(attempt.score for attempt in jam.attempts) / len(jam.attempts) if jam.attempts else 0,
            "coach_messages_count": len(jam.coach_messages)
        }
    
    def end_session(self, session_id: str):
        """End and cleanup a JAM session"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]


# Global service instance
jam_service = JAMModeService()
