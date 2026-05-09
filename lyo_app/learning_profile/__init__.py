"""Learning profile module — Stage B1.

Persistent per-user learning state used by the chat to personalize:
  * subjects the user has shown interest in
  * topics where the user has struggled
  * the last classroom session (for "continue where you left off")

Read by `LyoAIViewModel` on chat startup; written by classroom session
completion + quiz failure events (handled in later stages).
"""
from lyo_app.learning_profile.routes import router  # noqa: F401
