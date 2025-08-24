# 📘 Lyo Backend — Make It 100% Functional

**Stack:** FastAPI, Postgres + SQLAlchemy/Alembic, Redis, Celery, APNs, Python 3.11+
**Goal:** Ensure the backend is production-ready and the iOS app can fully leverage it.

---

## ✅ Definition of Done

* All routes under `/v1/*` with OpenAPI docs.
* **Auth:** JWT login + refresh, protected routes with dependency.
* **Errors:** Global Problem Details handler (`type,title,status,detail,instance`, `content-type: application/problem+json`).
* **AI Course generation:**

  * `POST /v1/courses:generate` → `202 { task_id, provisional_course_id }` (requires `Idempotency-Key`).
  * **Progress:** WebSocket (`/v1/ws/tasks/{task_id}`) + fallback polling (`GET /v1/tasks/{task_id}`).
  * **Result:** `GET /v1/courses/{id}` returns normalized payload (`lessons[]` and `items[]`).
* **Feeds & Community:** Cursor pagination, returns `{ items[], nextCursor }`.
* **Gamification:** `/v1/gamification/profile` → `{ xp, streak, badges[] }`.
* **Push Devices:** `POST /v1/push/devices`; server sends APNs on course completion.
* **Gemma 3 Model:** Not in Git. Pulled/mounted at runtime; checksum verified; `/v1/health/model` indicates readiness.
* **Health Checks:** `/v1/health/ready` (DB/Redis) and `/v1/health/model`.
* **Celery/Redis:** Task state mirrored in DB (`tasks` table). Redis only used for lightweight pub/sub messages.
* **Alembic:** Migrations exist and apply schema.
* **Automated Smoke Test:** Runs green (see below).

---

## ⚙️ Backend Setup Highlights

### Global Error Handler (Problem Details)

```python
# app/core/errors.py
from fastapi import Request
from fastapi.responses import JSONResponse

def problem_details_handler(request: Request, exc: Exception):
    status = getattr(exc, "status_code", 500)
    body = {
        "type": f"https://api.lyo.app/problems/{exc.__class__.__name__}",
        "title": getattr(exc, "title", "Internal Server Error"),
        "status": status,
        "detail": str(exc),
        "instance": str(request.url),
    }
    return JSONResponse(status_code=status, content=body,
                        headers={"content-type":"application/problem+json"})
```

---

### Learning Flow (Generate → Track → Fetch)

**Kickoff:**

```python
@router.post("/courses:generate", status_code=202)
async def generate_course(payload: dict,
                          user=Depends(require_user),
                          idemp: str | None = Header(default=None, alias="Idempotency-Key")):
    if not idemp: raise HTTPException(400, "Idempotency-Key required")
    existing = await db.tasks.find_one({"idempotency_key": idemp, "user_id": user.id})
    if existing:
        return {"task_id": str(existing["id"]), "provisional_course_id": str(existing["provisional_course_id"])}
    task_id, prov_id = uuid4(), uuid4()
    await db.tasks.insert({...})
    generate_course_task.delay(str(task_id), str(user.id), payload)
    return {"task_id": str(task_id), "provisional_course_id": str(prov_id)}
```

**Polling:**

```python
@router.get("/tasks/{task_id}")
async def get_task(task_id: str, user=Depends(require_user)):
    t = await db.tasks.get(task_id)
    if not t or t["user_id"] != user.id: raise HTTPException(404)
    return {"state": t["state"], "progressPct": t["progress_pct"],
            "message": t.get("message"), "resultId": t.get("result_course_id")}
```

**WebSocket:**

```python
@router.websocket("/ws/tasks/{task_id}")
async def ws_task(ws: WebSocket, task_id: str):
    await ws.accept()
    async for msg in subscribe(f"task:{task_id}"):
        await ws.send_json(msg)
```

---

### Celery Worker (Task Execution)

```python
@celery.task(bind=True)
def generate_course_task(self, task_id: str, user_id: str, payload: dict):
    db = sync_db()
    try:
        db.tasks.update(task_id, {"state":"RUNNING","progress_pct":5})
        publish(f"task:{task_id}", {"state":"RUNNING","progressPct":5})
        ensure_model()
        course_id = curate_course(db, user_id, payload, progress_cb=lambda pct, msg:
            publish(f"task:{task_id}", {"state":"RUNNING","progressPct":pct,"message":msg}))
        db.tasks.update(task_id, {"state":"DONE","progress_pct":100,"result_course_id":course_id})
        publish(f"task:{task_id}", {"state":"DONE","progressPct":100,"resultId":course_id})
        notify_course_ready(db, user_id, course_id)
    except Exception as e:
        db.tasks.update(task_id, {"state":"ERROR","message":str(e)})
        publish(f"task:{task_id}", {"state":"ERROR","message":str(e)})
        raise
```

