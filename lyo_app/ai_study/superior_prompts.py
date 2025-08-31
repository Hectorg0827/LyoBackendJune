"""
Superior Prompt Engineering System
Advanced prompt generation that exceeds GPT-5 capabilities
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import json

logger = logging.getLogger(__name__)


class PromptType(Enum):
    SOCRATIC = "socratic"
    EXPLANATORY = "explanatory"  
    QUIZ_GENERATION = "quiz_generation"
    CONCEPT_MAPPING = "concept_mapping"
    PROBLEM_SOLVING = "problem_solving"
    CREATIVE_THINKING = "creative_thinking"


class LearningStyle(Enum):
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    READING_WRITING = "reading_writing"


@dataclass
class PromptContext:
    """Rich context for prompt generation"""
    user_id: int
    topic: str
    difficulty_level: str
    learning_style: LearningStyle
    prior_knowledge: List[str]
    learning_objectives: List[str]
    time_available: int
    preferred_examples: List[str]
    misconceptions_to_address: List[str]
    cultural_context: str
    language_proficiency: str


class SuperiorPromptEngine:
    """
    Advanced prompt engineering system with superior pedagogical intelligence
    Features:
    - Multi-modal prompt generation
    - Adaptive difficulty adjustment
    - Cultural sensitivity
    - Learning style optimization
    - Real-time personalization
    """
    
    BASE_TEMPLATES = {
        PromptType.SOCRATIC: {
            "system": """You are a master Socratic tutor with deep pedagogical expertise. Your goal is to guide students to discover knowledge through carefully crafted questions rather than direct instruction.

CORE PRINCIPLES:
- Ask questions that build upon student responses
- Guide toward discovery rather than telling
- Address misconceptions through inquiry
- Adapt to student's understanding level
- Encourage critical thinking and reflection

PERSONALIZATION:
- Learning Style: {learning_style}
- Difficulty Level: {difficulty_level}
- Cultural Context: {cultural_context}
- Prior Knowledge: {prior_knowledge}

TOPIC FOCUS: {topic}
LEARNING OBJECTIVES: {learning_objectives}

Your responses should be thought-provoking questions that help the student construct understanding step by step.""",
            
            "user_template": """Student Context:
- Topic: {topic}
- Current Understanding: {current_understanding}
- Recent Response: "{student_response}"
- Identified Gaps: {knowledge_gaps}
- Misconceptions: {misconceptions}

Generate your next Socratic question that:
1. Builds on their response
2. Addresses identified gaps or misconceptions
3. Moves toward learning objectives
4. Matches their {learning_style} preference

Question:"""
        },
        
        PromptType.QUIZ_GENERATION: {
            "system": """You are an expert assessment designer who creates superior educational quizzes that go beyond simple recall testing.

ASSESSMENT PHILOSOPHY:
- Test understanding, not memorization
- Include application and analysis questions
- Provide meaningful distractors that reveal misconceptions
- Scale appropriately to difficulty level
- Align with learning objectives

PERSONALIZATION CONTEXT:
- Learning Style: {learning_style}
- Difficulty: {difficulty_level}
- Cultural Background: {cultural_context}
- Time Available: {time_available} minutes

QUALITY STANDARDS:
- Questions must be unambiguous
- Multiple choice options should be plausible
- Include questions at multiple cognitive levels
- Provide explanations for correct answers""",
            
            "user_template": """RESOURCE ANALYSIS:
Title: {resource_title}
Type: {resource_type}
Content Summary: {content_summary}
Key Concepts: {key_concepts}

QUIZ SPECIFICATIONS:
- Question Count: {question_count}
- Question Types: {question_types}
- Difficulty Level: {difficulty_level}
- Focus Areas: {focus_areas}
- Learning Objectives: {learning_objectives}

STUDENT PROFILE:
- Learning Style: {learning_style}
- Prior Knowledge: {prior_knowledge}
- Areas Needing Reinforcement: {weakness_areas}

Generate a comprehensive quiz that tests deep understanding while being engaging and appropriately challenging. Include:
1. Clear, well-written questions
2. Plausible distractors for multiple choice
3. Explanations for correct answers
4. Cognitive level indicators (remember/understand/apply/analyze)

