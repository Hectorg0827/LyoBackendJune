import asyncio
from lyo_app.ai_classroom.conversation_flow import _ai_chat_handler

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

async def run_all():
    await test_chat_persona()

if __name__ == "__main__":
    asyncio.run(run_all())