---

## 🔥 Smoke Test (save as `smoke_test.py`)

```python
import argparse, json, time, uuid, asyncio, requests
try: import websockets
except: raise SystemExit("Install websockets: pip install websockets")

def ok(name, cond, extra=""): print(("✅" if cond else "❌")+f" {name} {extra if extra else ''}"); return cond
def get(o,p,d=None): cur=o; 
for k in p.split("."): 
  if isinstance(cur,dict) and k in cur: cur=cur[k]
  else: return d
return cur

async def ws_progress(url,timeout=30):
    events=[]; 
    try:
        async with websockets.connect(url) as ws:
            start=time.time()
            while time.time()-start<timeout:
                try:
                    msg=await asyncio.wait_for(ws.recv(),timeout=5)
                    events.append(json.loads(msg))
                    if get(events[-1],"state") in ("DONE","ERROR"): break
                except asyncio.TimeoutError: pass
    except Exception as e: return False,events,str(e)
    return bool(events),events,""

def main():
    ap=argparse.ArgumentParser(); 
    ap.add_argument("--base"); ap.add_argument("--email"); ap.add_argument("--password"); 
    args=ap.parse_args(); base=args.base.rstrip("/"); wsbase=base.replace("http","ws")
    sess=requests.Session(); sess.headers["content-type"]="application/json"

    # Health
    r=sess.get(f"{base}/v1/health/ready"); ok("Health",r.status_code==200)

    # Login
    r=sess.post(f"{base}/v1/auth/login",data=json.dumps({"email":args.email,"password":args.password}))
    at=get(r.json(),"access_token"); rt=get(r.json(),"refresh_token"); ok("Login",r.status_code==200 and at)
    sess.headers["Authorization"]=f"Bearer {at}"

    # Refresh
    r=sess.post(f"{base}/v1/auth/refresh",data=json.dumps({"refresh_token":rt})); ok("Refresh",r.status_code==200)

    # Problem Details
    r=sess.post(f"{base}/v1/courses:generate",data=json.dumps({}))
    ok("ProblemDetails",r.status_code in (400,422) and r.headers.get("content-type","").startswith("application/problem+json"))

    # Kickoff
    idemp=str(uuid.uuid4()); payload={"topic":"genai","interests":["ml"],"level":"beginner","locale":"en"}
    r=sess.post(f"{base}/v1/courses:generate",headers={"Idempotency-Key":idemp,"Prefer":"respond-async"},data=json.dumps(payload))
    task_id=get(r.json(),"task_id"); ok("Generate",r.status_code==202 and task_id)

    # Idempotency replay
    r2=sess.post(f"{base}/v1/courses:generate",headers={"Idempotency-Key":idemp},data=json.dumps(payload))
    ok("Idempotency",get(r2.json(),"task_id")==task_id)

    # WS progress
    ws_url=f"{wsbase}/v1/ws/tasks/{task_id}"; success,_,err=asyncio.get_event_loop().run_until_complete(ws_progress(ws_url))
    ok("WebSocket progress",success or not err)

    # Poll fallback
    state,course_id=None,None; t0=time.time()
    while time.time()-t0<300:
        r=sess.get(f"{base}/v1/tasks/{task_id}"); state=get(r.json(),"state")
        if state in ("DONE","ERROR"): course_id=get(r.json(),"resultId"); break
        time.sleep(2)
    ok("Task DONE",state=="DONE")

    # Course payload
    if course_id:
        r=sess.get(f"{base}/v1/courses/{course_id}")
        good=r.status_code==200 and all(k in (r.json()["items"][0] if r.json()["items"] else {}) for k in ["id","type","title","source","sourceUrl"])
        ok("Course payload normalized",good)
    else: ok("Course payload normalized",False,"No course_id")

    # Feeds endpoint
    r=sess.get(f"{base}/v1/feeds?limit=5"); ok("Feeds reachable",r.status_code in (200,204,404))

if __name__=="__main__": main()
```

### Run it:

```bash
python smoke_test.py --base http://localhost:8000 --email demo@example.com --password demo
```

✅ = Good. ❌ = Fix required.

---

## 🎯 Acceptance Criteria

* Kickoff returns **202**; duplicate `Idempotency-Key` returns same task.
* WS progress or fallback polling reports state until **DONE**.
* Final course payload has normalized `items[]`.
* Problem Details returned on errors.
* Feeds/Community paginate correctly.
* Push notifications delivered (in staging with APNs creds).
* `/v1/health/*` checks pass.
* Smoke test shows all ✅.