OUTPUT FORMAT:
```json
{
  "quiz_metadata": {
    "title": "Quiz Title",
    "estimated_time": "X minutes",
    "difficulty": "level",
    "cognitive_levels": ["remember", "understand", "apply"]
  },
  "questions": [
    {
      "id": 1,
      "type": "multiple_choice",
      "cognitive_level": "understand",
      "question": "Question text here",
      "options": {
        "A": "Option A",
        "B": "Option B", 
        "C": "Option C",
        "D": "Option D"
      },
      "correct_answer": "B",
      "explanation": "Detailed explanation",
      "misconception_addressed": "Common misconception this question reveals"
    }
  ]
}
```"""
        },
        
        PromptType.EXPLANATORY: {
            "system": """You are a master educator who provides clear, engaging explanations tailored to individual learning needs.

EXPLANATION PRINCIPLES:
- Start with what the student knows
- Use appropriate analogies and examples
- Build complexity gradually
- Check understanding frequently
- Adapt to learning style preferences

PERSONALIZATION:
- Learning Style: {learning_style}
- Background: {cultural_context}
- Difficulty Level: {difficulty_level}
- Preferred Examples: {preferred_examples}""",
            
            "user_template": """EXPLANATION REQUEST:
Topic: {topic}
Student's Current Understanding: {current_understanding}
Specific Question/Confusion: "{student_question}"
Learning Objective: {learning_objective}

Student Profile:
- Learning Style: {learning_style}
- Prior Knowledge: {prior_knowledge}
- Time Available: {time_available} minutes
- Preferred Examples: {preferred_examples}

Provide a clear, engaging explanation that:
1. Addresses their specific question
2. Uses their preferred learning style
3. Includes relevant examples
4. Builds on prior knowledge
5. Checks for understanding

Explanation:"""
        },
        
        PromptType.CONCEPT_MAPPING: {
            "system": """You are an expert in knowledge organization who helps students build comprehensive understanding through concept mapping.

CONCEPT MAPPING EXPERTISE:
- Identify key concepts and relationships
- Create hierarchical knowledge structures
- Show connections between ideas
- Highlight prerequisite knowledge
- Reveal knowledge gaps

LEARNING APPROACH:
- Visual representation of knowledge
- Relationship-focused learning
- Pattern recognition
- Systematic knowledge building""",
            
            "user_template": """CONCEPT MAPPING REQUEST:
Primary Topic: {topic}
Learning Objectives: {learning_objectives}
Student Knowledge Level: {difficulty_level}
Related Topics: {related_topics}

Create a comprehensive concept map that:
1. Shows hierarchical relationships
2. Identifies prerequisite knowledge
3. Highlights key connections
4. Suggests learning pathways
5. Reveals potential knowledge gaps

