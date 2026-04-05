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
    job_data = {
        "job_id": job_id,
        "course_id": course_id,
        "user_id": user.id,
        "status": "generating",
        "modules_total": len(instant.get("syllabus", [])),
        "topic": req.topic,
        "user_level": req.user_level,
        "title": instant.get("title", req.topic),
        "objective": instant.get("objective", ""),
        "syllabus": instant.get("syllabus", []),
        "results": {},
        "modules_status": [
            {"index": idx, "state": "locked", "title": title}
            for idx, title in enumerate(instant.get("syllabus", []), start=1)
        ]
    }
    job_store.save(job_id, job_data)
    # Store course_id → job_id alias for O(1) lookup
    job_store.save(f"course:{course_id}", {"job_id": job_id})
    
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
                provider_order=["gemini-2.5-flash", "gpt-4o-mini"],
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
            module_content = None
            max_retries = 4

            for attempt in range(1, max_retries + 1):
                try:
                    module_content = await asyncio.wait_for(
                        _generate_module_content(
                            topic=topic,
                            outline=outline,
                            module_outline=mod_outline
                        ),
                        timeout=TIMEOUT_MODULE_GENERATION
                    )
                    # Validate: AI must return actual lessons, not empty stubs
                    # A single-lesson module with generic "Overview" content is the
                    # internal fallback of _generate_module_content — treat it as failure
                    lessons = module_content.get("lessons", []) if module_content else []
                    if len(lessons) >= 2:
                        print(f"✅ Module {idx} generated via AI (attempt {attempt}): {len(lessons)} lessons")
                        break
                    else:
                        print(f"⚠️ Module {idx} AI returned insufficient lessons ({len(lessons)}) (attempt {attempt})")
                        module_content = None
                except asyncio.TimeoutError:
                    print(f"⚠️ Module {idx} AI timed out (attempt {attempt}/{max_retries})")
                    module_content = None
                except Exception as gen_err:
                    print(f"⚠️ Module {idx} AI error (attempt {attempt}/{max_retries}): {gen_err}")
                    module_content = None

                # Brief pause before retry (escalating)
                if attempt < max_retries:
                    await asyncio.sleep(2 + attempt)

            if not module_content:
                print(f"⚠️ Module {idx} all AI attempts failed — using fallback")
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
        "job_id": job_id,
        "title": job.get("title", job["topic"]),
        "objective": job.get("objective", ""),
        "syllabus": job.get("syllabus", []),
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
    # Find job by course_id (O(1) via alias key)
    job = job_store.find_by_course_id(course_id)
    
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
    job = job_store.find_by_course_id(course_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Course not found")
    
    if "result" not in job:
        raise HTTPException(status_code=404, detail="Course not finished generating")
        
    return job["result"]
