"""
Chat Module Templates

Prompt templates for different agent modes and system prompts.
"""

from typing import Dict, List, Optional
from string import Template


# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

SYSTEM_PROMPTS = {
    "general": """You are Lyo, a friendly and knowledgeable AI learning assistant.

Your role:
- Help students learn effectively through clear explanations
- Be encouraging and supportive
- Adapt your communication style to the user's level
- Provide accurate, well-structured information
- Suggest next steps and related topics when appropriate

Keep responses concise but thorough. Use examples when helpful.""",

    "quick_explainer": """You are Lyo, an expert at providing quick, clear explanations.

Your role:
- Explain concepts in a simple, accessible way
- Start with the core idea, then add details
- Use analogies and real-world examples
- Break complex topics into digestible parts
- Highlight key takeaways

Keep explanations focused and avoid unnecessary tangents.
Format: Brief intro → Core explanation → Key points → Related concepts.""",

    "course_planner": """You are Lyo, an expert curriculum designer and learning path planner.

Your role:
- Create structured, progressive learning paths
- Break topics into logical modules and lessons
- Consider the learner's current level and goals
- Include practical exercises and assessments
- Estimate realistic time requirements
- Suggest prerequisites when needed

Output course structures in a clear, organized format.
Consider different learning styles and include varied content types.""",

    "practice": """You are Lyo, an expert at creating educational practice materials.

Your role:
- Generate challenging but fair practice questions
- Cover key concepts thoroughly
- Provide multiple question types (MCQ, true/false, open-ended)
- Include clear explanations for answers
- Progressive difficulty when appropriate
- Focus on understanding, not just memorization

Questions should test comprehension and application of knowledge.""",

    "note_taker": """You are Lyo, an expert at synthesizing and organizing information.

Your role:
- Extract key concepts and main ideas
- Organize information logically
- Create clear, scannable summaries
- Highlight important terms and definitions
- Identify connections between concepts
- Suggest tags for categorization

Output should be structured, easy to review, and useful for studying."""
}


# =============================================================================
# MODE-SPECIFIC TEMPLATES
# =============================================================================

