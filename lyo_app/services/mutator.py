import logging
import json
from typing import Dict, Any, Optional
from lyo_app.services.artifact_service import ArtifactService
from lyo_app.ai_agents.multi_agent_v2.model_manager import ModelManager
from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

class FollowUpMutator:
    """
    Handles artifact mutations (updates).
    Takes an existing artifact and a modification instruction, 
    then generates a new version.
    """
    
    def __init__(self, model_manager: Optional[ModelManager] = None):
        self.artifacts = ArtifactService()
        self.model_manager = model_manager or ModelManager()

    async def mutate(self, artifact_id: str, instruction: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Applies a mutation to an artifact.
        """
        # 1. Fetch latest version of artifact
        current_artifact = await self.artifacts.get_artifact(artifact_id)
        if not current_artifact:
            raise ValueError(f"Artifact {artifact_id} not found")
            
        art_type = current_artifact.get("type")
        current_content = current_artifact.get("content")
        
        # 2. Build prompt for mutation
        prompt = self._build_mutation_prompt(art_type, current_content, instruction, user_context)
        
        # 3. Call AI to apply mutation
        # We use a higher-tier model for mutations to ensure precision
        response = await self.model_manager.generate_with_retry(
            prompt=prompt,
            model_name="gemini-2.5-flash",
            temperature=0.2 # Low temperature for structural updates
        )
        
        # 4. Parse new content
        try:
            # Look for JSON in response
            # (In a real implementation, we'd use structured output with Pydantic)
            start = response.find("{")
            end = response.rfind("}") + 1
            new_content = json.loads(response[start:end])
        except Exception as e:
            logger.error(f"Failed to parse mutated content: {e}")
            raise ValueError("Mutation failed: AI returned invalid JSON")
            
        # 5. Save new version
        metadata = current_artifact.get("metadata", {})
        metadata["last_instruction"] = instruction
        
        new_artifact = await self.artifacts.update_artifact(artifact_id, new_content, metadata)
        
        return new_artifact

    def _build_mutation_prompt(self, art_type: str, content: Dict[str, Any], instruction: str, context: Optional[Dict[str, Any]]) -> str:
        return f"""You are an expert content editor for Lyo 2.0.
Your task is to update an existing artifact of type '{art_type}' based on the user's instruction.

CURRENT CONTENT (JSON):
{json.dumps(content, indent=2)}

USER INSTRUCTION:
"{instruction}"

CONTEXT:
{json.dumps(context or {}, indent=2)}

OUTPUT RULES:
1. Return ONLY the updated JSON content.
2. Maintain the exact same schema.
3. Be surgical: apply the instruction precisely without changing other parts unless necessary.
4. If the instruction is "make it harder", increase the depth of the questions/content.
5. If the instruction is "too short", add more relevant sections.

UPDATED JSON:"""
