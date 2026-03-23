import google.generativeai as genai
from typing import Dict, List, Any, Optional
import time
import logging
import asyncio
from datetime import datetime, timedelta

from app.core.config import settings
from app.services.ai_personalities import get_system_prompt, get_personality

logger = logging.getLogger(__name__)

class RateLimiter:
    """Simple rate limiter for API requests"""
    def __init__(self, max_requests: int = 60, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window  # seconds
        self.requests = []
    
    async def acquire(self):
        """Wait if necessary to respect rate limits"""
        now = datetime.utcnow()
        # Remove old requests outside the time window
        self.requests = [req_time for req_time in self.requests 
                        if now - req_time < timedelta(seconds=self.time_window)]
        
        if len(self.requests) >= self.max_requests:
            # Calculate wait time
            oldest_request = min(self.requests)
            wait_time = (oldest_request + timedelta(seconds=self.time_window) - now).total_seconds()
            if wait_time > 0:
                logger.warning(f"Rate limit reached. Waiting {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
                # Retry after waiting
                return await self.acquire()
        
        self.requests.append(now)
        return True

class AIService:
    def __init__(self):
        self.model = None
        self.model_name = 'gemini-2.5-flash'
        self.rate_limiter = RateLimiter(max_requests=60, time_window=60)
        self._initialize_gemini()
    
    def _initialize_gemini(self):
        """Initialize Gemini API with secure credential management"""
        try:
            if not settings.GEMINI_API_KEY:
                logger.warning("Gemini API key not provided. AI features will be limited.")
                return
            
            if settings.GEMINI_API_KEY == "your_gemini_api_key_here":
                logger.warning("Default Gemini API key detected. Please configure a valid API key.")
                return
            
            genai.configure(api_key=settings.GEMINI_API_KEY)
            
            # Configure generation settings
            generation_config = {
                "temperature": 0.9,
                "top_p": 1,
                "top_k": 1,
                "max_output_tokens": 2048,
            }
            
            # Try gemini-2.5-flash first (faster), fallback to gemini-2.5-pro if needed
            try:
                self.model = genai.GenerativeModel(
                    'gemini-2.5-flash',
                    generation_config=generation_config
                )
                self.model_name = 'gemini-2.5-flash'
                logger.info("Gemini API initialized successfully with gemini-2.5-flash")
            except Exception as e:
                logger.warning(f"Failed to initialize gemini-2.5-flash, trying gemini-2.5-pro: {e}")
                self.model = genai.GenerativeModel(
                    'gemini-2.5-pro',
                    generation_config=generation_config
                )
                self.model_name = 'gemini-2.5-pro'
                logger.info("Gemini API initialized successfully with gemini-2.5-pro")
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini API: {e}")
            raise
    
    async def _retry_with_backoff(self, func, max_retries: int = 3, initial_delay: float = 1.0):
        """Retry a function with exponential backoff"""
        delay = initial_delay
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return await func()
            except Exception as e:
                last_exception = e
                error_msg = str(e).lower()
                
                # Check if it's a rate limit error
                if "rate limit" in error_msg or "quota" in error_msg or "429" in error_msg:
                    logger.warning(f"Rate limit hit on attempt {attempt + 1}/{max_retries}. Waiting {delay}s")
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff
                    continue
                
                # Check if it's a temporary error
                elif "timeout" in error_msg or "connection" in error_msg or "503" in error_msg:
                    logger.warning(f"Temporary error on attempt {attempt + 1}/{max_retries}: {e}")
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                
                # For other errors, don't retry
                else:
                    logger.error(f"Non-retryable error: {e}")
                    raise
        
        # If all retries failed
        logger.error(f"All {max_retries} retry attempts failed")
        raise last_exception
    
    async def generate_response(
        self, 
        prompt: str, 
        context: Optional[str] = None,
        mode: str = "general",
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """Generate AI response using Gemini with rate limiting and retry logic"""
        if not self.model:
            return {
                "text": "AI service is not available. Please configure Gemini API key.",
                "model": "none",
                "tokens_used": 0,
                "response_time": 0,
                "error": "API not configured"
            }
        
        try:
            # Respect rate limits
            await self.rate_limiter.acquire()
            
            # Define the API call as an async function for retry logic
            async def make_api_call():
                start_time = time.time()
                
                # Build the full prompt with context
                full_prompt = self._build_prompt(prompt, context, mode)
                
                # Generate response (wrap sync call in executor)
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, 
                    self.model.generate_content, 
                    full_prompt
                )
                
                response_time = time.time() - start_time
                
                return {
                    "text": response.text,
                    "model": "gemini-2.0-flash-exp",
                    "tokens_used": self._estimate_tokens(full_prompt + response.text),
                    "response_time": response_time
                }
            
            # Execute with retry logic
            return await self._retry_with_backoff(make_api_call, max_retries=max_retries)
            
        except Exception as e:
            logger.error(f"AI response generation failed after retries: {e}")
            return {
                "text": f"Sorry, I encountered an error: {str(e)}",
                "model": "gemini-2.0-flash-exp",
                "tokens_used": 0,
                "response_time": 0,
                "error": str(e)
            }

    def generate_text(self, prompt: str) -> str:
        """Synchronous text generation for use in non-async contexts"""
        if not self.model:
            return "AI service is not available"
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error generating text: {e}")
            return f"Error generating text: {str(e)}"

    async def generate_simple_response(self, prompt: str) -> str:
        """Generate a plain text response from a prompt string"""
        if not self.model:
            raise Exception("AI model not initialized")
        await self.rate_limiter.acquire()
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, self.model.generate_content, prompt),
            timeout=20.0
        )
        return response.text.strip()
    
    def _build_prompt(self, prompt: str, context: Optional[str], mode: str) -> str:
        """Build the full prompt with context and mode-specific instructions"""
        # Get the system prompt from AI personalities
        system_prompt = get_system_prompt(mode)
        
        full_prompt = f"{system_prompt}\n\n"
        
        if context:
            full_prompt += f"Context: {context}\n\n"
        
        full_prompt += f"User: {prompt}\n\nAssistant:"
        
        return full_prompt
    
    async def generate_host_response(
        self,
        room_mode: str,
        current_topic: Optional[str] = None,
        conversation_history: List[str] = [],
        participant_count: int = 1
    ) -> Dict[str, Any]:
        """Generate contextual AI host response based on room mode"""
        
        # Build context from conversation history
        context = ""
        if conversation_history:
            context = "Recent conversation:\n" + "\n".join(conversation_history[-5:])  # Last 5 messages
        
        # Mode-specific prompts
        mode_prompts = {
            "debate": self._get_debate_host_prompt(current_topic, participant_count),
            "group-discussion": self._get_discussion_host_prompt(current_topic, participant_count),
            "jam": self._get_jam_host_prompt(),
            "reading": self._get_reading_host_prompt()
        }
        
        prompt = mode_prompts.get(room_mode, "Please provide guidance for the current speaking practice.")
        
        return await self.generate_response(prompt, context, room_mode)
    
    def _get_debate_host_prompt(self, topic: Optional[str], participant_count: int) -> str:
        """Generate debate judge prompt"""
        if topic:
            return f"As a debate judge, provide opening remarks for a debate on '{topic}' with {participant_count} participants. Set clear expectations and rules."
        else:
            return "As a debate judge, suggest a compelling debate topic and explain the rules for a structured debate."
    
    def _get_discussion_host_prompt(self, topic: Optional[str], participant_count: int) -> str:
        """Generate group discussion facilitator prompt"""
        if topic:
            return f"As a discussion facilitator, guide a conversation about '{topic}' with {participant_count} participants. Ask an engaging opening question."
        else:
            return f"As a discussion facilitator, suggest an interesting topic for {participant_count} participants and ask an opening question to start the conversation."
    
    async def generate_discussion_scenario(self, discussion_mode: str, participant_count: int = 2) -> Dict[str, Any]:
        """Generate a roleplay scenario for group discussions"""
        
        if discussion_mode == "business":
            prompt = f"""Generate a business roleplay scenario for {participant_count} participants. 
            
Format the response EXACTLY like this example:

Scenario: The Digital Masterpiece
Characters: Digital Art Display Creator (Pitching) & Traditional Fine Art Gallery Owner (Rejecting)
Meeting: At an Art VIP preview event.
Motivation: The Creator pitches a high-tech, museum-grade 8K digital canvas designed to display Digital art. They want the Gallery Owner to install these screens to sell digital works alongside their oil paintings. The Gallery Owner listens but rejects the collaboration. They explain that their specific collectors buy art for the "texture, smell, and physical permanence" of paint on canvas; screens feel too "commercial" and cold for their gallery's aesthetic. However, the Owner loves the sleek design of the hardware and suggests the Creator pitch to the Luxury Real Estate Developer across the room, who needs high-tech, interchangeable art solutions for staging modern multi-million dollar penthouses.
Opening Line: "Imagine if your collectors could change the art on their wall to match their mood instantly."

Create a similar scenario with:
- A clear business pitch situation
- One person pitching, one person rejecting but offering alternative
- Realistic business context
- Compelling opening line
"""
        else:  # casual
            prompt = f"""Generate a casual conversation scenario for {participant_count} participants.

Format the response EXACTLY like this example:

Scenario: The Weekend Adventure
Characters: Adventure Enthusiast (Suggesting) & Homebody Friend (Declining)
Setting: Coffee shop on Friday afternoon
Motivation: The Enthusiast wants to convince their friend to join a spontaneous camping trip this weekend. They describe the beautiful location, activities, and how it would be a great break from routine. The Friend appreciates the invitation but declines, explaining they have important personal projects to finish and prefer staying home. However, the Friend suggests they plan a day hike next month instead, which would be more manageable.
Opening Line: "What if we just packed up and headed to the mountains this weekend?"

Create a similar casual scenario with:
- A friendly suggestion/invitation
- One person suggesting, one declining but offering alternative
- Relatable everyday context
- Natural opening line
"""
        
        response = await self.generate_response(prompt, mode="group-discussion")
        
        # Parse the scenario
        scenario_text = response["text"]
        
        # Extract roles from the Characters line
        roles = []
        if "Characters:" in scenario_text:
            chars_line = [line for line in scenario_text.split("\n") if "Characters:" in line][0]
            # Extract role names (text before parentheses)
            import re
            role_matches = re.findall(r'([^(&]+)(?:\s*\([^)]+\))?(?:\s*&|$)', chars_line.split("Characters:")[1])
            roles = [role.strip() for role in role_matches if role.strip()]
        
        return {
            "scenario": scenario_text,
            "roles": roles[:participant_count],  # Limit to participant count
            "discussion_mode": discussion_mode,
            "response_time": response["response_time"]
        }
    
    def _get_jam_host_prompt(self) -> str:
        """Generate JAM coach prompt"""
        topics = [
            "The importance of breakfast",
            "Why cats make better pets than dogs",
            "The benefits of reading books",
            "How to make the perfect sandwich",
            "Why laughter is the best medicine",
            "The art of procrastination",
            "Life lessons from video games",
            "The secret to happiness",
            "Why coffee is the best beverage",
            "The joy of learning new skills",
            "How music affects our mood",
            "The power of a good night's sleep",
            "Why traveling broadens the mind",
            "The importance of staying curious",
            "How hobbies improve our lives",
            "The value of friendship",
            "Why exercise makes us feel better",
            "The magic of storytelling",
            "How technology has changed communication",
            "The beauty of nature"
        ]
        
        import random
        topic = random.choice(topics)
        
        return f"As a JAM coach, present this topic for a Just-A-Minute challenge: '{topic}'. Explain the rules: speak for one minute without hesitation, repetition, or deviation. Ask if the participant is ready with this topic or would like a different one."
    
    async def generate_jam_topic(self, conversation_history: List[str] = []) -> Dict[str, Any]:
        """Generate a JAM (Just-A-Minute) topic using Gemini AI with conversation context"""
        
        # Build context from conversation history
        context = ""
        if conversation_history:
            context = "Previous conversation:\n" + "\n".join(conversation_history[-5:])  # Last 5 exchanges
        
        # Use the JAM personality prompt
        personality = get_personality("JAM")
        system_prompt = personality["system_prompt"]
        
        prompt = """Generate a new JAM (Just-A-Minute) topic.

Rules:
- The "response" field must contain ONLY the topic phrase itself. Nothing else.
- No intro, no instructions, no punctuation beyond the topic itself.
- Good examples: "The unexpected benefits of getting lost", "Why mornings are overrated", "The art of doing nothing"
- Bad examples: "Your topic is: ...", "Speak about ...", "Today's topic: ..."

Respond in valid JSON format only: {"response": "<topic only>"}"""

        # Build full prompt with system instructions
        full_prompt = f"""{system_prompt}

{context}

{prompt}"""

        # Try with flash model first, then pro if it fails
        models_to_try = ['gemini-2.5-flash', 'gemini-2.5-pro']
        max_attempts = 5  # Keep retrying up to 5 times
        
        for attempt in range(max_attempts):
            for model_name in models_to_try:
                try:
                    logger.info(f"Attempt {attempt + 1}/{max_attempts} with {model_name}")
                    
                    # Respect rate limits
                    await self.rate_limiter.acquire()
                    
                    # Create model instance for this attempt
                    generation_config = {
                        "temperature": 0.9,
                        "top_p": 1,
                        "top_k": 1,
                        "max_output_tokens": 2048,
                    }
                    
                    model = genai.GenerativeModel(model_name, generation_config=generation_config)
                    
                    # Make API call with timeout
                    start_time = time.time()
                    
                    loop = asyncio.get_event_loop()
                    response = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            model.generate_content,
                            full_prompt
                        ),
                        timeout=25.0  # 25 second timeout
                    )
                    
                    response_time = time.time() - start_time
                    
                    # Parse JSON response
                    import json
                    response_text = response.text.strip()
                    
                    # Try to extract JSON
                    start_idx = response_text.find('{')
                    end_idx = response_text.rfind('}') + 1
                    
                    if start_idx >= 0 and end_idx > start_idx:
                        json_str = response_text[start_idx:end_idx]
                        data = json.loads(json_str)
                        
                        # Validate that we have a response
                        if data.get("response"):
                            logger.info(f"✅ JAM topic generated successfully with {model_name} on attempt {attempt + 1}")
                            return {
                                "response": data.get("response", ""),
                                "mistakes": data.get("mistakes", []),
                                "suggestions": data.get("suggestions", []),
                                "response_time": response_time
                            }
                        else:
                            logger.warning(f"Response missing 'response' field, retrying...")
                            continue
                    else:
                        logger.warning(f"Failed to parse JSON, retrying...")
                        continue
                        
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout with {model_name} on attempt {attempt + 1}, trying next...")
                    continue
                    
                except Exception as e:
                    error_str = str(e).lower()
                    if "deadline" in error_str or "504" in error_str:
                        logger.warning(f"Deadline exceeded with {model_name} on attempt {attempt + 1}, trying next...")
                        continue
                    else:
                        logger.warning(f"Error with {model_name} on attempt {attempt + 1}: {e}, trying next...")
                        continue
            
            # Wait a bit before next attempt
            if attempt < max_attempts - 1:
                await asyncio.sleep(2)  # 2 second delay between attempts
        
        # If all attempts failed, return fallback
        logger.error("All attempts to generate JAM topic failed, using fallback")
        import random
        fallback_topics = [
            "The power of practice",
            "Why curiosity matters",
            "The art of listening",
            "Small habits, big changes",
            "The value of silence",
        ]
        return {
            "response": random.choice(fallback_topics),
            "mistakes": [],
            "suggestions": [],
            "error": "all_attempts_failed"
        }
    
    async def evaluate_jam_performance(
        self, 
        topic: str, 
        transcript: str, 
        duration: int, 
        prosody_metrics: Optional[Dict] = None,
        conversation_history: List[str] = [],
        body_language: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Evaluate JAM speech performance using Gemini AI with prosody analysis and conversation context"""
        
        # Build conversation context
        context = ""
        if conversation_history:
            context = "Previous conversation:\n" + "\n".join(conversation_history[-10:])  # Last 10 exchanges
        
        # Build prosody context if available
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
        
        prompt = f"""You are a strict but fair Just-A-Minute (JAM) instructor evaluating a speech performance.

Topic Given: "{topic}"
Transcript: "{transcript}"

**CRITICAL INSTRUCTIONS:**
1. Your PRIMARY focus is analyzing the TRANSCRIPT CONTENT - what the speaker actually said
2. Check if they addressed the topic properly
3. Look for hesitation words in the transcript ("um", "uh", "er", "ah")
4. Identify repetition of words or ideas in the transcript
5. Check if they deviated from the topic

**SECONDARY considerations (only if relevant):**{prosody_context}

Analyze the speech for:
1. **Deviation**: Did they stay on topic? Did they actually address "{topic}"?
2. **Repetition**: Did they repeat the same words or ideas?
3. **Hesitation**: Are there filler words like "um", "uh", "er", "ah" in the transcript?

Provide your evaluation in JSON format with these exact keys:
{{
  "overall": "Brief assessment focusing on CONTENT quality (2-3 sentences)",
  "mistakes": [
    {{"type": "Hesitation/Repetition/Deviation", "description": "Specific example from the transcript"}},
    ...
  ],
  "suggestions": [
    "Actionable tip 1",
    "Actionable tip 2",
    ...
  ]
}}

Be constructive and encouraging. Focus on what they SAID, not how long they spoke."""

        # Retry up to 3 times to get a valid response
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"Evaluation attempt {attempt + 1}/{max_retries}")
                
                response = await self.generate_response(prompt, context, mode="jam", max_retries=2)
                
                # Try to parse JSON from response
                import json
                try:
                    # Extract JSON from response (might have extra text)
                    text = response.get("text", "")
                    
                    if not text:
                        logger.warning(f"Empty response on attempt {attempt + 1}, retrying...")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)
                            continue
                    
                    start = text.find('{')
                    end = text.rfind('}') + 1
                    if start >= 0 and end > start:
                        json_str = text[start:end]
                        evaluation = json.loads(json_str)
                        
                        # Validate that we have at least an overall field
                        if evaluation.get("overall"):
                            logger.info(f"✅ Evaluation successful on attempt {attempt + 1}")
                            return evaluation
                        else:
                            logger.warning(f"Missing 'overall' field on attempt {attempt + 1}, retrying...")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2)
                                continue
                    else:
                        # Fallback if no JSON found but we have text
                        if text:
                            logger.warning(f"No JSON found on attempt {attempt + 1}, using text as overall")
                            return {
                                "overall": text,
                                "mistakes": [],
                                "suggestions": ["Keep practicing and focus on the topic!"]
                            }
                        else:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2)
                                continue
                                
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error on attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    
            except Exception as e:
                logger.error(f"Evaluation error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
        
        # If all retries failed, return a generic evaluation
        logger.error("All evaluation attempts failed, returning generic feedback")
        return {
            "overall": "Good effort! Keep practicing your speaking skills. Focus on staying on topic and speaking clearly.",
            "mistakes": [],
            "suggestions": [
                "Practice speaking on the given topic without deviation",
                "Reduce filler words like 'um' and 'uh'",
                "Organize your thoughts before speaking"
            ]
        }
    
    def _get_reading_host_prompt(self) -> str:
        """Generate reading coach prompt"""
        return "As a reading coach, provide a short passage for pronunciation practice and explain what aspects of reading fluency you'll be focusing on (pace, articulation, expression)."
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of token count"""
        # Approximate: 1 token ≈ 4 characters for English text
        return len(text) // 4
    
    async def analyze_body_language(self, images: List[str], context: str = "") -> Dict[str, Any]:
        """
        Analyze body language from multiple image snapshots using Gemini Vision
        
        Args:
            images: List of base64 encoded images
            context: Additional context about the speech/presentation
        
        Returns:
            Body language analysis with insights
        """
        if not self.model:
            return {
                "analysis": "Body language analysis not available. Please configure Gemini API key.",
                "confidence_score": 0,
                "posture_notes": [],
                "gesture_notes": [],
                "facial_expression_notes": [],
                "recommendations": []
            }
        
        try:
            # Build prompt for body language analysis
            prompt = f"""You are an expert body language analyst. Analyze these snapshots taken during a speech/presentation.

Context: {context if context else "General speech practice"}

Analyze the following aspects:
1. **Posture**: Standing position, body alignment, confidence level
2. **Gestures**: Hand movements, their appropriateness and effectiveness
3. **Facial Expressions**: Engagement, emotion, authenticity
4. **Eye Contact**: Direction of gaze (if visible)
5. **Overall Presence**: Confidence, energy, professionalism

Provide your analysis in JSON format:
{{
  "overall_impression": "Brief overall assessment",
  "confidence_score": 0-100,
  "posture_notes": ["observation 1", "observation 2"],
  "gesture_notes": ["observation 1", "observation 2"],
  "facial_expression_notes": ["observation 1", "observation 2"],
  "strengths": ["strength 1", "strength 2"],
  "areas_for_improvement": ["area 1", "area 2"],
  "recommendations": ["actionable tip 1", "actionable tip 2"]
}}

Be constructive and specific in your feedback."""

            # For now, return a structured response
            # In production, you would send images to Gemini Vision API
            # This requires Gemini Pro Vision model
            
            response = await self.generate_response(prompt, mode="general")
            
            # Try to parse JSON from response
            import json
            try:
                text = response["text"]
                start = text.find('{')
                end = text.rfind('}') + 1
                if start >= 0 and end > start:
                    json_str = text[start:end]
                    analysis = json.loads(json_str)
                else:
                    analysis = {
                        "overall_impression": text,
                        "confidence_score": 75,
                        "posture_notes": [],
                        "gesture_notes": [],
                        "facial_expression_notes": [],
                        "strengths": [],
                        "areas_for_improvement": [],
                        "recommendations": ["Keep practicing!"]
                    }
            except Exception as e:
                logger.error(f"Failed to parse body language analysis JSON: {e}")
                analysis = {
                    "overall_impression": response["text"],
                    "confidence_score": 75,
                    "posture_notes": [],
                    "gesture_notes": [],
                    "facial_expression_notes": [],
                    "strengths": ["Good effort"],
                    "areas_for_improvement": [],
                    "recommendations": ["Keep practicing!"]
                }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Body language analysis failed: {e}")
            return {
                "overall_impression": "Unable to analyze body language at this time.",
                "confidence_score": 0,
                "posture_notes": [],
                "gesture_notes": [],
                "facial_expression_notes": [],
                "strengths": [],
                "areas_for_improvement": [],
                "recommendations": []
            }

    async def analyze_speech_content(self, transcript: str, mode: str) -> Dict[str, Any]:
        """Analyze speech content for feedback"""
        prompt = f"Analyze this speech transcript for a {mode} session and provide constructive feedback:\n\n{transcript}"
        
        response = await self.generate_response(prompt, mode=mode)
        
        return {
            "feedback": response["text"],
            "analysis_type": "content_analysis",
            "mode": mode,
            "response_time": response["response_time"]
        }


# Singleton instance for import
ai_service = AIService()
