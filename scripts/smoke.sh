#!/usr/bin/env bash
set -euo pipefail
python -m uvicorn lyo_app.market_ready_main:app --port 8010 --log-level warning &
PID=$!; sleep 2
curl -s http://localhost:8010/healthz | grep '"ok": true' >/dev/null
curl -s -X POST http://localhost:8010/v1/auth/login >/dev/null
curl -s http://localhost:8010/v1/feed/for-you  >/dev/null
curl -s -X POST http://localhost:8010/v1/tutor/turn >/dev/null
kill $PID
echo "SMOKE OK"
