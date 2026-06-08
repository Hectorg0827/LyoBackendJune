#!/bin/bash
# SessionStart hook for Claude Code on the web.
#
# Creates a project virtualenv and installs Python dependencies so the test
# suite (pytest) and linters (black / isort / flake8) work in remote sessions.
#
# A venv is used (rather than installing into the system interpreter) because
# the base image ships Debian-managed packages that pip cannot uninstall,
# which breaks `pip install -r requirements.txt`. The venv is isolated, matches
# how the production image installs dependencies, and keeps re-runs cheap.
#
# Idempotent and non-interactive.
set -euo pipefail

# Only run in the remote (Claude Code on the web) environment. Local sessions
# manage their own virtualenv via Poetry.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

VENV_DIR="$CLAUDE_PROJECT_DIR/.venv"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
"$VENV_PY" -m pip install --upgrade --quiet pip setuptools wheel

# Runtime dependencies (the same set the production image installs).
"$VENV_PY" -m pip install --no-cache-dir -r requirements.txt

# Test & lint tooling (pinned to match pyproject's dev group / requirements-dev).
"$VENV_PY" -m pip install --no-cache-dir \
  pytest==7.4.3 pytest-asyncio==0.21.1 pytest-cov==4.1.0 pytest-mock==3.12.0 \
  black==23.11.0 isort==5.12.0 flake8==6.1.0

# Make the venv (and the project's importable lyo_app package) the default for
# the rest of the session.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"$VENV_DIR\""
    echo "export PATH=\"$VENV_DIR/bin:\$PATH\""
    echo 'export PYTHONPATH="."'
  } >> "$CLAUDE_ENV_FILE"
fi

echo "LyoBackendJune dependencies installed into .venv (runtime + test/lint tooling)."
