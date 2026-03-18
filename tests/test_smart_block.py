"""Tests for SmartBlock schema and serialization."""
import json
import pytest
from lyo_app.ai.schemas.smart_block import (
    SmartBlock, SmartBlockType,
    TextBlockContent, CodeBlockContent, QuizBlockContent, QuizOption,
    FlashcardBlockContent, DataVizBlockContent, MasteryMapBlockContent, MasteryNode,
)


class TestSmartBlockSchema:
    """Verify SmartBlock Pydantic models serialize correctly for iOS consumption."""

    def test_text_block_serialization(self):
        block = SmartBlock.text("Hello world", subtype="paragraph")
        data = block.model_dump()
        assert data["type"] == "text"
        assert data["subtype"] == "paragraph"
        assert data["content"]["text"] == "Hello world"
        assert data["schema_version"] == 1

    def test_code_block_serialization(self):
        block = SmartBlock.code("print('hi')", language="python")
        data = block.model_dump()
        assert data["type"] == "code"
        assert data["content"]["language"] == "python"
        assert data["content"]["code"] == "print('hi')"

    def test_quiz_block_serialization(self):
        block = SmartBlock.quiz(
            question="2+2?",
            options=[QuizOption(id="a", text="3"), QuizOption(id="b", text="4")],
            correct_index=1,
            explanation="Math",
        )
        data = block.model_dump()
        assert data["type"] == "quiz"
        assert data["content"]["question"] == "2+2?"
        assert data["content"]["correct_index"] == 1
        assert len(data["content"]["options"]) == 2

    def test_mastery_map_serialization(self):
        block = SmartBlock.mastery_map(
            title="Python",
            nodes=[MasteryNode(title="Variables", status="completed", mastery_level=1.0)],
        )
        data = block.model_dump()
        assert data["type"] == "masteryMap"
        assert data["content"]["title"] == "Python"
        assert len(data["content"]["nodes"]) == 1

    def test_data_viz_mermaid(self):
        block = SmartBlock.data_viz("graph TD; A-->B;", fmt="mermaid")
        data = block.model_dump()
        assert data["type"] == "dataViz"
        assert data["content"]["format"] == "mermaid"

    def test_json_roundtrip(self):
        block = SmartBlock.text("Test")
        json_str = block.model_dump_json()
        parsed = json.loads(json_str)
        restored = SmartBlock.model_validate(parsed)
        assert restored.type == SmartBlockType.text
        assert restored.content["text"] == "Test"

    def test_unknown_type_preserved(self):
        block = SmartBlock(
            type=SmartBlockType.unknown,
            content={"raw": "future data"},
        )
        data = block.model_dump()
        assert data["type"] == "unknown"
        assert data["content"]["raw"] == "future data"

    def test_schema_version_default(self):
        block = SmartBlock.text("Hi")
        assert block.schema_version == 1

    def test_flashcard_factory(self):
        block = SmartBlock.flashcard(front="Q", back="A")
        data = block.model_dump()
        assert data["type"] == "flashcard"
        assert data["content"]["front"] == "Q"


class TestSmartBlockIOSCompat:
    """Verify snake_case JSON keys match iOS keyDecodingStrategy expectations."""

    def test_snake_case_keys_in_json(self):
        block = SmartBlock.text("Test")
        json_str = block.model_dump_json()
        parsed = json.loads(json_str)
        # iOS uses convertFromSnakeCase
        assert "schema_version" in parsed
        assert "type" in parsed

    def test_mastery_node_snake_case(self):
        node = MasteryNode(title="Vars", status="done", mastery_level=0.5)
        data = node.model_dump()
        assert "mastery_level" in data
        assert "node_id" in data