class PromptTemplates:
    """Collection of prompt templates for different modes and actions"""
    
    @staticmethod
    def quick_explain(topic: str, depth: str = "brief", context: Optional[str] = None) -> str:
        """Generate prompt for quick explanation"""
        depth_instructions = {
            "brief": "Provide a concise 2-3 sentence explanation.",
            "moderate": "Provide a clear explanation with key details and an example.",
            "detailed": "Provide a thorough explanation with multiple examples and nuances."
        }
        
        prompt = f"""Explain the following topic: {topic}

{depth_instructions.get(depth, depth_instructions['moderate'])}
"""
        if context:
            prompt += f"\nContext: {context}"
        
        prompt += """

Structure your response as:
1. Core explanation
2. Key points (2-4 bullet points)
3. A practical example or analogy
4. One related topic to explore next"""
        
        return prompt
    
    @staticmethod
    def course_plan(
        topic: str,
        goal: Optional[str] = None,
        time_available: Optional[str] = None,
        current_level: str = "beginner"
    ) -> str:
        """Generate prompt for course planning"""
        prompt = f"""Create a structured learning path for: {topic}

Learner level: {current_level}
"""
        if goal:
            prompt += f"Learning goal: {goal}\n"
        if time_available:
            prompt += f"Time available: {time_available}\n"
        
        prompt += """
Create a course with:
1. Course title and description
2. 3-5 modules, each containing 2-4 lessons
3. Learning objectives for the course
4. Prerequisites (if any)
5. Estimated time per module

For each module, provide:
- Module title
- Brief description
- Lesson titles with estimated minutes
- Key learning outcomes

Format as JSON with this structure:
{
    "title": "Course Title",
    "description": "Course description",
    "estimated_hours": 10,
    "prerequisites": ["prerequisite1"],
    "learning_objectives": ["objective1", "objective2"],
    "modules": [
        {
            "id": "module_1",
            "title": "Module Title",
            "description": "Module description",
            "estimated_minutes": 60,
            "lessons": [
                {"id": "lesson_1", "title": "Lesson Title", "duration_minutes": 15}
            ]
        }
    ]
}"""
        
        return prompt
    
    @staticmethod
    def practice_quiz(
        topic: str,
        difficulty: str = "intermediate",
        question_count: int = 5,
        question_types: Optional[List[str]] = None
    ) -> str:
        """Generate prompt for practice quiz"""
        types_str = ", ".join(question_types) if question_types else "multiple_choice, true_false"
        
        prompt = f"""Generate a practice quiz on: {topic}

Difficulty: {difficulty}
Number of questions: {question_count}
Question types: {types_str}

For each question, provide:
1. The question text
2. Question type
3. Options (for multiple choice)
4. Correct answer
5. Explanation of why the answer is correct
6. Difficulty rating

Format as JSON:
{{
    "quiz_id": "generated_id",
    "topic": "{topic}",
    "questions": [
        {{
            "id": "q1",
            "question": "Question text",
            "question_type": "multiple_choice",
            "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
            "correct_answer": "A",
            "explanation": "Explanation here",
            "difficulty": "{difficulty}"
        }}
    ]
}}"""
        
        return prompt
    
    @staticmethod
    def take_note(
        content: str,
        title: Optional[str] = None,
        extract_key_points: bool = True
    ) -> str:
        """Generate prompt for note taking"""
        prompt = f"""Create a structured note from the following content:

{content}

"""
        if title:
            prompt += f"Suggested title: {title}\n"
        
        if extract_key_points:
            prompt += """
Extract and organize:
1. Main topic/subject
2. Key concepts (3-5 bullet points)
3. Important definitions or terms
4. Summary (2-3 sentences)
5. Suggested tags for categorization

Format as JSON:
{
    "title": "Note Title",
    "summary": "Brief summary",
    "key_points": ["point1", "point2"],
    "terms": [{"term": "definition"}],
    "tags": ["tag1", "tag2"],
    "content": "Full organized note content"
}"""
        else:
            prompt += "\nOrganize and clean up this content into a clear note format."
        
        return prompt
    
    @staticmethod
    def explain_more(previous_response: str, specific_aspect: Optional[str] = None) -> str:
        """Generate prompt for expanded explanation"""
        prompt = f"""Based on this previous explanation:

{previous_response}

"""
        if specific_aspect:
            prompt += f"Provide more detail specifically about: {specific_aspect}"
        else:
            prompt += "Provide a more detailed explanation with additional examples and nuances."
        
        prompt += "\n\nInclude practical applications where relevant."
        
        return prompt
    
    @staticmethod
    def summarize(content: str, max_length: Optional[int] = None) -> str:
        """Generate prompt for summarization"""
        length_instruction = ""
        if max_length:
            length_instruction = f"Keep the summary under {max_length} words."
        
        return f"""Summarize the following content:

{content}

{length_instruction}

Provide:
1. A concise summary of the main points
2. Key takeaways (bullet points)
3. Any important caveats or considerations"""


# =============================================================================
# ROUTING TEMPLATES
# =============================================================================

class RouterTemplates:
    """Templates for mode routing decisions"""
    
    @staticmethod
    def mode_detection(message: str, context: Optional[str] = None) -> str:
        """Generate prompt for detecting appropriate mode"""
        return f"""Analyze this user message and determine the most appropriate response mode.

User message: "{message}"
{f'Context: {context}' if context else ''}

Modes available:
- quick_explainer: For "what is", "explain", "define", simple concept questions
    - course_planner: For "create course", "start class", "learning path", "teach me", "help me learn", structured learning requests
- practice: For "quiz me", "test", "practice", "exercise" requests
- note_taker: For "save this", "note", "remember", "summarize" requests
- general: For conversation, questions, or when unclear

Respond with JSON:
{{
    "mode": "detected_mode",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}"""
    
    @staticmethod
    def action_handling(action: str, message: str, context: Optional[str] = None) -> str:
        """Generate prompt for handling chip actions"""
        action_descriptions = {
            "practice": "Generate practice questions based on the conversation",
            "take_note": "Create a note from the conversation content",
            "explain_more": "Provide more detailed explanation",
            "quiz_me": "Create a quick quiz on the topic",
            "create_course": "Create a structured course plan",
            "summarize": "Summarize the key points discussed"
        }
        
        action_desc = action_descriptions.get(action, "Handle the user's request")
        
        return f"""Action requested: {action}
Action meaning: {action_desc}

User message: {message}
{f'Context: {context}' if context else ''}

Execute this action appropriately based on the conversation context."""


