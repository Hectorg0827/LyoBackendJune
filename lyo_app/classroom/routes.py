from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Any, Optional
import asyncio
import logging
import json

from .generator import ContentGenerator
from .schemas import LyoStreamChunk

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/classroom",
    tags=["classroom"]
)

# How long (seconds) to wait for a "continue" ack from the client before
# automatically advancing.  Prevents the lesson hanging forever if the iOS
# app never sends the acknowledgement (e.g. due to a network hiccup).
AUTO_ADVANCE_TIMEOUT = 120  # 2 minutes


async def _authenticate_lesson_ws(websocket: WebSocket) -> Optional[str]:
    """Authenticate a lesson WebSocket from its query parameters.

    The browser/iOS client connects with either ``?token=<jwt>`` (a logged-in
    user) or ``?api_key=lyo_sk_...`` (a provisioned guest/session key), matching
    the convention used by the other classroom WebSocket. Returns an opaque
    identity string on success, or ``None`` if authentication fails — callers
    must close the socket in that case so the AI generation budget can't be
    consumed anonymously.
    """
    token = websocket.query_params.get("token")
    api_key = websocket.query_params.get("api_key")

    # JWT (registered user)
    if token:
        try:
            from lyo_app.auth.jwt_auth import verify_token_async
            token_data = await verify_token_async(token, expected_type="access")
            if token_data and token_data.user_id:
                return f"user:{token_data.user_id}"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Lesson WS JWT auth failed: {e}")

    # API key (guest/session) — validated against the database, not trusted blindly.
    if api_key:
        try:
            from lyo_app.core.database import AsyncSessionLocal
            from lyo_app.auth.api_key_auth import validate_api_key
            async with AsyncSessionLocal() as db:
                key_obj = await validate_api_key(api_key, db)
                if key_obj:
                    return f"apikey:{getattr(key_obj, 'id', 'valid')}"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Lesson WS API-key auth failed: {e}")

    return None


@router.websocket("/ws/lesson/{topic}")
async def websocket_lesson_stream(websocket: WebSocket, topic: str):
    """
    Interactive WebSocket endpoint for the Lyo Classroom lesson.

    Auth: pass ?token=<jwt> or ?api_key=lyo_sk_... as a query parameter.

    Protocol:
      SERVER → CLIENT  { card: <card_data>, card_index: N, total_cards: 7 }
      CLIENT → SERVER  { "action_intent": "continue" }   (or any JSON with "action_intent")
      SERVER → CLIENT  { is_complete: true }   (after the last card is ack'd)

    The server sends ONE card at a time, then waits for the client to
    confirm before sending the next.  This keeps the WebSocket alive
    between slides and makes the "Continue" button actually meaningful.
    """
    # Authenticate BEFORE accepting so anonymous clients can't trigger
    # (paid) AI lesson generation. 4401 = application "Unauthorized".
    identity = await _authenticate_lesson_ws(websocket)
    if not identity:
        await websocket.close(code=4401)
        logger.info(f"[{topic}] Rejected unauthenticated lesson WS connection")
        return

    await websocket.accept()

    generator = ContentGenerator()

    # Pre-generate the full lesson so we know the total count upfront.
    # Each card is stored as a LyoStreamChunk.
    chunks: list[LyoStreamChunk] = []
    metadata_chunk: LyoStreamChunk | None = None

    try:
        async for chunk in generator.stream_lesson(topic):
            if chunk.metadata:
                metadata_chunk = chunk          # palette / topic metadata
            elif chunk.is_complete:
                pass                            # handled after loop
            else:
                chunks.append(chunk)            # actual card
    except Exception as e:
        logger.error(f"Error pre-generating lesson for '{topic}': {e}")
        try:
            await websocket.send_json({"error": str(e), "is_complete": True})
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
        return

    total_cards = len(chunks)

    # --- 1. Send lesson metadata first (palette, topic) ---
    if metadata_chunk:
        try:
            await websocket.send_json(
                metadata_chunk.model_dump(mode="json", exclude_none=True)
            )
        except Exception as e:
            logger.warning(f"Could not send metadata: {e}")

    # --- 2. Send cards one at a time, waiting for "continue" each time ---
    try:
        for index, chunk in enumerate(chunks):
            # Build the payload and enrich it with navigation context
            payload = chunk.model_dump(mode="json", exclude_none=True)
            payload["card_index"] = index
            payload["total_cards"] = total_cards
            payload["is_last_card"] = (index == total_cards - 1)

            # Send the card
            await websocket.send_json(payload)
            logger.info(
                f"[{topic}] Sent card {index + 1}/{total_cards}: "
                f"{chunk.card.type if chunk.card else 'unknown'}"
            )

            # Don't wait for ack on the last card — send the completion
            # signal immediately so the iOS app can show a "Finish" screen.
            if index == total_cards - 1:
                break

            # Wait for the client to send any message (typically
            # {"action_intent": "continue"}) before proceeding.
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=AUTO_ADVANCE_TIMEOUT,
                )
                client_msg = json.loads(raw)
                intent = client_msg.get("action_intent", "")
                logger.info(f"[{topic}] Received client intent: '{intent}' (card {index + 1})")
                # We accept any intent as a signal to continue (continue,
                # skip, hint, etc.).  Quiz-answer data is logged but ignored
                # for the purposes of card progression here.
            except asyncio.TimeoutError:
                logger.warning(
                    f"[{topic}] No client ack after {AUTO_ADVANCE_TIMEOUT}s "
                    f"— auto-advancing past card {index + 1}"
                )
            except WebSocketDisconnect:
                logger.info(f"[{topic}] Client disconnected at card {index + 1}")
                return
            except json.JSONDecodeError:
                logger.warning(f"[{topic}] Received non-JSON message — advancing anyway")

        # --- 3. Signal lesson completion ---
        await websocket.send_json({"is_complete": True, "total_cards": total_cards})
        logger.info(f"[{topic}] Lesson stream completed ({total_cards} cards)")

    except WebSocketDisconnect:
        logger.info(f"[{topic}] Client disconnected during lesson")
    except Exception as e:
        logger.error(f"[{topic}] Error during lesson stream: {e}", exc_info=True)
        try:
            await websocket.send_json({"error": str(e), "is_complete": True})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
