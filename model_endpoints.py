"""
Add model information endpoint to the FastAPI server
"""

from fastapi import APIRouter
from lyo_app.models.loading import tutor_model

router = APIRouter(prefix="/api/v1", tags=["AI Model"])

@router.get("/model/info")
async def model_info():
    """Get information about the loaded AI model"""
    try:
        # Ensure model is loaded
        tutor_model.load()
        info = tutor_model.info()
        
        return {
            "status": "success",
            "model_info": info,
            "capabilities": {
                "course_generation": True,
                "tutoring_hints": True,
                "structured_output": True,
                "multi_level_support": True,
                "socratic_questioning": True,
            },
            "supported_modes": ["explanation", "hint", "reflection"],
            "supported_levels": ["beginner", "intermediate", "advanced"],
            "performance": {
                "quantization": "4-bit" if not info.get("base_model", "").startswith("mock") else "mock",
                "memory_efficient": True,
                "inference_speed": "fast"
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "model_info": {
                "loaded": False,
                "error_details": "Model failed to load"
            }
        }

@router.post("/model/generate-tutor-response")
async def generate_tutor_response_endpoint(request_data: dict):
    """Generate a structured tutor response"""
    try:
        from lyo_app.models.loading import generate_tutor_response
        
        system_goal = request_data.get("system_goal", "Help the student learn")
        student_input = request_data.get("student_input", "")
        level = request_data.get("level", "beginner")
        mode = request_data.get("mode", "explanation")
        hint_level = request_data.get("hint_level")
        
        result = generate_tutor_response(
            system_goal=system_goal,
            student_input=student_input,
            level=level,
            mode=mode,
            hint_level=hint_level,
            max_new_tokens=request_data.get("max_new_tokens", 200)
        )
        
        return {
            "status": "success",
            "tutor_response": {
                "response": result.response,
                "reasoning": result.reasoning,
                "next_hint": result.next_hint,
                "meta": result.meta,
                "raw_output": result.raw[:200] + "..." if len(result.raw) > 200 else result.raw
            },
            "request_info": {
                "system_goal": system_goal,
                "level": level,
                "mode": mode,
                "hint_level": hint_level
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "tutor_response": None
        }
