"""Run the end-to-end learner loop in CI.

`scripts/e2e_learner_loop.py` boots the real application over a real database
and walks one learner from answering a check through to what the product then
tells them about themselves. Every other test in this suite exercises a piece
of that chain; this is the only one that exercises the chain.

It lives as a script so a person can run it directly while debugging, and as a
test so it cannot quietly stop working.
"""

import asyncio
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "e2e_learner_loop.py"


def _load():
    spec = importlib.util.spec_from_file_location("e2e_learner_loop", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.timeout(300)
def test_a_learner_can_go_round_the_loop():
    """Answer a check; be recorded; be described honestly back.

    A failure here means the chain is broken somewhere between the check
    endpoint, the event processor, the two projections and the three read
    endpoints — even if every unit test for those still passes.
    """
    from lyo_app.core.database import get_db
    from lyo_app.enhanced_main import app

    before = dict(app.dependency_overrides)

    module = _load()
    exit_code = asyncio.run(module.main())

    assert exit_code == 0, f"failed checks: {module.FAILURES}"
    # Guard against the script silently degrading into asserting nothing.
    assert len(module.CHECKS) >= 15, f"only {len(module.CHECKS)} checks ran"

    # `app` is a module-level singleton. The first version of this script left
    # its database override in place, handing every later test a session that
    # was already closed — four unrelated auth tests failed and the cause was
    # nowhere near them. Cheap to assert, miserable to debug.
    assert app.dependency_overrides == before, (
        "the e2e run leaked a dependency override onto the shared app"
    )
    assert get_db not in app.dependency_overrides or before.get(get_db) is not None