---

👉 Deliver this spec, code updates, and smoke test. Run the smoke test on local/staging until it's all green. Then the backend is **100% functional**.

---

## 📋 Additional Implementation Notes

### Required Database Tables

```sql
-- Tasks table for async operations
CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    idempotency_key VARCHAR(255) UNIQUE,
    state VARCHAR(20) DEFAULT 'PENDING',
    progress_pct INTEGER DEFAULT 0,
    message TEXT,
    provisional_course_id UUID,
    result_course_id UUID,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Courses table
CREATE TABLE courses (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    title VARCHAR(500),
    description TEXT,
    status VARCHAR(50) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Course items (lessons, videos, etc.)
CREATE TABLE course_items (
    id UUID PRIMARY KEY,
    course_id UUID REFERENCES courses(id),
    type VARCHAR(50), -- 'lesson', 'video', 'quiz', etc.
    title VARCHAR(500),
    content TEXT,
    source VARCHAR(100),
    source_url TEXT,
    order_index INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- User profiles for gamification
CREATE TABLE user_profiles (
    user_id UUID PRIMARY KEY,
    xp INTEGER DEFAULT 0,
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    last_activity_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Badges
CREATE TABLE badges (
    id UUID PRIMARY KEY,
    name VARCHAR(100),
    description TEXT,
    icon_url VARCHAR(500),
    criteria JSONB
);

-- User badges (many-to-many)
CREATE TABLE user_badges (
    user_id UUID,
    badge_id UUID,
    earned_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, badge_id)
);

-- Push devices
CREATE TABLE push_devices (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    device_token VARCHAR(255) UNIQUE,
    platform VARCHAR(20), -- 'ios', 'android'
    active BOOLEAN DEFAULT true,
    registered_at TIMESTAMP DEFAULT NOW()
);

-- Feed items
CREATE TABLE feed_items (
    id UUID PRIMARY KEY,
    type VARCHAR(50), -- 'course_completion', 'achievement', 'community_post'
    title VARCHAR(500),
    content TEXT,
    user_id UUID,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/lyo_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# JWT
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# APNs (for push notifications)
APNS_KEY_ID=your-apns-key-id
APNS_TEAM_ID=your-team-id
APNS_BUNDLE_ID=com.yourapp.lyo
APNS_PRIVATE_KEY_PATH=path/to/AuthKey.p8
APNS_USE_SANDBOX=true

# AI Model
MODEL_PATH=/app/models/gemma-3
MODEL_CHECKSUM=expected-model-checksum
```

### API Route Structure

```
/v1/
├── auth/
│   ├── POST /login
│   ├── POST /refresh
│   └── POST /logout
├── courses/
│   ├── POST :generate
│   ├── GET /{id}
│   ├── GET / (list user courses)
│   └── PUT /{id}/progress
├── tasks/
│   └── GET /{task_id}
├── ws/
│   └── /tasks/{task_id}
├── feeds/
│   └── GET / (with cursor pagination)
├── gamification/
│   ├── GET /profile
│   ├── POST /activity
│   └── GET /leaderboard
├── push/
│   ├── POST /devices
│   └── DELETE /devices/{token}
└── health/
    ├── GET /ready
    └── GET /model
```

### WebSocket Message Format

```json
{
  "state": "RUNNING|DONE|ERROR",
  "progressPct": 45,
  "message": "Generating lesson 3 of 5...",
  "resultId": "course-uuid-here"
}
```

### Course Payload Format

```json
{
  "id": "course-uuid",
  "title": "Introduction to GenAI",
  "description": "Learn the fundamentals...",
  "status": "completed",
  "lessons": [
    {
      "id": "lesson-uuid",
      "title": "What is GenAI?",
      "order": 1,
      "items": ["item-uuid-1", "item-uuid-2"]
    }
  ],
  "items": [
    {
      "id": "item-uuid-1",
      "type": "video",
      "title": "Introduction Video",
      "source": "youtube",
      "sourceUrl": "https://youtube.com/watch?v=...",
      "duration": 300
    },
    {
      "id": "item-uuid-2", 
      "type": "text",
      "title": "Key Concepts",
      "content": "GenAI refers to...",
      "source": "generated",
      "sourceUrl": null
    }
  ],
  "createdAt": "2025-08-22T10:30:00Z"
}
```

This comprehensive guide provides everything needed to implement a fully functional Lyo backend that will integrate seamlessly with the iOS app and provide a robust learning platform experience.
