# WebSocket credential containment

Uvicorn logs accepted/rejected WebSocket URLs on `uvicorn.error`. Disabling
HTTP access logs or filtering only the root logger misses that channel.

The record factory installed by `lyo_app.core.logging` strips every query
string, bearer credential, and JWT before a handler formats it. It preserves
the five argument fields used by Uvicorn's HTTP access formatter and sanitizes
exception tracebacks. The regression suite exercises actual local Uvicorn
HTTP requests and accepted/rejected WebSocket handshakes.

`JWT_REVOKED_JTIS` is a comma-separated list of JWT IDs for targeted incident
containment. Put only IDs in this variable, never complete tokens. Both fresh
and cached canonical JWT verification consult it, as does the legacy verifier.
It does not rotate signing keys or invalidate unrelated learner sessions.
Deploy with the affected IDs set; remove an ID only after its token expires.
Existing socket connections are closed by the replacement deployment.

This hotfix preserves old installed clients. It does not remove credentials
from already-retained logs. Limit access to those logs and apply the available
retention/purge controls separately.

The companion transport change must issue short-lived, single-use,
resource-bound tickets over authenticated HTTPS, consume them atomically, and
avoid JWTs in WebSocket URLs on Web/iOS/Android. Backend capability must deploy
first. Disable legacy query authentication only after supported clients have
been updated and their sync/Classroom/reconnect contracts validated.

Focused checks:

```
python -m pytest -q tests/test_websocket_log_redaction.py tests/test_jwt_emergency_revocation.py tests/test_logging_levels.py
```
