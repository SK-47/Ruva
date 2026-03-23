"""
Voice personality configurations for ElevenLabs Voice Agents.
Defines voice characteristics, tone, pace, and emotion for each coaching mode.
"""

from typing import Dict, Any
from app.services.ai_personalities import AI_PERSONALITIES

# Voice characteristics configuration for each personality type
VOICE_CHARACTERISTICS: Dict[str, Dict[str, Any]] = {
    "energetic_coach": {
        "stability": 0.5,  # Lower = more variable/expressive
        "similarity_boost": 0.75,  # Higher = more similar to original voice
        "style": 0.6,  # Style exaggeration
        "use_speaker_boost": True,
        "tone": "enthusiastic",
        "pace": "moderate-fast",
        "emotion": "encouraging",
        "pitch_range": "medium-high",
        "energy_level": "high",
        "coaching_style": "motivational"
    },
    
    "authoritative_judge": {
        "stability": 0.7,  # More stable/consistent
        "similarity_boost": 0.8,
        "style": 0.4,
        "use_speaker_boost": True,
        "tone": "formal",
        "pace": "measured",
        "emotion": "neutral-serious",
        "pitch_range": "medium-low",
        "energy_level": "controlled",
        "coaching_style": "analytical"
    },
    
    "warm_facilitator": {
        "stability": 0.6,
        "similarity_boost": 0.75,
        "style": 0.5,
        "use_speaker_boost": True,
        "tone": "friendly",
        "pace": "conversational",
        "emotion": "warm",
        "pitch_range": "medium",
        "energy_level": "moderate",
        "coaching_style": "collaborative"
    },
    
    "professional_coach": {
        "stability": 0.65,
        "similarity_boost": 0.8,
        "style": 0.45,
        "use_speaker_boost": True,
        "tone": "professional",
        "pace": "clear-deliberate",
        "emotion": "constructive",
        "pitch_range": "medium",
        "energy_level": "moderate",
        "coaching_style": "instructional"
    },
    
    "professional_interviewer": {
        "stability": 0.7,
        "similarity_boost": 0.8,
        "style": 0.4,
        "use_speaker_boost": True,
        "tone": "professional",
        "pace": "business-like",
        "emotion": "evaluative",
        "pitch_range": "medium",
        "energy_level": "moderate",
        "coaching_style": "questioning"
    },
    
    "business_professional": {
        "stability": 0.7,
        "similarity_boost": 0.8,
        "style": 0.4,
        "use_speaker_boost": True,
        "tone": "professional",
        "pace": "business-appropriate",
        "emotion": "confident",
        "pitch_range": "medium",
        "energy_level": "moderate-high",
        "coaching_style": "scenario-based"
    },
    
    "calm_companion": {
        "stability": 0.8,  # Very stable/soothing
        "similarity_boost": 0.75,
        "style": 0.3,
        "use_speaker_boost": True,
        "tone": "gentle",
        "pace": "slow-calming",
        "emotion": "empathetic",
        "pitch_range": "medium-low",
        "energy_level": "low-moderate",
        "coaching_style": "supportive"
    },
    
    "friendly_coach": {
        "stability": 0.55,
        "similarity_boost": 0.75,
        "style": 0.55,
        "use_speaker_boost": True,
        "tone": "casual-friendly",
        "pace": "relaxed",
        "emotion": "encouraging",
        "pitch_range": "medium",
        "energy_level": "moderate",
        "coaching_style": "conversational"
    },
    
    "neutral_coach": {
        "stability": 0.6,
        "similarity_boost": 0.75,
        "style": 0.5,
        "use_speaker_boost": True,
        "tone": "neutral",
        "pace": "moderate",
        "emotion": "helpful",
        "pitch_range": "medium",
        "energy_level": "moderate",
        "coaching_style": "balanced"
    }
}


def get_voice_characteristics(personality_type: str) -> Dict[str, Any]:
    """Get voice characteristics for a personality type"""
    return VOICE_CHARACTERISTICS.get(
        personality_type,
        VOICE_CHARACTERISTICS["neutral_coach"]
    )


