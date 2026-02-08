import logging
import json
import asyncio
from typing import List, Dict, Any
from lyo_app.ai.router import MultimodalRouter
from lyo_app.ai.planner import LyoPlanner
from lyo_app.ai.schemas.lyo2 import RouterRequest, ActiveArtifactContext, MediaRef

logger = logging.getLogger(__name__)

class LyoEvaluator:
    """
    Automated evaluation engine for Lyo 2.0.
    """
    
    def __init__(self):
        self.router = MultimodalRouter()
        self.planner = LyoPlanner()

    async def run_evaluation(self, golden_set_path: str) -> Dict[str, Any]:
        """
        Runs evaluation on a golden set file.
        """
        with open(golden_set_path, "r") as f:
            scenarios = json.load(f)
            
        results = {
            "total": len(scenarios),
            "passed": 0,
            "failed": 0,
            "details": []
        }
        
        for scenario in scenarios:
            logger.info(f"Evaluating scenario {scenario['id']}: {scenario['description']}")
            
            # 1. Prepare Request
            req_data = scenario["request"]
            request = RouterRequest(
                user_id="test_user",
                text=req_data.get("text"),
                active_artifact=ActiveArtifactContext(**req_data["active_artifact"]) if "active_artifact" in req_data else None,
                media=[MediaRef(**m) for m in req_data.get("media", [])]
            )
            
            # 2. Run Router
            router_res = await self.router.route(request)
            decision = router_res.decision
            
            # 3. Run Planner
            plan = await self.planner.plan(request, decision)
            
            # 4. Compare with Expected
            expected = scenario["expected"]
            errors = []
            
            if decision.intent != expected["intent"]:
                errors.append(f"Intent mismatch: expected {expected['intent']}, got {decision.intent}")
                
            actual_actions = [step.action_type for step in plan.steps]
            for exp_action in expected["planning_steps"]:
                if exp_action not in actual_actions:
                    errors.append(f"Missing action: {exp_action}")
            
            success = len(errors) == 0
            if success:
                results["passed"] += 1
            else:
                results["failed"] += 1
                
            results["details"].append({
                "id": scenario["id"],
                "success": success,
                "errors": errors,
                "actual_intent": decision.intent,
                "actual_actions": actual_actions
            })
            
        return results

if __name__ == "__main__":
    evaluator = LyoEvaluator()
    # To run locally: asyncio.run(evaluator.run_evaluation("lyo_app/ai/golden_set.json"))
