"""
Graph Course Generator - Converts Courses to Interactive Cinema Format

This service bridges the existing multi-agent course generation pipeline
with the new graph-based LearningNode structure for interactive cinema playback.

Features:
- Converts CurriculumStructure → GraphCourse with LearningNodes
- Adds interactive checkpoints (questions) at key points
- Creates remediation branches for common misconceptions
- Builds edge conditions for adaptive routing
- Generates hooks, transitions, and summaries
"""

import asyncio
import json
import logging
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from lyo_app.ai_classroom.models import (
    GraphCourse,
    LearningNode,
    LearningEdge,
    Concept,
    Misconception,
    NodeType,
    EdgeCondition
)
from lyo_app.ai_agents.multi_agent_v2.schemas.course_schemas import (
    CurriculumStructure,
    LessonContent,
    ModuleOutline,
    LessonOutline,
    CourseAssessments,
    ContentBlock,
    TextBlock,
    CodeBlock,
    ExerciseBlock,
    QuizQuestion
)
from lyo_app.core.ai_resilience import AIResilienceManager

logger = logging.getLogger(__name__)


class NodeGenerationType(str, Enum):
    """How the node was generated"""
    CONVERTED = "converted"       # From existing lesson content
    SYNTHESIZED = "synthesized"   # Generated via LLM for flow
    TEMPLATE = "template"         # From template library


@dataclass
class GraphGenerationConfig:
    """Configuration for graph course generation"""
    add_hook_nodes: bool = True           # Add engaging hooks at start
    add_transition_nodes: bool = True      # Add transitions between modules
    add_summary_nodes: bool = True         # Add summaries after modules
    add_review_checkpoints: bool = True    # Add review questions
    max_interaction_interval: int = 5      # Max nodes between interactions
    generate_remediation: bool = True      # Auto-generate remediation paths
    max_remediation_hops: int = 2          # Max remediation depth
    synthesize_missing_scripts: bool = True  # Generate TTS scripts via LLM
    target_node_duration_minutes: float = 2.0  # Ideal node length


@dataclass
class ConversionResult:
    """Result of converting a course to graph format"""
    course_id: str
    nodes_created: int
    edges_created: int
    concepts_created: int
    remediation_nodes: int
    duration_seconds: float
    warnings: List[str] = field(default_factory=list)


