
import asyncio
import json
import logging
from unittest.mock import MagicMock, AsyncMock, patch
from lyo_app.services.audio_manager import ActiveAudioSession, audio_manager
from lyo_app.feeds.addictive_algorithm import UserProfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_phase5_backend():
    print("🚀 Verifying Phase 5 Backend: Interactive Learning Loop")
    
    # 1. Mock WebSocket and Session
    mock_ws = AsyncMock()
    session_id = "123" # Mock DB ID
    
    # 2. Mock DB and Profile
    mock_profile = UserProfile(
        attention_span_seconds=30.0,
        preferred_content_types=["video"],
        peak_engagement_hours=[20],
        dopamine_response_pattern="quick_hits",
        addiction_level=0.8,
        binge_watching_tendency=0.9,
        curiosity_triggers=["shocking"],
        emotional_state="excited"
    )
    
    mock_session_obj = MagicMock()
    mock_session_obj.user_id = 1
    mock_session_obj.user.name = "Test User"
    
    # 3. Patch dependencies
    with patch("lyo_app.services.audio_manager.AsyncSessionLocal") as mock_db_factory, \
         patch("lyo_app.services.audio_manager.addictive_feed_algorithm._get_user_profile", return_value=mock_profile), \
         patch("lyo_app.services.audio_manager.highlight_service.generate_mastery_highlight", AsyncMock()) as mock_highlight:
        
        # Setup DB mock
        mock_db = AsyncMock()
        mock_db_factory.return_value.__aenter__.return_value = mock_db
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_obj
        mock_db.execute.return_value = mock_result
        
        # 4. Test Session Initialization
        session = ActiveAudioSession(session_id, mock_ws, audio_manager)
        await session.start()
        
        print(f"✅ Personalization loaded. History length: {len(session.history)}")
        assert "quick_hits" in session.history[0]["content"]
        assert session.user_id == 1
        
        # 5. Verify session_start widget push
        mock_ws.send_text.assert_called()
        last_call = mock_ws.send_text.call_args_list[0][0][0]
        start_widget = json.loads(last_call)
        assert start_widget["component"] == "session_start"
        print("✅ session_start widget pushed successfully.")
        
        # 6. Verify Widget Trigger extraction
        ai_response = "I have a surprise for you! [[WIDGET: quick_fact, {\"text\": \"The Eiffel Tower can be 15 cm taller during the summer.\"}]]. What do you think?"
        session._handle_widget_triggers(ai_response)
        
        # Wait a bit for the async task to trigger
        await asyncio.sleep(0.1)
        
        # Find the widget push call
        widget_pushed = False
        for call in mock_ws.send_text.call_args_list:
            msg = json.loads(call[0][0])
            if msg.get("component") == "quick_fact":
                widget_pushed = True
                assert "Eiffel Tower" in msg["data"]["text"]
                break
        
        assert widget_pushed
        print("✅ Widget trigger extracted and pushed successfully.")
        
        # 7. Add messages to history to meet 'len(self.history) > 3' requirement
        session.history.append({"role": "user", "content": "What is the capital of France?"})
        session.history.append({"role": "assistant", "content": "The capital of France is Paris."})
        session.history.append({"role": "user", "content": "Interesting!"})
        
        # 8. Test Session Stop & Highlight Trigger
        await session.stop()
        # Give a small delay for the background task to start
        await asyncio.sleep(0.5)
        mock_highlight.assert_called_once()
        print("✅ HighlightService triggered on session stop.")

    print("\n✨ Phase 5 Backend Verification Complete!")

if __name__ == "__main__":
    asyncio.run(verify_phase5_backend())
