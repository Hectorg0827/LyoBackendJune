import asyncio

async def mock_stream(chunks):
    for c in chunks:
        yield c
        await asyncio.sleep(0.001)

class EventType:
    MESSAGE_DELTA = "message_delta"

class StreamEvent:
    def __init__(self, event, data):
        self.event = event
        self.data = data
    def __repr__(self):
        return f"{self.event}: {self.data}"
    def to_sse(self):
        return self

async def buffering_logic_test(stream_generator):
    full_response = ""
    buffer = ""
    is_decision_made = False
    is_json_mode = False
    chunk_index = 0
    events = []

    async for chunk in stream_generator:
        full_response += chunk
        
        if not is_decision_made:
            buffer += chunk
            stripped = buffer.lstrip()
            
            # Decision Logic: Check first ~5 meaningful chars
            if len(stripped) >= 5: 
                if stripped.startswith("{") or stripped.startswith("```"):
                    is_json_mode = True
                    is_decision_made = True
                elif len(stripped) >= 15 or (" " in stripped): 
                    is_decision_made = True
                    is_json_mode = False
                    chunk_index += 1
                    events.append(StreamEvent(EventType.MESSAGE_DELTA, {"content": buffer}).data["content"])
                    buffer = ""
        else:
            if not is_json_mode:
                chunk_index += 1
                events.append(StreamEvent(EventType.MESSAGE_DELTA, {"content": chunk}).data["content"])

    if not is_decision_made and buffer and not (buffer.strip().startswith("{") or buffer.strip().startswith("```")):
            chunk_index += 1
            events.append(StreamEvent(EventType.MESSAGE_DELTA, {"content": buffer}).data["content"])
            
    return events, is_json_mode

async def test():
    print("Test 1: Normal Text")
    stream1 = mock_stream(["Hello", " world", " this", " is", " text"])
    events, mode = await buffering_logic_test(stream1)
    print(f"Events: {events}, IsJson: {mode}")
    assert mode == False
    assert "".join(events) == "Hello world this is text"

    print("\nTest 2: JSON Response")
    stream2 = mock_stream(["{", "\n", '"type":', ' "OPEN_CLASSROOM"'])
    events, mode = await buffering_logic_test(stream2)
    print(f"Events: {events}, IsJson: {mode}")
    assert mode == True
    assert len(events) == 0 # Should be fully buffered

    print("\nTest 3: JSON Markdown")
    stream3 = mock_stream(["```json", "\n{...}"])
    events, mode = await buffering_logic_test(stream3)
    print(f"Events: {events}, IsJson: {mode}")
    assert mode == True
    assert len(events) == 0

    print("\nTest 4: Short Text")
    stream4 = mock_stream(["Hi"])
    events, mode = await buffering_logic_test(stream4)
    print(f"Events: {events}, IsJson: {mode}")
    assert mode == False
    assert len(events) == 1
    assert events[0] == "Hi"
    
    print("\nTest 5: Tricky Start (Whitespace)")
    stream5 = mock_stream(["   ", "Sure", ", here is..."])
    events, mode = await buffering_logic_test(stream5)
    print(f"Events: {events}, IsJson: {mode}")
    assert mode == False # Should detect text because of "Sure" even with spaces
    assert "".join(events) == "   Sure, here is..."

    print("\nALL TESTS PASSED")

if __name__ == "__main__":
    asyncio.run(test())
