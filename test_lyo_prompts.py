import asyncio
from lyo_app.ai_classroom.conversation_flow import _ai_chat_handler
from lyo_app.ai_classroom.scene_lifecycle_engine import SceneLifecycleEngine
from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.ai_agents.multi_agent_v2.agents.tutor_agent import TutorAgent

async def test_chat_persona():
    print("--- TESTING CHAT LOBBY PERSONA ---")
    messages = [
        {"role": "user", "content": "Can you explain limits to me?"}
    ]
    response = await _ai_chat_handler(message="Can you explain limits to me?", context=[])
    print(f"USER: Can you explain limits to me?")
    print(f"LYO: {response}\n")

    response2 = await _ai_chat_handler(message="Hello Hector! It's been a while.", context=[])
    print(f"USER: Hello Hector! It's been a while.")
    print(f"LYO: {response2}\n")

async def test_classroom_director():
    print("--- TESTING CLASSROOM DIRECTOR ---")
    
    # We can mock the context snapshot
    class MockContext:
        topic = "Calculus limits"
        course_title = "Calculus 101"
        lesson_index = 0
        total_lessons = 5
        lesson_title = "Intro to Limits"
        user_id = "test_user"
        course_id = "test_course"
        knowledge_states = []
        preferred_difficulty = 0.5

    context = MockContext()
    
    from lyo_app.ai_classroom.director_prompt import CLASSROOM_DIRECTOR_PROMPT
    
    input_block = f"""
INPUT FORMAT:
subject: "{context.course_title}"
session_number: 1
user_name: "Learner"
user_memory: "Likes clear and concise explanations."
last_session_recap: ""
user_level: "developing"
"""
    prompt = CLASSROOM_DIRECTOR_PROMPT + "\n\n" + input_block
    
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    print("Calling LLM for Classroom Director Script (this takes 5-10 seconds)...")
    try:
        response = await ai_resilience_manager.chat_completion(
            messages=messages,
            temperature=0.4,
            max_tokens=2500,
            response_format={"type": "json_object"} if False else None
        )
        print("CLASSROOM SCRIPT JSON:")
        print(response.get("content") or response.get("response"))
    except Exception as e:
        print(f"Failed to generate classroom script: {e}")

async def run_all():
    await test_chat_persona()
    await test_classroom_director()

if __name__ == "__main__":
    asyncio.run(run_all())
