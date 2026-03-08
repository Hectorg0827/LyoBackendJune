import uuid
import asyncio
import json
from typing import Dict, Any, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from lyo_app.auth.dependencies import get_current_user_or_guest
from lyo_app.cache.job_store import get_job_store
from lyo_app.api.v2.courses import _generate_module_content, _build_fallback_module, TIMEOUT_MODULE_GENERATION
from lyo_app.core.ai_resilience import ai_resilience_manager

# Let's import the full course truth fetcher
from lyo_app.api.v2.courses import get_course_result

router = APIRouter()
job_store = get_job_store()

class GenerateRequest(BaseModel):
    topic: str
    user_level: str = "beginner"


@router.post("/course/generate")
async def start_course_generation(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    user = Depends(get_current_user_or_guest)
):
    job_id = f"prog_{uuid.uuid4().hex[:8]}"
    course_id = f"c_{uuid.uuid4().hex[:8]}"
    
    # Phase A: Single fast AI call for syllabus + preview (< 3 sec)
    instant = await generate_instant_payload(req.topic, req.user_level)
    
    # Store job metadata in internal DB
    job_store[job_id] = {
        "job_id": job_id,
        "course_id": course_id,
        "user_id": user.id,
        "status": "generating",
        "modules_total": len(instant.get("syllabus", [])),
        "topic": req.topic,
        "user_level": req.user_level,
        "syllabus": instant.get("syllabus", []),
        "results": {},
        "modules_status": [
            {"index": idx, "state": "locked", "title": title}
            for idx, title in enumerate(instant.get("syllabus", []), start=1)
        ]
    }
    
    job_store.save(job_id, job_store[job_id])
    
    # Kick off full generation as background task
    background_tasks.add_task(
        generate_modules_progressively,
        job_id=job_id,
        course_id=course_id,
        topic=req.topic,
        level=req.user_level,
        syllabus=instant["syllabus"],
        user_id=user.id
    )
    
    return {
        "job_id": job_id,
        "schema_version": "1.0",
        "instant": {
            "course_id": course_id,
            "title": instant["title"],
            "objective": instant["objective"],
            "level": req.user_level,
            "syllabus": instant["syllabus"],
            "module_preview": instant.get("module_preview")
        }
    }


async def generate_instant_payload(topic: str, level: str) -> dict:
    """
    Fast AI call (<3 sec) — uses Gemini Flash to produce a real, topic-specific
    course syllabus and structured preview.  Falls back to deterministic titles
    only if AI is unavailable so delivery is always guaranteed.
    """
    # --- AI path (primary) ---
    try:
        if not ai_resilience_manager.session:
            await ai_resilience_manager.initialize()

        system_prompt = (
            "You are an expert curriculum designer. "
            "Given a topic and learner level, respond ONLY with valid JSON — no markdown fences, no extra text. "
            "Schema: "
            '{"title": string, "objective": string, "syllabus": [string x8], '
            '"module_preview": {"module_index": 1, "module_title": string, '
            '"lesson_preview": {"title": string, "summary": string, "mini_practice": [string x2]}}}'
            "\nRules: syllabus must have EXACTLY 8 specific, pedagogically-ordered module titles "
            "that are directly relevant to the topic (not generic like 'Core Concepts'). "
            "Each title should be a specific concept the learner will master."
        )
        user_prompt = f"Topic: {topic}\nLevel: {level}"

        ai_response = await asyncio.wait_for(
            ai_resilience_manager.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=600,
                provider_order=["gemini-2.0-flash", "gpt-4o-mini"],
            ),
            timeout=5.0,
        )

        raw = ai_response.get("content", "")
        # Strip markdown fences if present
        if "```" in raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            raw = raw[start:end] if start != -1 and end > start else raw

        payload = json.loads(raw)

        # Validate required fields
        syllabus = payload.get("syllabus", [])
        if not isinstance(syllabus, list) or len(syllabus) < 4:
            raise ValueError("Invalid syllabus from AI")

        print(f"✅ AI instant payload generated for '{topic}': {len(syllabus)} modules")
        return payload

    except Exception as e:
        print(f"⚠️  AI instant payload failed ({e}), using deterministic fallback")

    # --- Deterministic fallback (backup) ---
    topic_cap = topic.title()
    syllabus = [
        f"What is {topic_cap}? A First Look",
        f"Core Terminology and Key Concepts",
        f"How {topic_cap} Works Under the Hood",
        f"Practical {topic_cap}: Real-World Examples",
        f"Common Patterns and Best Practices",
        f"Troubleshooting and Avoiding Mistakes",
        f"Advanced {topic_cap} Techniques",
        f"Putting It All Together: {topic_cap} Mastery",
    ]

    return {
        "title": f"Complete Guide to {topic_cap}",
        "objective": f"Master {topic} from foundational principles to advanced real-world application.",
        "syllabus": syllabus,
        "module_preview": {
            "module_index": 1,
            "module_title": syllabus[0],
            "lesson_preview": {
                "title": "Welcome & What You'll Learn",
                "summary": f"A fast-paced introduction to {topic}: what it is, why it matters, and where we're headed.",
                "mini_practice": [
                    f"In one sentence, what do you already know about {topic}?",
                    "What specific outcome do you want from this course?"
                ]
            }
        }
    }


