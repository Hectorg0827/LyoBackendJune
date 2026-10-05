# Voice delivery on canonical Chat

Voice uses the same Chat interaction contract, teaching policy, account history,
planner, memory and model routing as text. `DeliveryMode.VOICE` controls spoken
formatting. Client delivery capability controls which SSE text events are sent;
it never selects a second AI workflow.

## Client capability

Send `voice_session` on a Chat request, or continue using
`state_summary.voice_session`. Explicit top-level metadata takes precedence.
Both forms support `active`, `transport`, `locale`, `turn_id`,
`interrupted_previous_turn`, `hands_free`, and `delivery`.

| `delivery` | Text delivery | Client requirement |
| --- | --- | --- |
| `answer` (default) | One canonical answer through the existing answer/clarification events | Existing clients remain compatible |
| `ready` | `voice_ready` before blocks and the independently owned persistence write finish | Handle readiness and suppress final answer speech when `speak` is false |
| `segments` | Ordered `voice_text_segment` events during eligible model generation, followed by final readiness/answer | Queue segments once, handle incomplete outcomes, and suppress final answer speech |

Do not opt in until the client handles the corresponding event types. Some
legacy clients treat any top-level `text` field as another answer, so readiness
and segments must both be gated. An active session without `delivery` receives
only the existing answer path.

```json
{
  "text": "Explain why roots matter",
  "conversation_id": "server-conversation-id",
  "client_message_id": "unique-user-turn-id",
  "voice_session": {
    "active": true,
    "transport": "client_stt_tts",
    "delivery": "segments",
    "interrupted_previous_turn": false
  }
}
```

## Playback and replay

Use the server's `message_id` as the assistant turn identity. For segments,
queue each `(message_id, sequence)` once, in sequence order; append to TTS rather
than replacing an utterance already playing. A final readiness/answer with
`speak: false` updates the screen and completes the turn without speaking the
whole answer again. For `ready`, speak readiness once and use the final answer
for rendering only. The default `answer` path speaks its canonical answer once.

An authenticated retry with the same `client_message_id` replays the same
assistant identity with `replayed: true`. Clients must retain playback identity
long enough to avoid automatically speaking an already delivered replay.
`turn_id` is descriptive client metadata; it does not authorize a conversation
or replace server ownership and client-message deduplication.

## Interruption and incomplete output

On barge-in, stop queued/local TTS and abort the old SSE request. The backend
cancels and joins its owned executor and closes the provider stream. Send the
new transcript through Chat with `interrupted_previous_turn: true`; the existing
interaction contract follows the new request without restarting the old answer.

Providers can fall back before emitting text. After visible text, provider
failure or truncation produces `generation_status: "incomplete"` and a
`voice_incomplete` event. It never advertises completed readiness or starts a
second provider from the beginning. Reaching the requested token limit marks
the answer incomplete without marking the healthy provider unavailable.
Incomplete history retains its status on
reload and replay, and is excluded from successful assistant context.

Completed answers schedule an idempotent write with an independent DB session
before delivery; stream closure cannot cancel that write. Lesson writes retain
unredacted grading blocks. Writes are bounded and failures are logged; this is
not a durable job queue or a guarantee against process/database failure.

Usage events capture observed provider tokens on completion, failure and
cancellation. `usage_reported: false` means token usage was unavailable, rather
than a provider reporting zero billable tokens.

## Validation boundary

Regression tests cover canonical text, ordering, identifiers, capability gating,
replay, persistence, provider fallback, usage and ASGI disconnects. Device TTS,
audio queues, production network barge-in, and time to first audible speech still
require client/device testing before claiming an audio latency improvement.