# =============================================================================
# CTA TEMPLATES
# =============================================================================

class CTATemplates:
    """Templates for generating CTAs"""
    
    # Standard CTA definitions by context
    STANDARD_CTAS = {
        "after_explanation": [
            {
                "type": "practice_now",
                "label": "Practice This",
                "action": "practice",
                "priority": 1
            },
            {
                "type": "take_note",
                "label": "Save Note",
                "action": "take_note",
                "priority": 2
            },
            {
                "type": "explain_more",
                "label": "Learn More",
                "action": "explain_more",
                "priority": 3
            }
        ],
        "after_course_plan": [
            {
                "type": "start_course",
                "label": "Start Learning",
                "action": "open_classroom",
                "priority": 1
            },
            {
                "type": "customize",
                "label": "Customize Plan",
                "action": "customize_course",
                "priority": 2
            },
            {
                "type": "share",
                "label": "Share",
                "action": "share_course",
                "priority": 3
            }
        ],
        "after_quiz": [
            {
                "type": "review_answers",
                "label": "Review Answers",
                "action": "review_answers",
                "priority": 1
            },
            {
                "type": "try_again",
                "label": "Try Again",
                "action": "retry_quiz",
                "priority": 2
            },
            {
                "type": "move_on",
                "label": "Continue Learning",
                "action": "next_topic",
                "priority": 3
            }
        ],
        "after_note": [
            {
                "type": "view_notes",
                "label": "View All Notes",
                "action": "view_notes",
                "priority": 1
            },
            {
                "type": "continue",
                "label": "Continue Chat",
                "action": "continue",
                "priority": 2
            }
        ]
    }
    
    # Standard chip actions by mode
    STANDARD_CHIPS = {
        "quick_explainer": [
            {"action": "explain_more", "label": "Explain More", "icon": "expand"},
            {"action": "practice", "label": "Practice", "icon": "quiz"},
            {"action": "take_note", "label": "Take Note", "icon": "note"},
            {"action": "create_course", "label": "Create Course", "icon": "course"}
        ],
        "course_planner": [
            {"action": "practice", "label": "Quiz Me", "icon": "quiz"},
            {"action": "take_note", "label": "Save Plan", "icon": "note"},
            {"action": "summarize", "label": "Summarize", "icon": "summary"}
        ],
        "practice": [
            {"action": "explain_more", "label": "Explain Answer", "icon": "explain"},
            {"action": "take_note", "label": "Save Question", "icon": "note"},
            {"action": "practice", "label": "More Practice", "icon": "quiz"}
        ],
        "note_taker": [
            {"action": "practice", "label": "Practice", "icon": "quiz"},
            {"action": "explain_more", "label": "Expand", "icon": "expand"}
        ],
        "general": [
            {"action": "explain_more", "label": "Tell Me More", "icon": "expand"},
            {"action": "practice", "label": "Quiz Me", "icon": "quiz"},
            {"action": "take_note", "label": "Take Note", "icon": "note"},
            {"action": "create_course", "label": "Create Course", "icon": "course"}
        ]
    }
    
    @classmethod
    def get_ctas_for_context(cls, context: str) -> List[Dict]:
        """Get appropriate CTAs for a given context"""
        return cls.STANDARD_CTAS.get(context, cls.STANDARD_CTAS["after_explanation"])
    
    @classmethod
    def get_chips_for_mode(cls, mode: str) -> List[Dict]:
        """Get appropriate chip actions for a given mode"""
        return cls.STANDARD_CHIPS.get(mode, cls.STANDARD_CHIPS["general"])


# =============================================================================
# POST-PROCESSING TEMPLATES
# =============================================================================

class PostProcessingTemplates:
    """Templates for response post-processing"""
    
    @staticmethod
    def clean_response(response: str, max_length: Optional[int] = None) -> str:
        """Instructions for cleaning/formatting a response"""
        return f"""Clean and format this response:

{response}

Rules:
1. Remove any duplicate information
2. Ensure proper markdown formatting
3. Keep language clear and concise
{f'4. Maximum length: {max_length} characters' if max_length else ''}

Return the cleaned response."""
    
    @staticmethod
    def extract_structured_data(response: str, expected_format: str) -> str:
        """Instructions for extracting structured data"""
        return f"""Extract structured data from this response:

{response}

Expected format:
{expected_format}

Return valid JSON matching the expected format."""
