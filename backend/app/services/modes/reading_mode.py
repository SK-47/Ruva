"""
Reading Mode Service - AI-powered reading comprehension and fluency analysis
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
from pydantic import BaseModel
import uuid

logger = logging.getLogger(__name__)

class ReadingPhase(str, Enum):
    SETUP = "setup"
    PASSAGE_GIVEN = "passage_given"
    READING = "reading"
    ANALYSIS = "analysis"
    COMPLETED = "completed"

class ReadingDifficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"

class ReadingGenre(str, Enum):
    FICTION = "fiction"
    NON_FICTION = "non_fiction"
    NEWS = "news"
    ACADEMIC = "academic"
    POETRY = "poetry"
    TECHNICAL = "technical"

class ReadingAttempt(BaseModel):
    attempt_number: int
    passage: str
    genre: ReadingGenre
    difficulty: ReadingDifficulty
    started_at: datetime
    completed_at: Optional[datetime] = None
    reading_duration: Optional[float] = None  # in seconds
    transcript: Optional[str] = None
    word_count: int = 0
    reading_speed_wpm: Optional[float] = None
    accuracy_score: Optional[float] = None
    fluency_score: Optional[float] = None
    comprehension_score: Optional[float] = None
    overall_score: Optional[float] = None

class ReadingFeedback(BaseModel):
    overall_assessment: str
    strengths: List[str]
    areas_for_improvement: List[str]
    pronunciation_feedback: List[str]
    fluency_feedback: List[str]
    comprehension_feedback: List[str]
    suggestions: List[str]
    next_difficulty_recommendation: ReadingDifficulty

class ReadingState(BaseModel):
    session_id: str
    room_id: str
    participant_id: str
    participant_name: str
    phase: ReadingPhase
    difficulty_level: ReadingDifficulty
    preferred_genres: List[ReadingGenre] = []
    current_passage: Optional[str] = None
    current_genre: Optional[ReadingGenre] = None
    current_attempt: Optional[ReadingAttempt] = None
    attempts: List[ReadingAttempt] = []
    total_attempts: int = 0
    session_feedback: Optional[ReadingFeedback] = None
    created_at: datetime
    updated_at: datetime

class ReadingService:
    """Service for managing reading comprehension sessions"""
    
    def __init__(self):
        self.active_sessions: Dict[str, ReadingState] = {}
    
    def create_session(
        self,
        room_id: str,
        session_id: str,
        participant_id: str,
        participant_name: str,
        difficulty_level: ReadingDifficulty = ReadingDifficulty.BEGINNER
    ) -> ReadingState:
        """Create a new reading session"""
        
        reading_state = ReadingState(
            session_id=session_id,
            room_id=room_id,
            participant_id=participant_id,
            participant_name=participant_name,
            phase=ReadingPhase.SETUP,
            difficulty_level=difficulty_level,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.active_sessions[session_id] = reading_state
        return reading_state
    
    def set_passage(
        self,
        session_id: str,
        passage: str,
        genre: ReadingGenre = ReadingGenre.NON_FICTION
    ) -> ReadingState:
        """Set a reading passage for the session"""
        if session_id not in self.active_sessions:
            raise ValueError(f"Reading session {session_id} not found")
        
        reading = self.active_sessions[session_id]
        reading.current_passage = passage
        reading.current_genre = genre
        reading.phase = ReadingPhase.PASSAGE_GIVEN
        reading.updated_at = datetime.utcnow()
        
        return reading
    
    def start_reading_attempt(self, session_id: str) -> ReadingState:
        """Start a new reading attempt"""
        if session_id not in self.active_sessions:
            raise ValueError(f"Reading session {session_id} not found")
        
        reading = self.active_sessions[session_id]
        
        if not reading.current_passage:
            raise ValueError("No passage set for this session")
        
        # Count words in passage
        word_count = len(reading.current_passage.split())
        
        attempt = ReadingAttempt(
            attempt_number=reading.total_attempts + 1,
            passage=reading.current_passage,
            genre=reading.current_genre,
            difficulty=reading.difficulty_level,
            started_at=datetime.utcnow(),
            word_count=word_count
        )
        
        reading.current_attempt = attempt
        reading.phase = ReadingPhase.READING
        reading.updated_at = datetime.utcnow()
        
        return reading
    
    def complete_reading_attempt(
        self,
        session_id: str,
        transcript: str,
        reading_duration: float
    ) -> ReadingState:
        """Complete the current reading attempt"""
        if session_id not in self.active_sessions:
            raise ValueError(f"Reading session {session_id} not found")
        
        reading = self.active_sessions[session_id]
        
        if not reading.current_attempt:
            raise ValueError("No active reading attempt")
        
        # Complete the attempt
        reading.current_attempt.completed_at = datetime.utcnow()
        reading.current_attempt.transcript = transcript
        reading.current_attempt.reading_duration = reading_duration
        
        # Calculate reading speed (words per minute)
        if reading_duration > 0:
            reading.current_attempt.reading_speed_wpm = (
                reading.current_attempt.word_count / (reading_duration / 60)
            )
        
        # Add to attempts history
        reading.attempts.append(reading.current_attempt)
        reading.total_attempts += 1
        reading.phase = ReadingPhase.ANALYSIS
        reading.updated_at = datetime.utcnow()
        
        return reading
    
    def generate_adaptive_passage(self, session_id: str) -> str:
        """Generate a passage adapted to the user's skill level"""
        if session_id not in self.active_sessions:
            raise ValueError(f"Reading session {session_id} not found")
        
        reading = self.active_sessions[session_id]
        
        # Passages organized by difficulty level
        passages_by_level = {
            ReadingDifficulty.BEGINNER: [
                "The sun rises in the east and sets in the west. Every morning, people wake up to see the bright yellow sun in the sky. The sun gives us light and warmth. Without the sun, plants cannot grow and animals cannot live. The sun is very important for life on Earth.",
                "Cats are popular pets around the world. They have soft fur and sharp claws. Cats like to sleep during the day and play at night. They can see very well in the dark. Many people love cats because they are independent and clean animals.",
                "Reading books is a wonderful hobby. Books can take us to different places and times. When we read, we learn new words and ideas. Some books tell exciting stories, while others teach us about science or history. Reading helps our minds grow stronger.",
                "Water is essential for all living things. We need water to drink, cook, and clean. Plants need water to grow, and animals need water to survive. Most of our planet is covered with water in oceans, rivers, and lakes.",
                "Friendship is one of life's greatest gifts. Good friends support each other through happy and difficult times. They share secrets, laugh together, and help solve problems. True friends are honest and kind to each other."
            ],
            ReadingDifficulty.INTERMEDIATE: [
                "Climate change represents one of the most significant challenges facing humanity today. Rising global temperatures are causing ice caps to melt, sea levels to rise, and weather patterns to become increasingly unpredictable. Scientists worldwide are working to understand these changes and develop solutions to reduce greenhouse gas emissions.",
                "The invention of the internet has revolutionized how we communicate, work, and access information. What began as a military research project has evolved into a global network connecting billions of people. Social media, online shopping, and remote work have all become integral parts of modern life.",
                "Artificial intelligence is rapidly advancing across various industries. Machine learning algorithms can now recognize images, translate languages, and even compose music. While AI offers tremendous benefits for healthcare, education, and business efficiency, it also raises important questions about privacy and employment.",
                "Sustainable agriculture practices are becoming increasingly important as the world's population grows. Farmers are adopting techniques like crop rotation, organic fertilizers, and precision farming to increase yields while protecting the environment. These methods help preserve soil health and reduce water consumption.",
                "The human brain contains approximately 86 billion neurons that communicate through electrical and chemical signals. This complex network enables us to think, feel, remember, and create. Neuroscientists continue to discover new insights about how the brain processes information and forms memories."
            ],
            ReadingDifficulty.ADVANCED: [
                "The philosophical implications of quantum mechanics have perplexed scientists and philosophers since the early twentieth century. The Copenhagen interpretation suggests that particles exist in superposition until observed, fundamentally challenging our understanding of reality and causation. This quantum indeterminacy has profound consequences for discussions of free will and determinism.",
                "Postcolonial literary theory examines how literature both reflects and shapes cultural identity in the aftermath of colonial rule. Authors like Chinua Achebe and Salman Rushdie have employed narrative techniques that subvert Western literary conventions while reclaiming indigenous storytelling traditions. This literary movement challenges hegemonic discourse and celebrates cultural hybridity.",
                "The emergence of CRISPR-Cas9 gene editing technology has revolutionized molecular biology and raised unprecedented ethical questions. While this tool offers potential cures for genetic diseases and agricultural improvements, it also presents risks of unintended consequences and concerns about genetic enhancement. The scientific community continues to debate appropriate regulatory frameworks.",
                "Behavioral economics integrates psychological insights into economic theory, challenging the assumption of rational decision-making. Concepts like loss aversion, anchoring bias, and hyperbolic discounting explain why people often make choices that appear economically irrational. These findings have significant implications for public policy and market design.",
                "The anthropocene epoch represents a new geological age defined by human impact on Earth's systems. From climate change to biodiversity loss, human activities have fundamentally altered planetary processes. This concept challenges traditional boundaries between natural and social sciences, requiring interdisciplinary approaches to environmental challenges."
            ]
        }
        
        import random
        level_passages = passages_by_level.get(reading.difficulty_level, passages_by_level[ReadingDifficulty.BEGINNER])
        return random.choice(level_passages)
    
    def analyze_reading_performance(self, session_id: str) -> Optional[ReadingFeedback]:
        """Analyze reading performance and provide feedback"""
        if session_id not in self.active_sessions:
            return None
        
        reading = self.active_sessions[session_id]
        
        if not reading.current_attempt or not reading.current_attempt.transcript:
            return None
        
        attempt = reading.current_attempt
        
        # Calculate basic metrics
        original_words = attempt.passage.lower().split()
        transcript_words = attempt.transcript.lower().split()
        
        # Simple accuracy calculation (word matching)
        correct_words = 0
        for i, word in enumerate(transcript_words):
            if i < len(original_words) and word == original_words[i]:
                correct_words += 1
        
        accuracy = (correct_words / len(original_words)) * 100 if original_words else 0
        attempt.accuracy_score = accuracy
        
        # Reading speed assessment
        wpm = attempt.reading_speed_wpm or 0
        
        # Fluency scoring based on reading speed and accuracy
        if wpm >= 150 and accuracy >= 95:
            fluency_score = 95
        elif wpm >= 120 and accuracy >= 90:
            fluency_score = 85
        elif wpm >= 100 and accuracy >= 85:
            fluency_score = 75
        elif wpm >= 80 and accuracy >= 80:
            fluency_score = 65
        else:
            fluency_score = max(50, accuracy * 0.6)
        
        attempt.fluency_score = fluency_score
        
        # Overall score (weighted average)
        overall_score = (accuracy * 0.4 + fluency_score * 0.6)
        attempt.overall_score = overall_score
        
        # Generate feedback
        strengths = []
        improvements = []
        suggestions = []
        
        if accuracy >= 90:
            strengths.append("Excellent word accuracy")
        elif accuracy >= 80:
            strengths.append("Good word recognition")
        else:
            improvements.append("Focus on careful pronunciation of each word")
        
        if wpm >= 150:
            strengths.append("Excellent reading speed")
        elif wpm >= 120:
            strengths.append("Good reading pace")
        elif wpm < 80:
            improvements.append("Practice reading more fluently")
        
        if fluency_score >= 85:
            strengths.append("Natural reading flow")
        else:
            improvements.append("Work on smooth, natural reading rhythm")
        
        # Suggestions based on performance
        if overall_score >= 90:
            suggestions.append("Try more challenging passages")
            next_difficulty = ReadingDifficulty.ADVANCED if reading.difficulty_level != ReadingDifficulty.ADVANCED else reading.difficulty_level
        elif overall_score >= 75:
            suggestions.append("Continue practicing at this level")
            next_difficulty = reading.difficulty_level
        else:
            suggestions.append("Practice with shorter passages first")
            next_difficulty = ReadingDifficulty.BEGINNER if reading.difficulty_level != ReadingDifficulty.BEGINNER else reading.difficulty_level
        
        suggestions.extend([
            "Read aloud daily to improve fluency",
            "Focus on clear pronunciation",
            "Practice with different text types"
        ])
        
        feedback = ReadingFeedback(
            overall_assessment=f"Your reading performance scored {overall_score:.1f}%. " + 
                             ("Excellent work!" if overall_score >= 85 else 
                              "Good progress!" if overall_score >= 70 else 
                              "Keep practicing!"),
            strengths=strengths,
            areas_for_improvement=improvements,
            pronunciation_feedback=[
                "Focus on clear consonant sounds",
                "Practice vowel pronunciation",
                "Work on word stress patterns"
            ],
            fluency_feedback=[
                "Maintain steady reading pace",
                "Use natural pauses between sentences",
                "Practice reading with expression"
            ],
            comprehension_feedback=[
                "Read the passage once silently first",
                "Focus on understanding before reading aloud",
                "Practice summarizing what you read"
            ],
            suggestions=suggestions,
            next_difficulty_recommendation=next_difficulty
        )
        
        reading.session_feedback = feedback
        reading.phase = ReadingPhase.COMPLETED
        reading.updated_at = datetime.utcnow()
        
        return feedback
    
    def get_session_state(self, session_id: str) -> Optional[ReadingState]:
        """Get the current state of a reading session"""
        return self.active_sessions.get(session_id)
    
    def get_session_summary(self, session_id: str) -> Optional[Dict]:
        """Get a summary of the reading session"""
        if session_id not in self.active_sessions:
            return None
        
        reading = self.active_sessions[session_id]
        
        return {
            "session_id": session_id,
            "participant_name": reading.participant_name,
            "difficulty_level": reading.difficulty_level,
            "total_attempts": reading.total_attempts,
            "current_phase": reading.phase,
            "current_passage": reading.current_passage,
            "session_feedback": reading.session_feedback.model_dump() if reading.session_feedback else None,
            "attempts": [attempt.model_dump() for attempt in reading.attempts]
        }

# Global service instance
reading_service = ReadingService()