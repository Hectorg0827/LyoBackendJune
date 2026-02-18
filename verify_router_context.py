
import asyncio
import sys
import os
from unittest.mock import MagicMock, patch

# Add project root
sys.path.append(os.getcwd())

from lyo_app.chat.router import ChatRouter, ChatMode

async def test_router_context():
    print("🧠 Verifying Context-Aware Router...")
    
    # Mock AI Resilience
    with patch("lyo_app.chat.agents.ai_resilience_manager") as mock_ai:
        # 1. Setup Mock
        future = asyncio.Future()
        future.set_result({
            "content": '{"mode": "PRACTICE", "reasoning": "User asked for another one in quiz context"}', 
            "usage": {"total_tokens": 50},
            "model": "gpt-4o-mini"
        })
        mock_ai.chat_completion.return_value = future
        
        # 2. Initialize Router
        router = ChatRouter()
        
        # 3. Test Inputs
        message = "Give me another one"
        history = [
            {"role": "user", "content": "Quiz me on biology"},
            {"role": "assistant", "content": "Question 1: What is the powerhouse of the cell?"},
            {"role": "user", "content": "Mitochondria"},
            {"role": "assistant", "content": "Correct!"}
        ]
        context = {"learner_context": "Student is preparing for Biology Midterm"}
        
        # 4. Run Route
        print("   - Calling router.route() with context & history...")
        # Force semantic routing by using a message that fails regex (no "quiz", "test", etc explicitly)
        # "Give me another one" might match some generic patterns, so we explicitly check _semantic_route logic
        
        # We'll call _semantic_route directly to verify prompt construction
        mode, reasoning = await router._semantic_route(message, history, context)
        
        # 5. Verify Prompt Construction
        print("   - Verifying LLM Prompt...")
        call_args = mock_ai.chat_completion.call_args
        if not call_args:
            print("❌ LLM was not called")
            return

        messages_sent = call_args.kwargs["messages"]
        
        # Check System Prompt
        if "Intent Router" not in messages_sent[0]["content"]:
            print("❌ System prompt missing")
            return
            
        # Check Learner Context Injection
        context_msg = next((m for m in messages_sent if "Learner Context" in m["content"]), None)
        if not context_msg or "Biology Midterm" not in context_msg["content"]:
            print("❌ Learner Context not injected correctly")
            return
        
        # Check History Injection (Full content)
        if "powerhouse of the cell" not in str(messages_sent):
            print("❌ Conversation history not injected")
            return
            
        # Check Mode Result
        if mode != ChatMode.PRACTICE:
            print(f"❌ Wrong mode returned: {mode}")
            return
            
        print("   ✅ Prompt constructed correctly with Context & History")
        print("   ✅ Router returned correct Semantic Mode")
        print("\n🎉 Router Logic Verified!")

if __name__ == "__main__":
    # Mock the import inside the method
    with patch.dict(sys.modules, {"lyo_app.core.ai_resilience": MagicMock()}):
        asyncio.run(test_router_context())
