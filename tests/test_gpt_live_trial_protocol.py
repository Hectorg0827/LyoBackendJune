"""Contract tests against a fake GPT-Live provider. No paid network calls."""
import asyncio
import json

import pytest

from lyo_app.live_trial import routes


class FakePhone:
    def __init__(self):
        self.messages = []

    async def send_text(self, value):
        self.messages.append(json.loads(value))

    async def receive_text(self):
        # A real phone sends PCM continuously; the fake checks the provider
        # lifecycle without ever opening a microphone or a paid API socket.
        await asyncio.sleep(10)
        return '{"type":"end"}'


class FakeProvider:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def send(self, value):
        self.messages.append(json.loads(value))

    async def __aiter__(self):
        events = [
            {"type": "session.started", "session": {"id": "fake_1"}},
            {"type": "session.input_transcript.delta", "delta": "Explain fractions"},
            {
                "type": "session.delegation.created",
                "delegation": {"id": "fake_delegate", "target": "client"},
            },
            {"type": "session.output_audio.delta", "delta": "AAABAA=="},
            {"type": "session.output_transcript.delta", "delta": "Sure, let's try!"},
            {"type": "session.closed", "usage": {"seconds": 12}},
        ]
        for event in events:
            yield json.dumps(event)

@pytest.mark.asyncio
async def test_fake_provider_receives_no_paid_backend_delegation(monkeypatch):
    import websockets

    provider = FakeProvider()
    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: provider)
    phone = FakePhone()
    seconds = await routes._relay(phone, api_key="not-a-real-key")

    assert seconds == 12
    assert provider.closed is True
    start = provider.messages[0]
    assert start["type"] == "session.start"
    assert start["session"]["model"] == "gpt-live-1"
    assert start["session"]["audio"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert start["session"]["delegation"]["type"] == "client"
    assert start["session"]["store"] is False
    assert not any("responses" in json.dumps(event) for event in provider.messages)

    local_answer = provider.messages[1]
    assert local_answer["type"] == "session.commentary.append"
    assert local_answer["delegation_id"] == "fake_delegate"
    assert "fraction" in local_answer["content"].lower()

    assert phone.messages[0]["type"] == "ready"
    assert phone.messages[1]["role"] == "user"
    assert phone.messages[2] == {"type": "audio", "audio": "AAABAA=="}
    assert phone.messages[-1]["type"] == "ended"


@pytest.mark.asyncio
async def test_hard_cutoff_cancels_a_stuck_provider_without_waiting_for_audio():
    was_cancelled = False

    async def never_ending_provider():
        nonlocal was_cancelled
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            was_cancelled = True
            raise

    with pytest.raises(TimeoutError):
        await routes._with_wall_deadline(never_ending_provider(), seconds=0.01)
    assert was_cancelled is True


@pytest.mark.asyncio
async def test_input_is_restricted_to_audio_and_end(monkeypatch):
    """Client-supplied provider commands are never forwarded upstream."""
    import websockets

    class CommandPhone(FakePhone):
        def __init__(self):
            super().__init__()
            self.sent = False

        async def receive_text(self):
            if not self.sent:
                self.sent = True
                return json.dumps({
                    "type": "session.update",
                    "session": {"delegation": {"type": "responses"}},
                })
            return await super().receive_text()

    provider = FakeProvider()
    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: provider)
    await routes._relay(CommandPhone(), api_key="not-a-real-key")
    assert not any(event["type"] == "session.update" for event in provider.messages)
