"""Study Plans module — Stage B2.

Persistent per-user study plans created from chat ("I have a test next
Tuesday — help me study"). Plans survive app restart and can be referenced
by the chat in subsequent sessions ("you're on day 2 of 4 of your science
plan…").

Schema is intentionally simple: subject + topics + a free-form deadline
phrase + a list of daily-breakdown strings. We don't model calendars yet
(that's Stage C); the deadline is "Tuesday" or "next week" as the user
typed it.
"""
from lyo_app.study_plans.routes import router  # noqa: F401