async def generate_modules_progressively(job_id: str, course_id: str, topic: str, level: str, syllabus: List[str], user_id):
    """Background worker — generates modules one at a time, updates status after each"""
    job = job_store.get(job_id)
    if not job:
        print(f"🚨 Job {job_id} missing immediately.")
        return

    # Create dummy outline for existing orchestrator calls
    outline = {
        "title": f"{topic} Course",
        "description": "Progresssive Course",
        "modules": [{"id": f"prog_m_{idx}", "title": t, "description": "Module"} for idx, t in enumerate(syllabus, 1)]
    }

    results = []
    modules_status = job.get("modules_status", [])

    for idx, module_title in enumerate(syllabus, start=1):
        try:
            modules_status[idx-1]["state"] = "building"
            job["modules_status"] = modules_status
            job_store.save(job_id, job)
            
            # Use the robust resilient module builder from v2 courses
            mod_outline = outline["modules"][idx-1]
            try:
                module_content = await asyncio.wait_for(
                    _generate_module_content(
                        topic=topic,
                        outline=outline,
                        module_outline=mod_outline
                    ),
                    timeout=TIMEOUT_MODULE_GENERATION
                )
            except Exception:
                module_content = _build_fallback_module(mod_outline, topic, {"level": level})
            
            # Inject required struct fields for progressive UI
            module_content["index"] = idx
            module_content["state"] = "ready"
            # iOS ProgressiveModule uses "summary" — backend AI uses "description"
            # Ensure both keys exist so either iOS version can decode it
            if "summary" not in module_content or not module_content.get("summary"):
                module_content["summary"] = module_content.get("description", "")
            # Normalize each lesson: iOS ProgressiveLesson uses "summary" for the short desc
            for lesson in module_content.get("lessons", []):
                if "summary" not in lesson or not lesson.get("summary"):
                    lesson["summary"] = lesson.get("content", "")[:200]  # first 200 chars as preview
            
            # Store completed module
            job.setdefault("results", {})[str(idx)] = module_content
            modules_status[idx-1]["state"] = "ready"
            job["modules_status"] = modules_status
            job_store.save(job_id, job)
            results.append(module_content)
            
        except Exception as e:
            print(f"🚨 Module {idx} failed: {e}")
            modules_status[idx-1]["state"] = "failed"
            job["modules_status"] = modules_status
            job_store.save(job_id, job)
    
    # Mark job complete
    job["status"] = "complete"
    
    # Store full results so Final Truth endpoint works
    job["result"] = {
        "id": course_id,
        "title": job["topic"],
        "modules": results,
        "schema_version": "1.0"
    }
    job_store.save(job_id, job)


@router.get("/course/generate/status")
async def check_generation_status(
    job_id: str,
    user = Depends(get_current_user_or_guest)
):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    modules_status = job.get("modules_status", [])
    ready_count = sum(1 for m in modules_status if m.get("state") == "ready")
    total = job.get("modules_total", 0)
    
    eta = max(0, (total - ready_count) * 20)
    
    return {
        "state": job.get("status", "failed"),
        "progress": ready_count / total if total > 0 else 0,
        "modules": modules_status,
        "course_id": job.get("course_id"),
        "schema_version": "1.0",
        "eta_seconds": eta
    }


@router.get("/course/{course_id}/module/{module_index}")
async def get_module(
    course_id: str,
    module_index: int,
    user = Depends(get_current_user_or_guest)
):
    # Find job by course_id
    all_jobs = job_store.get_all() if hasattr(job_store, 'get_all') else job_store.store.values()
    job = next((j for j in all_jobs if isinstance(j, dict) and j.get("course_id") == course_id), None)
    
    if not job:
        raise HTTPException(status_code=404, detail="Course not found")
        
    module = job.get("results", {}).get(str(module_index))
    if not module:
        raise HTTPException(status_code=404, detail="Module not found or not ready")

    # Ensure iOS-compatible field names on every response
    if "summary" not in module or not module.get("summary"):
        module["summary"] = module.get("description", "")
    for lesson in module.get("lessons", []):
        if "summary" not in lesson or not lesson.get("summary"):
            lesson["summary"] = lesson.get("content", "")[:200]
    
    return module


@router.get("/course/{course_id}")
async def get_full_course(
    course_id: str,
    user = Depends(get_current_user_or_guest)
):
    """The single source of truth. Always returns whatever exists."""
    all_jobs = job_store.get_all() if hasattr(job_store, 'get_all') else job_store.store.values()
    job = next((j for j in all_jobs if isinstance(j, dict) and j.get("course_id") == course_id), None)
    
    if not job:
        raise HTTPException(status_code=404, detail="Course not found")
    
    if "result" not in job:
        raise HTTPException(status_code=404, detail="Course not finished generating")
        
    return job["result"]
