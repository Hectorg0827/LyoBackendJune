"""Tests for SmartBlock SSE emission conversion in stream_lyo2."""
import json
import pytest
from lyo_app.ai.schemas.lyo2 import UIBlock, UIBlockType
from lyo_app.api.v1.stream_lyo2 import _to_smart_blocks


class TestToSmartBlocks:
    def test_plain_text_answer(self):
        blocks = _to_smart_blocks("Hello world", None)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        assert blocks[0]["subtype"] == "paragraph"
        assert blocks[0]["content"]["text"] == "Hello world"

    def test_empty_answer_no_artifact(self):
        blocks = _to_smart_blocks("", None)
        assert blocks == []

    def test_none_answer_no_artifact(self):
        blocks = _to_smart_blocks(None, None)
        assert blocks == []

    def test_quiz_artifact(self):
        artifact = UIBlock(
            type=UIBlockType.QUIZ,
            content={
                "question": "What is 2+2?",
                "options": [{"text": "3"}, {"text": "4"}, {"text": "5"}],
                "correct_index": 1,
                "explanation": "Basic math",
            },
        )
        blocks = _to_smart_blocks("Try this quiz:", artifact)
        assert len(blocks) == 2
        assert blocks[0]["type"] == "text"
        assert blocks[1]["type"] == "quiz"
        assert blocks[1]["content"]["question"] == "What is 2+2?"
        assert len(blocks[1]["content"]["options"]) == 3
        assert blocks[1]["content"]["correct_index"] == 1

    def test_flashcards_artifact(self):
        artifact = UIBlock(
            type=UIBlockType.FLASHCARDS,
            content={
                "cards": [
                    {"front": "Q1", "back": "A1"},
                    {"front": "Q2", "back": "A2"},
                ],
            },
        )
        blocks = _to_smart_blocks(None, artifact)
        assert len(blocks) == 2
        assert all(b["type"] == "flashcard" for b in blocks)
        assert blocks[0]["content"]["front"] == "Q1"
        assert blocks[1]["content"]["back"] == "A2"

    def test_study_plan_artifact(self):
        artifact = UIBlock(
            type=UIBlockType.STUDY_PLAN,
            content={"plan": "Step 1: Read chapter 3\nStep 2: Solve exercises"},
        )
        blocks = _to_smart_blocks("Here's your plan:", artifact)
        assert len(blocks) == 2
        assert blocks[0]["type"] == "text"
        assert blocks[0]["subtype"] == "paragraph"
        assert blocks[1]["type"] == "text"
        assert blocks[1]["subtype"] == "summary"
        assert "Step 1" in blocks[1]["content"]["text"]

    def test_schema_version_present(self):
        blocks = _to_smart_blocks("Hello", None)
        assert blocks[0]["schema_version"] == 1

    def test_quiz_with_string_options(self):
        """Quiz options can be plain strings instead of dicts."""
        artifact = UIBlock(
            type=UIBlockType.QUIZ,
            content={
                "question": "Capital of France?",
                "options": ["Berlin", "Paris", "Madrid"],
                "correct_index": 1,
            },
        )
        blocks = _to_smart_blocks(None, artifact)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "quiz"
        assert blocks[0]["content"]["options"][1]["text"] == "Paris"
