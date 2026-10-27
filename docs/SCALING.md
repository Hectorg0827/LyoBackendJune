# Running more than one server process

Production runs `uvicorn lyo_app.enhanced_main:app` (see the `Dockerfile`).
Two settings decide how many copies of the app run:

- **`WEB_CONCURRENCY`** (environment variable): worker processes inside one
  container. Default `1`.
- **Railway replicas**: whole containers.

Either way, each copy has its **own memory**. Anything kept only in memory is
invisible to the other copies, and a request (or a reconnect) can land on any
copy. This page lists what is safe today and what breaks with 2 or more copies.

## Safe with several copies

| Feature | Why it is safe |
|---|---|
| Accounts, courses, posts, chat history… | Stored in PostgreSQL. |
| Uploaded files | Stored in the object-storage bucket (the server refuses to start in production without one). |
| Sign-in tokens | Each request looks the user up in the database. |
| Study reminders (`STUDY_REMINDERS_ENABLED`) | Rows are locked with `FOR UPDATE SKIP LOCKED`, so two copies never send the same reminder. |
| Course-generation jobs (`lyo_app/cache/job_store.py`) | In Redis — **only if `REDIS_URL` is set and reachable**; otherwise each copy has its own and polling another copy returns 404. |
| `/api/v1/ws/` websocket | Uses Redis pub/sub. |

## Breaks with several copies (kept only in one process's memory)

| Feature | What goes wrong | Where |
|---|---|---|
| Multi-device sync (`/sync/ws`, `/sync/devices`, session transfer, typing) | Devices only see devices connected to the **same** copy. The Redis pub/sub code exists but is never started (`conversation_sync_service.initialize()` is never called) and its listener does not forward messages. | `lyo_app/services/conversation_sync.py` |
| AI tutor sessions (`/api/v2` tutor chat) | A conversation started on one copy is unknown to the other ("session not found" / context lost). | `_sessions` in `lyo_app/ai_agents/multi_agent_v2/tutor_routes.py` |
| Living Classroom websocket and classroom conversation state | Rooms, message queues and the current topic live in memory; a reconnect to another copy starts from nothing. | `lyo_app/ai_classroom/websocket_manager.py`, `lyo_app/ai_classroom/conversation_flow.py` |
| AI agents websocket (`/api/v1/ai/ws/{user_id}`) | Messages for a user reach them only if they are connected to the copy that sends. | `lyo_app/ai_agents/websocket_manager.py` |
| Rate limits (sign-in, security middleware) | Counted per copy, so the real limit is N times higher. | `lyo_app/core/rate_limiter.py` |
| Small caches (JWT payloads, AI cost totals, asset metadata) | Harmless: each copy just has its own cache; cost totals are per copy. | various |

## Startup with several workers

Every worker runs the startup steps, including `create_all` (creating any
missing tables). When a **new** table is created, two workers can race and
one logs `Database initialization FAILED`; the other succeeds. Tables
already exist after migrations, so this is normally silent. Run a single
worker for the first deploy of a release that adds tables, if in doubt.

## Recommendation

Keep `WEB_CONCURRENCY=1` and one replica until the "Breaks" items above
that you need are moved to Redis (sync, tutor sessions, classroom state).
To handle more load before that, use a bigger Railway instance rather than
more copies.
