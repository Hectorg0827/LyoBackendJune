import sys
import os
import json
from pydantic import BaseModel

# Add current directory to path so we can import lyo_app
sys.path.insert(0, os.getcwd())

import pytest

# `workflows` imports temporalio, which is an optional deployment dependency.
# Calling sys.exit here — as this file used to — turns a missing optional
# package into a collection crash that takes down the entire suite, not just
# this module. Skipping leaves every other test runnable.
WorkflowStatusResponse = pytest.importorskip(
    "lyo_app.routers.workflows",
    reason="temporalio is not installed in this environment",
).WorkflowStatusResponse

def test_workflow_status_serialization():
    print("Testing WorkflowStatusResponse serialization...")
    
    # Create sample data
    mock_append = [{"type": "lesson", "title": "New Lesson", "content": {}}]
    mock_replace = [{"target_id": "old_lesson", "content": {"title": "Updated Lesson"}}]
    
    response = WorkflowStatusResponse(
        workflow_id="test-123",
        status="RUNNING",
        current_step="Generating content",
        total_steps=10,
        completed_steps=2,
        progress_percentage=20.0,
        lessons_completed=[],
        append_items=mock_append,
        replace_items=mock_replace,
        proxy_justification="Starting with basics..."
    )
    
    # Serialize to dict (as FastAPI would)
    data = response.model_dump() if hasattr(response, 'model_dump') else response.dict()
    
    # Verification
    if "append_items" not in data:
        print("❌ FAILED: append_items missing")
        sys.exit(1)
        
    if "replace_items" not in data:
        print("❌ FAILED: replace_items missing")
        sys.exit(1)
        
    if data["append_items"] != mock_append:
        print("❌ FAILED: append_items content mismatch")
        sys.exit(1)
        
    print("✅ SUCCESS: WorkflowStatusResponse supports optimized hydration fields.")
    print(f"JSON Output: {json.dumps(data, indent=2)}")

if __name__ == "__main__":
    test_workflow_status_serialization()