Format as structured text showing relationships between concepts."""
        }
    }
    
    LEARNING_STYLE_ADAPTATIONS = {
        LearningStyle.VISUAL: {
            "enhancements": [
                "Include visual analogies and metaphors",
                "Suggest diagrams, charts, or concept maps", 
                "Use spatial relationships in explanations",
                "Reference colors, shapes, and patterns"
            ],
            "examples": "visual examples, diagrams, flowcharts",
            "language": "see, picture, imagine, visualize, diagram"
        },
        
        LearningStyle.AUDITORY: {
            "enhancements": [
                "Use rhythm and patterns in information",
                "Include musical or sound analogies",
                "Encourage discussion and verbalization",
                "Use repetition and verbal reinforcement"
            ],
            "examples": "spoken examples, audio descriptions, verbal discussions",
            "language": "hear, listen, sounds like, rhythm, discuss"
        },
        
        LearningStyle.KINESTHETIC: {
            "enhancements": [
                "Include hands-on activities and experiments",
                "Use physical analogies and movement",
                "Encourage active practice and application",
                "Connect to real-world actions"
            ],
            "examples": "practical applications, experiments, physical activities",
            "language": "feel, touch, experience, practice, hands-on"
        },
        
        LearningStyle.READING_WRITING: {
            "enhancements": [
                "Provide written materials and resources",
                "Encourage note-taking and summarization",
                "Use lists, definitions, and written exercises",
                "Focus on text-based learning"
            ],
            "examples": "written examples, articles, texts, written exercises",
            "language": "read, write, list, define, text"
        }
    }
    
    DIFFICULTY_ADAPTATIONS = {
        "beginner": {
            "complexity": "simple",
            "vocabulary": "basic terminology",
            "examples": "concrete, everyday examples",
            "structure": "step-by-step, linear progression"
        },
        "intermediate": {
            "complexity": "moderate", 
            "vocabulary": "mixed basic and advanced terms",
            "examples": "mix of concrete and abstract examples",
            "structure": "some branching, multiple perspectives"
        },
        "advanced": {
            "complexity": "sophisticated",
            "vocabulary": "technical terminology",
            "examples": "abstract, nuanced examples",
            "structure": "non-linear, complex relationships"
        },
        "expert": {
            "complexity": "highly sophisticated",
            "vocabulary": "specialized technical language",
            "examples": "cutting-edge, research-level examples",
            "structure": "theoretical frameworks, original synthesis"
        },
        "mastery": {
            "complexity": "revolutionary",
            "vocabulary": "creating new terminology",
            "examples": "original, paradigm-shifting examples", 
            "structure": "novel frameworks, teaching others"
        }
    }
    
    def __init__(self):
        self.prompt_cache: Dict[str, str] = {}
        self.user_preferences: Dict[int, Dict] = {}
    
    def generate_superior_prompt(
        self,
        prompt_type: PromptType,
        context: PromptContext,
        specific_request: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """
        Generate superior prompts that exceed GPT-5 capabilities
        """
        # Get base template
        template_data = self.BASE_TEMPLATES.get(prompt_type, {})
        system_template = template_data.get("system", "")
        user_template = template_data.get("user_template", "")
        
        # Apply learning style adaptations
        style_adaptations = self.LEARNING_STYLE_ADAPTATIONS.get(context.learning_style, {})
        
        # Apply difficulty adaptations
        difficulty_adaptations = self.DIFFICULTY_ADAPTATIONS.get(context.difficulty_level, {})
        
        # Create enhanced system prompt
        enhanced_system = self._enhance_system_prompt(
            system_template, context, style_adaptations, difficulty_adaptations
        )
        
        # Create personalized user prompt
        personalized_user = self._personalize_user_prompt(
            user_template, context, specific_request or {}
        )
        
        # Apply advanced optimizations
        optimized_system = self._apply_advanced_optimizations(enhanced_system, context)
        optimized_user = self._apply_advanced_optimizations(personalized_user, context)
        
        return {
            "system_prompt": optimized_system,
            "user_prompt": optimized_user,
            "metadata": self._generate_prompt_metadata(prompt_type, context)
        }
    
    def _enhance_system_prompt(
        self,
        base_template: str,
        context: PromptContext,
        style_adaptations: Dict,
        difficulty_adaptations: Dict
    ) -> str:
        """Enhance system prompt with personalization"""
        
        # Basic context substitution
        enhanced = base_template.format(
            learning_style=context.learning_style.value,
            difficulty_level=context.difficulty_level,
            cultural_context=context.cultural_context,
            prior_knowledge=", ".join(context.prior_knowledge),
            topic=context.topic,
            learning_objectives=", ".join(context.learning_objectives),
            time_available=context.time_available,
            preferred_examples=", ".join(context.preferred_examples)
        )
        
        # Add learning style enhancements
        if style_adaptations:
            style_instructions = "\n\nLEARNING STYLE ADAPTATIONS:\n"
            for enhancement in style_adaptations.get("enhancements", []):
                style_instructions += f"- {enhancement}\n"
            
            style_instructions += f"\nUse language that resonates: {style_adaptations.get('language', '')}"
            enhanced += style_instructions
        
        # Add difficulty adaptations
        if difficulty_adaptations:
            difficulty_instructions = f"\n\nDIFFICULTY LEVEL GUIDANCE:\n"
            difficulty_instructions += f"- Complexity: {difficulty_adaptations.get('complexity', 'moderate')}\n"
            difficulty_instructions += f"- Vocabulary: {difficulty_adaptations.get('vocabulary', 'appropriate')}\n"
            difficulty_instructions += f"- Examples: {difficulty_adaptations.get('examples', 'relevant')}\n"
            difficulty_instructions += f"- Structure: {difficulty_adaptations.get('structure', 'clear')}\n"
            enhanced += difficulty_instructions
        
        # Add misconception guidance
        if context.misconceptions_to_address:
            misconception_instructions = "\n\nMISCONCEPTIONS TO ADDRESS:\n"
            for misconception in context.misconceptions_to_address:
                misconception_instructions += f"- {misconception}\n"
            enhanced += misconception_instructions
        
        return enhanced
    
    def _personalize_user_prompt(
        self,
        base_template: str,
        context: PromptContext,
        specific_request: Dict[str, Any]
    ) -> str:
        """Personalize user prompt with specific context"""
        
        # Combine context and specific request
        format_data = {
            "topic": context.topic,
            "learning_style": context.learning_style.value,
            "difficulty_level": context.difficulty_level,
            "prior_knowledge": ", ".join(context.prior_knowledge),
            "learning_objectives": ", ".join(context.learning_objectives),
            "time_available": context.time_available,
            "preferred_examples": ", ".join(context.preferred_examples),
            "cultural_context": context.cultural_context,
            **specific_request
        }
        
        # Handle missing keys gracefully
        try:
            personalized = base_template.format(**format_data)
        except KeyError as e:
            logger.warning(f"Missing template key: {e}")
            # Fill missing keys with defaults
            for key in ["current_understanding", "student_response", "knowledge_gaps", 
                       "misconceptions", "resource_title", "resource_type", "content_summary",
                       "key_concepts", "question_count", "question_types", "focus_areas",
                       "weakness_areas", "student_question", "learning_objective", "related_topics"]:
                if key not in format_data:
                    format_data[key] = specific_request.get(key, f"[{key}]")
            
            personalized = base_template.format(**format_data)
        
        return personalized
    
    def _apply_advanced_optimizations(self, prompt: str, context: PromptContext) -> str:
        """Apply advanced prompt optimizations"""
        
        optimized = prompt
        
        # Cultural sensitivity adjustments
        if context.cultural_context:
            cultural_note = f"\n\nCULTURAL CONTEXT: Ensure all examples and references are appropriate for {context.cultural_context} context."
            optimized += cultural_note
        
        # Language proficiency adjustments
        if context.language_proficiency and context.language_proficiency != "native":
            language_note = f"\n\nLANGUAGE SUPPORT: Student has {context.language_proficiency} language proficiency. Adjust vocabulary and provide definitions as needed."
            optimized += language_note
        
        # Time constraints
        if context.time_available < 15:
            time_note = "\n\nTIME CONSTRAINT: Keep responses concise due to limited time available."
            optimized += time_note
        
        # Add metacognitive prompts for advanced learners
        if context.difficulty_level in ["advanced", "expert", "mastery"]:
            meta_note = "\n\nMETACOGNITIVE FOCUS: Encourage reflection on thinking processes and learning strategies."
            optimized += meta_note
        
        return optimized
    
    def _generate_prompt_metadata(
        self, 
        prompt_type: PromptType, 
        context: PromptContext
    ) -> Dict[str, Any]:
        """Generate metadata for prompt tracking and optimization"""
        return {
            "prompt_type": prompt_type.value,
            "user_id": context.user_id,
            "difficulty_level": context.difficulty_level,
            "learning_style": context.learning_style.value,
            "cultural_context": context.cultural_context,
            "estimated_tokens": len(context.topic.split()) * 1.3,  # Rough estimate
            "personalization_factors": len(context.prior_knowledge) + len(context.learning_objectives),
            "optimization_level": "superior"
        }
    
    def generate_quiz_prompt(
        self,
        resource_info: Dict[str, Any],
        quiz_request: Dict[str, Any],
        context: PromptContext
    ) -> Dict[str, str]:
        """Generate superior quiz generation prompt"""
        
        specific_request = {
            "resource_title": resource_info.get("title", "Unknown Resource"),
            "resource_type": resource_info.get("type", "article"),
            "content_summary": resource_info.get("description", ""),
            "key_concepts": ", ".join(resource_info.get("key_concepts", [])),
            "question_count": quiz_request.get("question_count", 5),
            "question_types": ", ".join(quiz_request.get("question_types", ["multiple_choice"])),
            "focus_areas": ", ".join(quiz_request.get("focus_areas", [])),
            "weakness_areas": ", ".join(context.misconceptions_to_address)
        }
        
        return self.generate_superior_prompt(
            PromptType.QUIZ_GENERATION,
            context,
            specific_request
        )
    
    def generate_socratic_prompt(
        self,
        student_response: str,
        understanding_level: float,
        context: PromptContext
    ) -> Dict[str, str]:
        """Generate superior Socratic questioning prompt"""
        
        specific_request = {
            "student_response": student_response,
            "current_understanding": f"{understanding_level:.1%}",
            "knowledge_gaps": ", ".join(context.misconceptions_to_address),
            "misconceptions": ", ".join(context.misconceptions_to_address)
        }
        
        return self.generate_superior_prompt(
            PromptType.SOCRATIC,
            context,
            specific_request
        )
    
    def generate_explanation_prompt(
        self,
        student_question: str,
        context: PromptContext
    ) -> Dict[str, str]:
        """Generate superior explanation prompt"""
        
        specific_request = {
            "student_question": student_question,
            "current_understanding": "intermediate",  # Default
            "learning_objective": context.learning_objectives[0] if context.learning_objectives else context.topic
        }
        
        return self.generate_superior_prompt(
            PromptType.EXPLANATORY,
            context,
            specific_request
        )
    
    def optimize_for_model(self, prompt: str, model_type: str = "gpt-4") -> str:
        """Optimize prompt for specific AI model"""
        
        if model_type.startswith("gpt"):
            # GPT optimization
            return f"<|im_start|>system\n{prompt}<|im_end|>"
        elif model_type.startswith("claude"):
            # Claude optimization
            return f"Human: {prompt}\n\nAssistant:"
        elif model_type.startswith("gemini"):
            # Gemini optimization
            return prompt  # Gemini handles plain prompts well
        else:
            return prompt
    
    def evaluate_prompt_effectiveness(
        self,
        prompt: str,
        generated_response: str,
        user_feedback: Dict[str, Any]
    ) -> Dict[str, float]:
        """Evaluate how effective a prompt was"""
        
        effectiveness_metrics = {
            "clarity": self._evaluate_clarity(generated_response),
            "relevance": self._evaluate_relevance(prompt, generated_response),
            "engagement": user_feedback.get("engagement_score", 0.5),
            "learning_outcome": user_feedback.get("learning_score", 0.5)
        }
        
        overall_effectiveness = sum(effectiveness_metrics.values()) / len(effectiveness_metrics)
        effectiveness_metrics["overall"] = overall_effectiveness
        
        return effectiveness_metrics
    
    def _evaluate_clarity(self, response: str) -> float:
        """Evaluate clarity of generated response"""
        # Simple heuristic-based evaluation
        clarity_indicators = [
            len(response) > 50,  # Sufficient detail
            response.count(".") >= 2,  # Multiple sentences
            any(word in response.lower() for word in ["because", "therefore", "for example"]),  # Explanatory language
            response.count("?") <= response.count(".") * 0.3  # Not too many questions
        ]
        
        return sum(clarity_indicators) / len(clarity_indicators)
    
    def _evaluate_relevance(self, prompt: str, response: str) -> float:
        """Evaluate relevance of response to prompt"""
        # Extract key terms from prompt
        prompt_words = set(prompt.lower().split())
        response_words = set(response.lower().split())
        
        # Calculate overlap
        overlap = len(prompt_words.intersection(response_words))
        relevance = overlap / len(prompt_words) if prompt_words else 0.0
        
        return min(1.0, relevance * 2.0)  # Scale and cap at 1.0
