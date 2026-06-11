"""Resilient test script for verifying the "I Have a Test" prep and study planner agent system."""
import asyncio
import json
from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.study_plans.routes import INTAKE_SYSTEM_PROMPT, PLANNER_SYSTEM_PROMPT, COACH_SYSTEM_PROMPT


async def test_intake_agent():
    print("\n--- 🧪 TESTING INTAKE AGENT ---")
    messages = [
        {"role": "system", "content": INTAKE_SYSTEM_PROMPT},
        {"role": "user", "content": "I have an AP Biology exam in 3 weeks, and I feel really stressed about it."}
    ]
    
    print("Sending message to Intake Agent...")
    res = await ai_resilience_manager.chat_completion(
        messages=messages,
        temperature=0.7,
        response_format={"type": "json_object"}
    )
    content = res.get("content", "{}")
    print("Intake Agent JSON Response:")
    print(json.dumps(json.loads(content), indent=2))


async def test_planner_agent():
    print("\n--- 🧪 TESTING PLANNER AGENT ---")
    test_profile = {
        "subject": "AP Biology",
        "test_date": "2026-06-15",
        "test_format": "multiple_choice",
        "baseline_confidence": 3,
        "daily_minutes_available": 45,
        "study_days_per_week": 5,
        "stress_level": 8,
        "topics": [
            {"name": "Cellular Energetics", "confidence": 2},
            {"name": "Gene Transmission", "confidence": 7},
            {"name": "Ecology & Evolution", "confidence": 5}
        ]
    }
    
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(test_profile)}
    ]
    
    print("Generating Personalized Study Plan from Profile...")
    res = await ai_resilience_manager.chat_completion(
        messages=messages,
        temperature=0.4,
        response_format={"type": "json_object"}
    )
    content = res.get("content", "{}")
    print("Planner Agent JSON Response:")
    print(json.dumps(json.loads(content), indent=2))


async def test_coach_agent():
    print("\n--- 🧪 TESTING DAILY COACH AGENT ---")
    coach_context = {
        "days_until_test": 12,
        "stress_level": 8,
        "daily_minutes": 45,
        "sessions": [
            {"id": "s1", "topic": "Cellular Energetics: Photosynthesis", "session_type": "learn", "status": "completed", "performance_score": 0.8},
            {"id": "s2", "topic": "Cellular Energetics: Cellular Respiration", "session_type": "learn", "status": "skipped", "performance_score": None},
            {"id": "s3", "topic": "Gene Transmission: Mitosis", "session_type": "practice", "status": "skipped", "performance_score": None},
            {"id": "s4", "topic": "Gene Transmission: Meiosis", "session_type": "learn", "status": "skipped", "performance_score": None}
        ]
    }
    
    messages = [
        {"role": "system", "content": COACH_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(coach_context)}
    ]
    
    print("Evaluating Pacing Context for Daily Coaching Action...")
    res = await ai_resilience_manager.chat_completion(
        messages=messages,
        temperature=0.3,
        response_format={"type": "json_object"}
    )
    content = res.get("content", "{}")
    print("Coach Agent JSON Response:")
    print(json.dumps(json.loads(content), indent=2))


async def run_all():
    await test_intake_agent()
    await test_planner_agent()
    await test_coach_agent()


if __name__ == "__main__":
    asyncio.run(run_all())
