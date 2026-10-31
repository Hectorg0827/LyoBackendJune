"""Staging-only GPT-Live audio relay for Android.

No client connects to OpenAI or sees an OpenAI credential. The server owns the
WebSocket, the nonrefundable budget reservation and the wall-clock cutoff.
Only raw microphone PCM and an end command are accepted from the phone.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from lyo_app.auth.dependencies import get_current_user
from lyo_app.core.database import engine
from lyo_app.auth.schemas import UserRead
from .budget import (
    SESSION_MAX_WALL_SECONDS,
    SESSION_RESERVATION_MICRO_USD,
    TRIAL_CAP_MICRO_USD,
    TrialBudgetExhausted,
    claim_ticket,
    finish_ticket,
    get_status,
    initialize_schema,
    issue_ticket,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/gpt-live-trial", tags=["staging-gpt-live-trial"])
PROVIDER_URL = "wss://api.openai.com/v1/live/sessions"

# Do not expose user history, student data, secrets or provider events to logs.
VOICE_INSTRUCTIONS = (
    "You are Lyo, a friendly, grounded, curious voice companion for learning. "
    "Speak naturally, with human rhythm, brief thoughtful pauses, warm humor and "
    "an occasional genuine hmm or soft chuckle when it fits. Never recite stage "
    "directions or add repeated fillers. Match the learner's language and energy. "
    "Listen even while speaking; accept interruptions immediately. Ask one helpful "
    "question at a time and check understanding. Stay honest when you do not know. "
    "This is a short voice-quality trial, not a full classroom session: no learner "
    "memory, grading, or external research is connected. Do not claim otherwise. "
    "Delegate curriculum facts and tasks to the client backend."
)


def _staging_allowed(host: str) -> bool:
    """Multiple independent server-side gates; default deny in all environments."""
    expected_host = os.getenv("LYO_GPT_LIVE_STAGING_HOST", "").strip().lower()
    deploy_environment = os.getenv("ENVIRONMENT", "").strip().lower()
    railway_environment = os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip().lower()
    key_present = bool(os.getenv("LYO_GPT_LIVE_STAGING_OPENAI_API_KEY", "").strip())
    return bool(
        os.getenv("LYO_GPT_LIVE_TRIAL_ENABLED", "").strip().lower() == "true"
        and deploy_environment == "staging"
        and (not railway_environment or railway_environment == "staging")
        and expected_host
        and expected_host not in {"api.lyoai.app", "lyoai.app"}
        and host.strip().split(":")[0].lower() == expected_host
        and key_present
        and os.getenv("LYO_GPT_LIVE_TRIAL_ALLOWED_USER_IDS", "").strip()
    )


def _user_allowed(user_id: int) -> bool:
    allowlist = {
        item.strip()
        for item in os.getenv("LYO_GPT_LIVE_TRIAL_ALLOWED_USER_IDS", "").split(",")
        if item.strip()
    }
    return str(user_id) in allowlist and user_id > 0


def _local_trial_answer(context: str) -> str:
    """Deterministic sample lesson facts; no extra billable model/tool calls."""
    text = context.lower()[-1600:]
    if "fraction" in text or "fracción" in text:
        return (
            "A fraction describes part of a whole. The bottom number tells how "
            "many equal parts there are; the top number tells how many you have. "
            "For example, 3 over 4 is three of four equal pieces. Ask them to "
            "tell you what the top number means."
        )
    if "cell" in text or "célula" in text:
        return (
            "A cell is a tiny living unit. Its membrane controls what enters and "
            "leaves. Many cells have a nucleus containing DNA, and mitochondria "
            "help release usable energy. Ask which part they want to explore."
        )
    if "algebra" in text or "variable" in text:
        return (
            "In algebra a variable is a letter representing a value, such as x. "
            "If x plus 3 equals 7, subtract 3 from both sides and x is 4. "
            "Invite them to try a simple example."
        )
    return (
        "This short trial is testing natural live conversation and interruptions. "
        "The full LYO teaching engine is not connected to this trial, so don't "
        "invent answers. Invite the learner to try fractions, cells or algebra "
        "for a small verified teaching demonstration."
    )


@router.get("/status")
async def trial_status(
    request: Request,
    current_user: UserRead = Depends(get_current_user),
):
    allowed = _staging_allowed(request.headers.get("host", "")) and _user_allowed(current_user.id)
    if not allowed:
        return {"enabled": False, "cap_usd": "10.00", "session_seconds": SESSION_MAX_WALL_SECONDS}
    try:
        await initialize_schema(engine)
        snapshot = await get_status(engine)
    except Exception:
        logger.exception("Staging trial ledger unavailable")
        raise HTTPException(status_code=503, detail="Trial safety ledger unavailable")
    return {
        "enabled": snapshot.max_sessions_remaining > 0,
        "cap_usd": "10.00",
        "reserved_usd": f"{snapshot.reserved_micro_usd / 1_000_000:.2f}",
        "remaining_usd": f"{snapshot.remaining_micro_usd / 1_000_000:.2f}",
        "session_seconds": SESSION_MAX_WALL_SECONDS,
    }


@router.post("/ticket")
async def start_trial(
    request: Request,
    current_user: UserRead = Depends(get_current_user),
):
    if not _staging_allowed(request.headers.get("host", "")) or not _user_allowed(current_user.id):
        raise HTTPException(status_code=403, detail="Staging voice trial is disabled")
    try:
        await initialize_schema(engine)
        ticket = await issue_ticket(engine, int(current_user.id))
        snapshot = await get_status(engine)
    except TrialBudgetExhausted:
        raise HTTPException(status_code=429, detail="The $10 voice trial budget is exhausted")
    except Exception:
        logger.exception("Trial ledger failed closed")
        raise HTTPException(status_code=503, detail="Trial safety ledger unavailable")
    return {
        "ticket": ticket,
        "expires_in_seconds": 45,
        "session_seconds": SESSION_MAX_WALL_SECONDS,
        "reserved_usd": f"{SESSION_RESERVATION_MICRO_USD / 1_000_000:.2f}",
        "remaining_usd": f"{snapshot.remaining_micro_usd / 1_000_000:.2f}",
    }


async def _send_json(websocket: WebSocket, data: dict) -> None:
    await websocket.send_text(json.dumps(data, separators=(",", ":")))


async def _relay(websocket: WebSocket, api_key: str) -> int | None:
    """Run one provider connection. The caller imposes a hard total timeout."""
    import websockets

    last_user_transcript = ""
    reported_seconds: int | None = None
    # Only the staging-only key is ever used; production's OPENAI_API_KEY is not.
    async with websockets.connect(
        PROVIDER_URL,
        additional_headers={"Authorization": f"Bearer {api_key}"},
        open_timeout=8,
        close_timeout=2,
        max_size=2 * 1024 * 1024,
    ) as provider:
        await provider.send(json.dumps({
            "type": "session.start",
            "event_id": "lyo_trial_start",
            "session": {
                "model": "gpt-live-1",
                "instructions": VOICE_INSTRUCTIONS,
                "audio": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "output": {"voice": "marin"},
                },
                "delegation": {"type": "client", "acknowledgement_delay_ms": 600},
                "store": False,
            },
        }))
        ready = asyncio.Event()
        ending = asyncio.Event()

        async def phone_to_provider() -> None:
            window_started = time.monotonic()
            bytes_this_second = 0
            try:
                while not ending.is_set():
                    payload = await websocket.receive_text()
                    try:
                        message = json.loads(payload)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(message, dict):
                        continue
                    if message.get("type") == "end":
                        ending.set()
                        await provider.send(json.dumps({"type": "session.close"}))
                        return
                    if message.get("type") != "audio" or not ready.is_set():
                        continue
                    encoded = message.get("audio")
                    if not isinstance(encoded, str) or len(encoded) > 18_000:
                        continue
                    try:
                        pcm = base64.b64decode(encoded, validate=True)
                    except (binascii.Error, ValueError):
                        continue
                    if not pcm or len(pcm) % 2 or len(pcm) > 9600:
                        continue
                    now = time.monotonic()
                    if now - window_started >= 1:
                        window_started, bytes_this_second = now, 0
                    bytes_this_second += len(pcm)
                    if bytes_this_second > 72_000:
                        ending.set()
                        await provider.send(json.dumps({"type": "session.close"}))
                        return
                    await provider.send(json.dumps({
                        "type": "session.input_audio.append",
                        "audio": encoded,
                    }))
            except (WebSocketDisconnect, RuntimeError):
                ending.set()
                try:
                    await provider.send(json.dumps({"type": "session.close"}))
                except Exception:
                    pass

        sender = asyncio.create_task(phone_to_provider())
        try:
            async for raw in provider:
                try:
                    event = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                event_type = event.get("type")
                if event_type == "session.started":
                    ready.set()
                    await _send_json(websocket, {
                        "type": "ready", "seconds_remaining": SESSION_MAX_WALL_SECONDS,
                    })
                elif event_type == "session.output_audio.delta":
                    delta = event.get("delta")
                    if isinstance(delta, str):
                        await _send_json(websocket, {"type": "audio", "audio": delta})
                elif event_type in {"session.input_transcript.delta", "session.output_transcript.delta"}:
                    delta = event.get("delta")
                    if isinstance(delta, str) and delta:
                        role = "user" if event_type == "session.input_transcript.delta" else "assistant"
                        if role == "user":
                            last_user_transcript = (last_user_transcript + delta)[-1600:]
                        await _send_json(websocket, {
                            "type": "transcript", "role": role, "text": delta,
                        })
                elif event_type == "session.delegation.created":
                    delegation = event.get("delegation") or {}
                    identifier = delegation.get("id")
                    if delegation.get("target") == "client" and isinstance(identifier, str):
                        await provider.send(json.dumps({
                            "type": "session.commentary.append",
                            "event_id": "lyo_demo_" + uuid.uuid4().hex,
                            "delegation_id": identifier,
                            "content": _local_trial_answer(last_user_transcript),
                        }))
                elif event_type == "session.closed":
                    usage = event.get("usage") or {}
                    seconds = usage.get("seconds")
                    reported_seconds = int(seconds) if isinstance(seconds, (int, float)) and seconds >= 0 else None
                    await _send_json(websocket, {
                        "type": "ended", "reason": "session_completed",
                    })
                    return reported_seconds
                elif event_type == "error":
                    await _send_json(websocket, {
                        "type": "error", "message": "Voice provider could not continue.",
                    })
        finally:
            ending.set()
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
    return reported_seconds


@router.websocket("/stream")
async def trial_stream(websocket: WebSocket):
    """Single-use authenticated ticket; no unmetered client/provider sessions."""
    if not _staging_allowed(websocket.headers.get("host", "")):
        await websocket.close(code=1008)
        return
    ticket = websocket.headers.get("x-lyo-live-ticket", "")
    try:
        if not await claim_ticket(engine, ticket):
            await websocket.close(code=1008)
            return
    except Exception:
        logger.exception("Trial ticket verification failed closed")
        await websocket.close(code=1011)
        return

    await websocket.accept()
    seconds: int | None = None
    try:
        # Includes upstream connection, startup, speech and finalization.
        # No task survives this deadline to continue generating billable audio.
        async with asyncio.timeout(SESSION_MAX_WALL_SECONDS):
            seconds = await _relay(
                websocket,
                os.environ["LYO_GPT_LIVE_STAGING_OPENAI_API_KEY"],
            )
    except TimeoutError:
        logger.info("GPT-Live staging trial reached hard session deadline")
        try:
            await _send_json(websocket, {"type": "ended", "reason": "time_limit"})
        except Exception:
            pass
    except Exception:
        logger.exception("Staging voice trial terminated")
        try:
            await _send_json(websocket, {"type": "error", "message": "Voice trial ended safely."})
        except Exception:
            pass
    finally:
        try:
            await finish_ticket(engine, ticket, seconds)
        except Exception:
            # Never return the reservation or open a new connection on DB errors.
            logger.exception("Trial usage audit unavailable; reservation remains debited")
        try:
            await websocket.close()
        except Exception:
            pass
