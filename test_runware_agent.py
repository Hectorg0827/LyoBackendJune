import asyncio
from lyo_app.chat.agents import CoursePlannerAgent

async def run():
    agent = CoursePlannerAgent()
    res = await agent.process("Make me a course on quantum mechanics")
    print("\n--- AGENT RESULT ---")
    print(res["course_data"])
    print("--------------------")

if __name__ == "__main__":
    asyncio.run(run())
