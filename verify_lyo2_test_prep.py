import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from lyo_app.ai.schemas.lyo2 import RouterRequest
from lyo_app.ai.router import MultimodalRouter
from lyo_app.api.v1.stream_lyo2 import test_prep_agent

logging.basicConfig(level=logging.INFO)

async def test_prep_flow():
    router = MultimodalRouter()
    
    print("\n\n--- TEST 1: Should ask for clarification ---")
    req1 = RouterRequest(
        user_id="test_user",
        text="I have a test next friday",
        state_summary={},
        conversation_history=[],
        media=[]
    )
    decision1 = await router.route(req1)
    print("Routing Intent:", decision1.decision.intent.value)
    
    if decision1.decision.intent.value == "TEST_PREP":
        print("Intercepting via new TestPrepAgent...")
        result = await test_prep_agent.analyze_test_prep(req1)
        if result.success and result.data:
            print("Extracted Data:", result.data.model_dump())
            if result.data.missing_critical_info:
                print("Missing Info:", result.data.missing_critical_info)
                print("Clarification Question:", result.data.follow_up_question)
        else:
            print("Failed extraction:", result.error)
            
    print("\n\n--- TEST 2: Should have enough info ---")
    req2 = RouterRequest(
        user_id="test_user",
        text="I have a Biology test next friday covering cell structure and mitochondria.",
        state_summary={},
        conversation_history=[],
        media=[]
    )
    decision2 = await router.route(req2)
    print("Routing Intent:", decision2.decision.intent.value)
    
    if decision2.decision.intent.value == "TEST_PREP":
        print("Intercepting via new TestPrepAgent...")
        result2 = await test_prep_agent.analyze_test_prep(req2)
        if result2.success and result2.data:
            print("Extracted Data:", result2.data.model_dump())
            if result2.data.missing_critical_info:
                print("Missing Info:", result2.data.missing_critical_info)
            else:
                print("All good, ready for planner!")
        else:
            print("Failed extraction:", result2.error)

    print("\n\n--- TEST 3: Uploaded Media (Base64) ---")
    mock_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    uri = f"data:image/png;base64,{mock_b64}"
    
    from lyo_app.ai.schemas.lyo2 import MediaRef, InputModality
    req3 = RouterRequest(
        user_id="test_user",
        text="I have a test next friday. Here are my notes.",
        state_summary={},
        conversation_history=[],
        media=[MediaRef(modality=InputModality.IMAGE, uri=uri)]
    )
    decision3 = await router.route(req3)
    print("Routing Intent:", decision3.decision.intent.value)
    
    if decision3.decision.intent.value == "TEST_PREP":
        print("Intercepting via new TestPrepAgent...")
        result3 = await test_prep_agent.analyze_test_prep(req3)
        if result3.success and result3.data:
            print("Extracted Data:", result3.data.model_dump())
            if result3.data.missing_critical_info:
                print("Missing Info:", result3.data.missing_critical_info)
                print("Clarification Question:", result3.data.follow_up_question)
            else:
                print("All good, ready for planner!")
        else:
            print("Failed extraction:", result3.error)

if __name__ == "__main__":
    asyncio.run(test_prep_flow())