def get_voice_settings_for_mode(mode: str) -> Dict[str, Any]:
    """Get complete voice settings for a coaching mode"""
    # Get the AI personality for this mode
    from app.services.ai_personalities import get_voice_personality
    
    personality_type = get_voice_personality(mode)
    characteristics = get_voice_characteristics(personality_type)
    
    # Get the full AI personality config
    ai_personality = AI_PERSONALITIES.get(
        mode.lower().replace(" ", "-").replace("_", "-"),
        AI_PERSONALITIES["general"]
    )
    
    return {
        "personality_type": personality_type,
        "mode": mode,
        "voice_characteristics": characteristics,
        "system_prompt": ai_personality["system_prompt"],
        "description": ai_personality["description"],
        "coaching_behaviors": get_coaching_behaviors(mode)
    }


def get_coaching_behaviors(mode: str) -> Dict[str, Any]:
    """Get mode-specific coaching behaviors"""
    behaviors = {
        "jam": {
            "interrupt_on_mistakes": True,
            "provide_immediate_feedback": True,
            "track_hesitations": True,
            "track_repetitions": True,
            "track_deviations": True,
            "time_limit": 60,  # seconds
            "encouragement_frequency": "high"
        },
        
        "debate": {
            "interrupt_on_mistakes": False,
            "provide_immediate_feedback": False,
            "track_arguments": True,
            "track_rebuttals": True,
            "provide_final_judgment": True,
            "rounds": 6,
            "encouragement_frequency": "low"
        },
        
        "group-discussion": {
            "interrupt_on_mistakes": False,
            "provide_immediate_feedback": False,
            "facilitate_turn_taking": True,
            "ask_questions": True,
            "summarize_points": True,
            "encourage_participation": True,
            "encouragement_frequency": "moderate"
        },
        
        "reading": {
            "interrupt_on_mistakes": False,
            "provide_immediate_feedback": True,
            "track_pronunciation": True,
            "track_pace": True,
            "track_articulation": True,
            "provide_passage": True,
            "encouragement_frequency": "moderate"
        },
        
        "interview": {
            "interrupt_on_mistakes": False,
            "provide_immediate_feedback": False,
            "ask_questions": True,
            "evaluate_responses": True,
            "provide_final_evaluation": True,
            "question_count": 7,
            "encouragement_frequency": "low"
        },
        
        "business-talks": {
            "interrupt_on_mistakes": False,
            "provide_immediate_feedback": False,
            "maintain_persona": True,
            "create_scenarios": True,
            "provide_final_feedback": True,
            "turn_count": 10,
            "encouragement_frequency": "moderate"
        },
        
        "therapy": {
            "interrupt_on_mistakes": False,
            "provide_immediate_feedback": False,
            "practice_active_listening": True,
            "ask_open_questions": True,
            "provide_safety_resources": True,
            "no_diagnosis": True,
            "encouragement_frequency": "high"
        },
        
        "socialising": {
            "interrupt_on_mistakes": False,
            "provide_immediate_feedback": False,
            "create_scenarios": True,
            "be_patient": True,
            "provide_encouragement": True,
            "provide_final_feedback": True,
            "encouragement_frequency": "high"
        },
        
        "general": {
            "interrupt_on_mistakes": False,
            "provide_immediate_feedback": True,
            "be_supportive": True,
            "be_constructive": True,
            "encouragement_frequency": "moderate"
        }
    }
    
    mode_key = mode.lower().replace(" ", "-").replace("_", "-")
    return behaviors.get(mode_key, behaviors["general"])


def get_all_voice_personalities() -> list:
    """Get all available voice personalities with their configurations"""
    return [
        {
            "personality_type": personality_type,
            "characteristics": characteristics,
            "modes": [
                mode for mode, config in AI_PERSONALITIES.items()
                if config.get("voice_personality") == personality_type
            ]
        }
        for personality_type, characteristics in VOICE_CHARACTERISTICS.items()
    ]
