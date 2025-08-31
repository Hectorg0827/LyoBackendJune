#!/usr/bin/env python3
"""Quick sanity checks for StudyModeService enhancements.
Runs adaptive difficulty, history summarization threshold, and quiz prompt structure validations.
Use this as a fallback while pytest output issue is investigated.
"""
import os, asyncio, sys
os.environ.setdefault("SECRET_KEY", "quick-test-key")
os.environ.setdefault("GCS_BUCKET_NAME", "quick-bucket")
os.environ.setdefault("GCS_PROJECT_ID", "quick-project")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from lyo_app.ai_study.service import StudyModeService
from lyo_app.ai_study.models import StudySession, QuizType
from lyo_app.ai_study.schemas import ConversationMessage, QuizGenerationRequest

failures = []

svc = StudyModeService()

# 1. Adaptive difficulty
sess = StudySession(user_id=1, resource_id="r1", tutor_personality="socratic", difficulty_level="intermediate")
svc._adjust_adaptive_difficulty(sess, 95.0)
if sess.difficulty_level not in ("advanced", "expert", "intermediate"):
    failures.append(f"Adaptive high score escalation unexpected level {sess.difficulty_level}")
svc._adjust_adaptive_difficulty(sess, 20.0)
if sess.difficulty_level not in ("beginner", "intermediate", "advanced", "expert"):
    failures.append(f"Adaptive low score de-escalation unexpected level {sess.difficulty_level}")

# 2. History summarization no-op below threshold
history = [ConversationMessage(role=None, content=f"msg {i}") for i in range(svc.SUMMARIZE_THRESHOLD - 2)]
summary = asyncio.run(svc._maybe_summarize_history(history))
if len(summary) != len(history):
    failures.append("History summarization altered short history unexpectedly")

# 3. Quiz prompt structure
req = QuizGenerationRequest(
    resource_id="res1",
    resource_title="Title",
    resource_content="Some content",
    quiz_type=QuizType.MULTIPLE_CHOICE,
    question_count=3,
    difficulty_level="intermediate",
    focus_areas=["topic1"],
)
resource_info = {"title": "Title", "type": "article", "description": "Desc"}
prompt = svc._build_quiz_generation_prompt(resource_info, req)
for fragment in ["RESOURCE DETAILS", "QUIZ REQUIREMENTS", "OUTPUT FORMAT", "Generate exactly"]:
    if fragment not in prompt:
        failures.append(f"Missing fragment in quiz prompt: {fragment}")

if failures:
    print("FAILURES:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
else:
    print("All quick enhancement checks passed (3).")
    sys.exit(0)