class GraphCourseGenerator:
    """
    Generates interactive cinema graph courses from structured course content.
    
    The generator transforms linear course content into a rich directed graph
    that enables:
    1. Netflix-like playback with smooth narration
    2. Interactive checkpoints for engagement
    3. Adaptive remediation for struggling learners
    4. Spaced repetition integration for retention
    """
    
    def __init__(
        self,
        config: Optional[GraphGenerationConfig] = None,
        ai_manager: Optional[AIResilienceManager] = None
    ):
        self.config = config or GraphGenerationConfig()
        self.ai_manager = ai_manager or AIResilienceManager()
        
        # Track node ordering
        self._node_sequence: int = 0
        
        # Script generation prompt template
        self.SCRIPT_GENERATION_PROMPT = """
You are creating narration scripts for an AI tutor named Lyo that teaches through 
voice-guided lessons. The style should be warm, encouraging, and conversational - 
like a knowledgeable friend explaining concepts.

Content to convert into a narration script:
{content}

Requirements:
1. Write in first person as Lyo (use "I" and "we")
2. Keep it concise - aim for {target_duration} seconds of speaking
3. Use simple language that's easy to understand when heard (not read)
4. Include brief pauses (marked with ...) for dramatic effect
5. End with an engaging transition or question

Generate only the narration script, nothing else.
"""
        
        self.HOOK_GENERATION_PROMPT = """
Create an engaging hook for the start of a lesson about: {topic}

The hook should:
1. Grab attention with an interesting question or surprising fact
2. Be spoken by an AI tutor named Lyo
3. Be {duration} seconds when spoken
4. Create curiosity about the topic
5. Feel conversational and warm

Generate only the hook script.
"""
        
        self.TRANSITION_PROMPT = """
Create a smooth transition script from "{from_topic}" to "{to_topic}".

Requirements:
1. Briefly summarize what was just learned
2. Create a bridge to the next topic
3. Maintain learner momentum
4. Be about {duration} seconds when spoken
5. Use encouraging language

Generate only the transition script.
"""
    
    async def generate_graph_course(
        self,
        db: AsyncSession,
        curriculum: CurriculumStructure,
        lessons: List[LessonContent],
        assessments: Optional[CourseAssessments] = None,
        creator_id: Optional[str] = None
    ) -> Tuple[GraphCourse, ConversionResult]:
        """
        Convert a structured course into a graph-based course.
        
        Args:
            db: Database session
            curriculum: Course curriculum structure
            lessons: List of lesson contents
            assessments: Optional quiz/assessment data
            creator_id: ID of the course creator
            
        Returns:
            Tuple of (GraphCourse, ConversionResult)
        """
        start_time = datetime.utcnow()
        self._node_sequence = 0
        warnings: List[str] = []
        
        # Create the graph course
        course = GraphCourse(
            id=str(uuid4()),
            title=curriculum.course_title,
            description=curriculum.course_description,
            subject=self._extract_subject(curriculum),
            estimated_duration_minutes=int(curriculum.total_estimated_hours * 60),
            difficulty_level=self._map_difficulty(curriculum),
            prerequisites=json.dumps(self._extract_prerequisites(curriculum)),
            learning_objectives=json.dumps(self._extract_objectives(curriculum)),
            tags=json.dumps(self._extract_tags(curriculum)),
            created_by=creator_id,
            version=1,
            is_published=False
        )
        
        db.add(course)
        
        # Build lesson lookup for quick access
        lesson_lookup = {lesson.lesson_id: lesson for lesson in lessons}
        
        # Track created nodes for edge building
        all_nodes: List[LearningNode] = []
        module_end_nodes: Dict[str, LearningNode] = {}
        
        # Process each module
        for mod_idx, module in enumerate(curriculum.modules):
            module_nodes = await self._process_module(
                db=db,
                course=course,
                module=module,
                mod_idx=mod_idx,
                lesson_lookup=lesson_lookup,
                assessments=assessments,
                warnings=warnings
            )
            all_nodes.extend(module_nodes)
            
            if module_nodes:
                module_end_nodes[module.id] = module_nodes[-1]
        
        # Create concept entries
        concepts_created = await self._create_concepts(
            db=db,
            course=course,
            curriculum=curriculum,
            lessons=lessons
        )
        
        # Generate remediation nodes if enabled
        remediation_count = 0
        if self.config.generate_remediation:
            remediation_count = await self._generate_remediation_nodes(
                db=db,
                course=course,
                all_nodes=all_nodes,
                warnings=warnings
            )
        
        # Commit changes
        await db.commit()
        
        # Build result
        duration = (datetime.utcnow() - start_time).total_seconds()
        edge_count = await self._count_edges(db, course.id)
        
        result = ConversionResult(
            course_id=course.id,
            nodes_created=len(all_nodes),
            edges_created=edge_count,
            concepts_created=concepts_created,
            remediation_nodes=remediation_count,
            duration_seconds=duration,
            warnings=warnings
        )
        
        logger.info(
            f"Generated graph course '{course.title}': "
            f"{result.nodes_created} nodes, {result.edges_created} edges "
            f"in {duration:.2f}s"
        )
        
        return course, result
    
    async def _process_module(
        self,
        db: AsyncSession,
        course: GraphCourse,
        module: ModuleOutline,
        mod_idx: int,
        lesson_lookup: Dict[str, LessonContent],
        assessments: Optional[CourseAssessments],
        warnings: List[str]
    ) -> List[LearningNode]:
        """Process a single module and its lessons into nodes"""
        nodes: List[LearningNode] = []
        prev_node: Optional[LearningNode] = None
        interaction_counter = 0
        
        # Add hook node at module start
        if self.config.add_hook_nodes:
            hook_node = await self._create_hook_node(
                db=db,
                course=course,
                module=module,
                mod_idx=mod_idx
            )
            nodes.append(hook_node)
            prev_node = hook_node
        
        # Process each lesson in the module
        for les_idx, lesson_outline in enumerate(module.lessons):
            # Try to find matching lesson content
            # Lesson IDs might be formatted differently
            lesson_content = self._find_lesson_content(
                lesson_outline, lesson_lookup
            )
            
            if lesson_content:
                # Convert lesson content to nodes
                lesson_nodes = await self._convert_lesson_to_nodes(
                    db=db,
                    course=course,
                    lesson_content=lesson_content,
                    mod_idx=mod_idx,
                    les_idx=les_idx
                )
                
                for node in lesson_nodes:
                    nodes.append(node)
                    
                    # Link from previous node
                    if prev_node:
                        await self._create_edge(
                            db=db,
                            source=prev_node,
                            target=node,
                            condition=EdgeCondition.ALWAYS.value
                        )
                    
                    prev_node = node
                    interaction_counter += 1
                    
                    # Add interaction checkpoint if needed
                    if (self.config.add_review_checkpoints and 
                        interaction_counter >= self.config.max_interaction_interval):
                        interaction_node = await self._create_interaction_node(
                            db=db,
                            course=course,
                            context_node=node,
                            assessments=assessments
                        )
                        if interaction_node:
                            await self._create_edge(
                                db=db,
                                source=node,
                                target=interaction_node,
                                condition=EdgeCondition.ALWAYS.value
                            )
                            nodes.append(interaction_node)
                            prev_node = interaction_node
                            interaction_counter = 0
            else:
                # No content found - create placeholder
                warnings.append(
                    f"No content for lesson: {lesson_outline.id} - {lesson_outline.title}"
                )
                placeholder = await self._create_placeholder_node(
                    db=db,
                    course=course,
                    lesson_outline=lesson_outline,
                    mod_idx=mod_idx,
                    les_idx=les_idx
                )
                nodes.append(placeholder)
                if prev_node:
                    await self._create_edge(db, prev_node, placeholder, EdgeCondition.ALWAYS.value)
                prev_node = placeholder
        
        # Add summary node at module end
        if self.config.add_summary_nodes and nodes:
            summary_node = await self._create_summary_node(
                db=db,
                course=course,
                module=module,
                mod_idx=mod_idx
            )
            await self._create_edge(db, prev_node, summary_node, EdgeCondition.ALWAYS.value)
            nodes.append(summary_node)
        
        return nodes
    
    async def _convert_lesson_to_nodes(
        self,
        db: AsyncSession,
        course: GraphCourse,
        lesson_content: LessonContent,
        mod_idx: int,
        les_idx: int
    ) -> List[LearningNode]:
        """Convert a lesson's content blocks into learning nodes"""
        nodes: List[LearningNode] = []
        
        # Create introduction narrative node
        intro_node = LearningNode(
            id=str(uuid4()),
            course_id=course.id,
            node_type=NodeType.NARRATIVE.value,
            title=f"Introduction: {lesson_content.title}",
            script_text=lesson_content.introduction,
            visual_cue=f"Introducing {lesson_content.title}",
            duration_seconds=self._estimate_duration(lesson_content.introduction),
            sequence_in_course=self._next_sequence(),
            module_index=mod_idx,
            lesson_index=les_idx,
            metadata=json.dumps({
                "lesson_id": lesson_content.lesson_id,
                "lesson_type": lesson_content.lesson_type.value
            })
        )
        db.add(intro_node)
        nodes.append(intro_node)
        
        # Convert content blocks
        for block in lesson_content.content_blocks:
            block_node = await self._convert_content_block(
                db=db,
                course=course,
                block=block,
                lesson_content=lesson_content,
                mod_idx=mod_idx,
                les_idx=les_idx
            )
            if block_node:
                nodes.append(block_node)
        
        # Create key takeaways node
        if lesson_content.key_takeaways:
            takeaways_script = self._format_takeaways(lesson_content.key_takeaways)
            takeaway_node = LearningNode(
                id=str(uuid4()),
                course_id=course.id,
                node_type=NodeType.SUMMARY.value,
                title=f"Key Takeaways: {lesson_content.title}",
                script_text=takeaways_script,
                visual_cue="Key takeaways summary",
                duration_seconds=self._estimate_duration(takeaways_script),
                sequence_in_course=self._next_sequence(),
                module_index=mod_idx,
                lesson_index=les_idx
            )
            db.add(takeaway_node)
            nodes.append(takeaway_node)
        
        return nodes
    
    async def _convert_content_block(
        self,
        db: AsyncSession,
        course: GraphCourse,
        block: ContentBlock,
        lesson_content: LessonContent,
        mod_idx: int,
        les_idx: int
    ) -> Optional[LearningNode]:
        """Convert a single content block to a learning node"""
        
        if isinstance(block, TextBlock):
            # Text blocks become narrative nodes
            script = await self._generate_narration_script(
                block.content,
                block.title
            )
            node = LearningNode(
                id=str(uuid4()),
                course_id=course.id,
                node_type=NodeType.NARRATIVE.value,
                title=block.title,
                script_text=script,
                visual_cue=f"Explanation: {block.title}",
                duration_seconds=self._estimate_duration(script),
                sequence_in_course=self._next_sequence(),
                module_index=mod_idx,
                lesson_index=les_idx,
                metadata=json.dumps({"original_content": block.content[:500]})
            )
            db.add(node)
            return node
            
        elif isinstance(block, CodeBlock):
            # Code blocks become explanation nodes with code display
            code_script = self._generate_code_explanation(block)
            node = LearningNode(
                id=str(uuid4()),
                course_id=course.id,
                node_type=NodeType.EXPLANATION.value,
                title=block.title,
                script_text=code_script,
                visual_cue=f"Code: {block.language}",
                duration_seconds=self._estimate_duration(code_script),
                sequence_in_course=self._next_sequence(),
                module_index=mod_idx,
                lesson_index=les_idx,
                metadata=json.dumps({
                    "code": block.code,
                    "language": block.language,
                    "filename": block.filename
                })
            )
            db.add(node)
            return node
            
        elif isinstance(block, ExerciseBlock):
            # Exercise blocks become interaction nodes
            node = LearningNode(
                id=str(uuid4()),
                course_id=course.id,
                node_type=NodeType.INTERACTION.value,
                title=block.title,
                script_text=f"Let's practice! {block.instructions}",
                visual_cue="Exercise time",
                duration_seconds=30,  # Interaction nodes have variable duration
                sequence_in_course=self._next_sequence(),
                module_index=mod_idx,
                lesson_index=les_idx,
                interaction_type="exercise",
                interaction_data=json.dumps({
                    "instructions": block.instructions,
                    "hints": block.hints,
                    "solution": block.solution,
                    "difficulty": block.difficulty
                }),
                metadata=json.dumps({"expected_output": block.expected_output})
            )
            db.add(node)
            return node
        
        return None
    
    async def _create_hook_node(
        self,
        db: AsyncSession,
        course: GraphCourse,
        module: ModuleOutline,
        mod_idx: int
    ) -> LearningNode:
        """Create an engaging hook node for module start"""
        hook_script = await self._generate_hook_script(
            module.title,
            module.description
        )
        
        node = LearningNode(
            id=str(uuid4()),
            course_id=course.id,
            node_type=NodeType.HOOK.value,
            title=f"Module {mod_idx + 1}: {module.title}",
            script_text=hook_script,
            visual_cue=f"Welcome to {module.title}",
            duration_seconds=self._estimate_duration(hook_script),
            sequence_in_course=self._next_sequence(),
            module_index=mod_idx,
            is_checkpoint=True  # Mark as checkpoint for tracking
        )
        db.add(node)
        return node
    
    async def _create_summary_node(
        self,
        db: AsyncSession,
        course: GraphCourse,
        module: ModuleOutline,
        mod_idx: int
    ) -> LearningNode:
        """Create a summary node for module end"""
        outcomes = module.learning_outcomes
        summary_script = self._generate_summary_script(
            module.title,
            outcomes
        )
        
        node = LearningNode(
            id=str(uuid4()),
            course_id=course.id,
            node_type=NodeType.SUMMARY.value,
            title=f"Summary: {module.title}",
            script_text=summary_script,
            visual_cue="Module complete!",
            duration_seconds=self._estimate_duration(summary_script),
            sequence_in_course=self._next_sequence(),
            module_index=mod_idx,
            is_checkpoint=True
        )
        db.add(node)
        return node
    
    async def _create_interaction_node(
        self,
        db: AsyncSession,
        course: GraphCourse,
        context_node: LearningNode,
        assessments: Optional[CourseAssessments]
    ) -> Optional[LearningNode]:
        """Create an interaction checkpoint node"""
        # Generate a quick check question based on recent content
        question_data = self._generate_quick_check(context_node, assessments)
        
        if not question_data:
            return None
        
        node = LearningNode(
            id=str(uuid4()),
            course_id=course.id,
            node_type=NodeType.INTERACTION.value,
            title="Quick Check",
            script_text="Let's see if you've got this! " + question_data["question"],
            visual_cue="Quick check time",
            duration_seconds=15,
            sequence_in_course=self._next_sequence(),
            module_index=context_node.module_index,
            lesson_index=context_node.lesson_index,
            interaction_type=question_data["type"],
            interaction_data=json.dumps(question_data),
            correct_answer=question_data.get("correct_answer")
        )
        db.add(node)
        return node
    
    async def _create_placeholder_node(
        self,
        db: AsyncSession,
        course: GraphCourse,
        lesson_outline: LessonOutline,
        mod_idx: int,
        les_idx: int
    ) -> LearningNode:
        """Create a placeholder node for missing content"""
        script = f"This lesson covers {lesson_outline.title}. {lesson_outline.description}"
        
        node = LearningNode(
            id=str(uuid4()),
            course_id=course.id,
            node_type=NodeType.NARRATIVE.value,
            title=lesson_outline.title,
            script_text=script,
            visual_cue=lesson_outline.title,
            duration_seconds=self._estimate_duration(script),
            sequence_in_course=self._next_sequence(),
            module_index=mod_idx,
            lesson_index=les_idx,
            metadata=json.dumps({"placeholder": True, "lesson_id": lesson_outline.id})
        )
        db.add(node)
        return node
    
    async def _create_edge(
        self,
        db: AsyncSession,
        source: LearningNode,
        target: LearningNode,
        condition: str,
        priority: int = 0
    ):
        """Create an edge between two nodes"""
        edge = LearningEdge(
            id=str(uuid4()),
            source_node_id=source.id,
            target_node_id=target.id,
            condition=condition,
            priority=priority
        )
        db.add(edge)
    
    async def _generate_remediation_nodes(
        self,
        db: AsyncSession,
        course: GraphCourse,
        all_nodes: List[LearningNode],
        warnings: List[str]
    ) -> int:
        """Generate remediation paths for interaction nodes"""
        count = 0
        
        for node in all_nodes:
            if node.node_type == NodeType.INTERACTION.value:
                # Create a remediation node for failed interactions
                remediation = await self._create_remediation_for_interaction(
                    db=db,
                    course=course,
                    interaction_node=node
                )
                if remediation:
                    # Create edge from interaction (on fail) to remediation
                    await self._create_edge(
                        db=db,
                        source=node,
                        target=remediation,
                        condition=EdgeCondition.FAIL.value,
                        priority=1
                    )
                    # Create edge from remediation back to retry
                    await self._create_edge(
                        db=db,
                        source=remediation,
                        target=node,
                        condition=EdgeCondition.ALWAYS.value
                    )
                    count += 1
        
        return count
    
    async def _create_remediation_for_interaction(
        self,
        db: AsyncSession,
        course: GraphCourse,
        interaction_node: LearningNode
    ) -> Optional[LearningNode]:
        """Create a remediation node for a failed interaction"""
        interaction_data = json.loads(interaction_node.interaction_data or "{}")
        
        # Generate remediation script
        remediation_script = self._generate_remediation_script(
            interaction_node.title,
            interaction_data
        )
        
        node = LearningNode(
            id=str(uuid4()),
            course_id=course.id,
            node_type=NodeType.REMEDIATION.value,
            title=f"Let's Review: {interaction_node.title}",
            script_text=remediation_script,
            visual_cue="Review time",
            duration_seconds=self._estimate_duration(remediation_script),
            sequence_in_course=self._next_sequence(),
            module_index=interaction_node.module_index,
            lesson_index=interaction_node.lesson_index,
            parent_node_id=interaction_node.id,
            remediation_hop=1,
            metadata=json.dumps({"for_interaction": interaction_node.id})
        )
        db.add(node)
        return node
    
    async def _create_concepts(
        self,
        db: AsyncSession,
        course: GraphCourse,
        curriculum: CurriculumStructure,
        lessons: List[LessonContent]
    ) -> int:
        """Extract and create concept entries for the course"""
        concepts_created = 0
        seen_concepts: set = set()
        
        # Extract concepts from learning outcomes
        for module in curriculum.modules:
            for outcome in module.learning_outcomes:
                concept_name = self._extract_concept_name(outcome)
                if concept_name and concept_name not in seen_concepts:
                    concept = Concept(
                        id=str(uuid4()),
                        name=concept_name,
                        description=outcome,
                        course_id=course.id,
                        difficulty_weight=1.0
                    )
                    db.add(concept)
                    seen_concepts.add(concept_name)
                    concepts_created += 1
        
        return concepts_created
    
    async def _count_edges(self, db: AsyncSession, course_id: str) -> int:
        """Count edges for the course"""
        result = await db.execute(
            select(LearningEdge)
            .join(LearningNode, LearningEdge.source_node_id == LearningNode.id)
            .where(LearningNode.course_id == course_id)
        )
        return len(result.scalars().all())
    
    # Helper methods
    
    def _next_sequence(self) -> int:
        """Get next sequence number"""
        self._node_sequence += 1
        return self._node_sequence
    
    def _estimate_duration(self, text: str, words_per_minute: int = 150) -> int:
        """Estimate speaking duration for text"""
        words = len(text.split())
        minutes = words / words_per_minute
        return max(10, int(minutes * 60))  # Minimum 10 seconds
    
    def _find_lesson_content(
        self,
        lesson_outline: LessonOutline,
        lesson_lookup: Dict[str, LessonContent]
    ) -> Optional[LessonContent]:
        """Find matching lesson content by various ID formats"""
        # Try direct match
        if lesson_outline.id in lesson_lookup:
            return lesson_lookup[lesson_outline.id]
        
        # Try variations
        variations = [
            lesson_outline.id.replace("les_", "mod"),
            lesson_outline.id.replace("_", ""),
            f"mod{lesson_outline.id.split('_')[1]}_les{lesson_outline.id.split('_')[2]}"
        ]
        
        for var in variations:
            if var in lesson_lookup:
                return lesson_lookup[var]
        
        return None
    
    def _extract_subject(self, curriculum: CurriculumStructure) -> str:
        """Extract subject from curriculum"""
        # Simple extraction from title
        title_lower = curriculum.course_title.lower()
        subjects = ["python", "javascript", "math", "science", "history", "english"]
        for subj in subjects:
            if subj in title_lower:
                return subj.capitalize()
        return "General"
    
    def _map_difficulty(self, curriculum: CurriculumStructure) -> str:
        """Map curriculum to difficulty string"""
        # Would need to access the original intent
        return "intermediate"
    
    def _extract_prerequisites(self, curriculum: CurriculumStructure) -> List[str]:
        """Extract prerequisites from modules"""
        prereqs = set()
        for module in curriculum.modules:
            for prereq in module.prerequisites:
                prereqs.add(prereq)
        return list(prereqs)
    
    def _extract_objectives(self, curriculum: CurriculumStructure) -> List[str]:
        """Extract learning objectives from all modules"""
        objectives = []
        for module in curriculum.modules:
            objectives.extend(module.learning_outcomes)
        return objectives[:10]  # Limit to 10
    
    def _extract_tags(self, curriculum: CurriculumStructure) -> List[str]:
        """Extract tags from curriculum"""
        # Simple extraction from title words
        words = curriculum.course_title.split()
        return [w.lower() for w in words if len(w) > 3][:5]
    
    def _format_takeaways(self, takeaways: List[str]) -> str:
        """Format takeaways into a narration script"""
        script = "Let's recap what you've learned... "
        for i, takeaway in enumerate(takeaways[:5], 1):
            script += f"Number {i}: {takeaway}. "
        script += "Great job making it through!"
        return script
    
    def _generate_code_explanation(self, block: CodeBlock) -> str:
        """Generate narration for code block"""
        script = f"Let's look at some {block.language} code. "
        if block.explanation:
            script += block.explanation
        else:
            script += f"This code demonstrates {block.title}. Take a moment to read through it."
        return script
    
    async def _generate_narration_script(
        self,
        content: str,
        title: str
    ) -> str:
        """Generate TTS-friendly narration script from content"""
        if not self.config.synthesize_missing_scripts:
            return content
        
        try:
            # Use AI to convert to spoken script
            prompt = self.SCRIPT_GENERATION_PROMPT.format(
                content=content[:1000],
                target_duration=int(self.config.target_node_duration_minutes * 60)
            )
            
            response = await self.ai_manager.generate_with_fallback(
                prompt=prompt,
                max_tokens=500,
                temperature=0.7
            )
            
            return response.get("content", content)
            
        except Exception as e:
            logger.warning(f"Script generation failed: {e}")
            return content
    
    async def _generate_hook_script(
        self,
        topic: str,
        description: str
    ) -> str:
        """Generate an engaging hook script"""
        try:
            prompt = self.HOOK_GENERATION_PROMPT.format(
                topic=f"{topic}: {description}",
                duration=20
            )
            
            response = await self.ai_manager.generate_with_fallback(
                prompt=prompt,
                max_tokens=200,
                temperature=0.8
            )
            
            return response.get("content", f"Welcome to {topic}! This is going to be exciting.")
            
        except Exception as e:
            logger.warning(f"Hook generation failed: {e}")
            return f"Welcome to {topic}! Let's dive in and explore {description}."
    
    def _generate_summary_script(
        self,
        title: str,
        outcomes: List[str]
    ) -> str:
        """Generate summary narration script"""
        script = f"Congratulations on completing {title}! "
        script += "You've learned: "
        for outcome in outcomes[:3]:
            script += f"{outcome}. "
        script += "Amazing progress! Let's keep going."
        return script
    
    def _generate_quick_check(
        self,
        context_node: LearningNode,
        assessments: Optional[CourseAssessments]
    ) -> Optional[Dict[str, Any]]:
        """Generate a quick check question"""
        # For now, generate a simple true/false question
        topic = context_node.title
        return {
            "type": "true_false",
            "question": f"You've just learned about {topic}. Do you feel confident with this concept?",
            "correct_answer": "true",
            "explanation": "Great! If you're not sure, we can review together.",
            "is_self_assessment": True
        }
    
    def _generate_remediation_script(
        self,
        title: str,
        interaction_data: Dict[str, Any]
    ) -> str:
        """Generate remediation narration"""
        script = f"No worries! Let's take another look at {title}. "
        if "hints" in interaction_data:
            hints = interaction_data["hints"]
            if hints:
                script += f"Here's a helpful hint: {hints[0]}. "
        script += "Take your time, and try again when you're ready."
        return script
    
    def _extract_concept_name(self, outcome: str) -> Optional[str]:
        """Extract a concept name from a learning outcome"""
        # Simple extraction - take first key noun phrase
        words = outcome.split()
        if len(words) >= 3:
            return " ".join(words[:3])
        return None


# Factory function
def create_graph_generator(
    config: Optional[GraphGenerationConfig] = None
) -> GraphCourseGenerator:
    """Create a GraphCourseGenerator with optional custom config"""
    return GraphCourseGenerator(config=config)
