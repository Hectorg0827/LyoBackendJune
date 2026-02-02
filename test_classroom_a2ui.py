"""
Test script for classroom A2UI endpoint
Tests the new /classroom/lesson/{lesson_id}/ui endpoint
"""

import json

def test_classroom_generator():
    """Test the classroom A2UI generator directly"""
    from lyo_app.a2ui.classroom_generator import classroom_a2ui_generator
    
    lesson_content = """
# Variables in Python

Variables store data values.

## Creating Variables

```python
x = 5
name = "Alice"
```

Key points:
- No type declaration needed
- Dynamic typing
- Case sensitive
"""
    
    component = classroom_a2ui_generator.generate_lesson_ui(
        lesson_title="Python Variables",
        lesson_content=lesson_content,
        module_title="Python Basics",
        lesson_number=1,
        total_lessons=10,
        has_next=True,
        has_previous=False,
        quiz_data={
            "question": "What is a variable?",
            "options": ["A container", "A function", "A loop", "A method"],
            "correct_index": 0
        }
    )
    
    print("✅ A2UI Component generated successfully!")
    print(f"   Type: {component.type}")
    print(f"   Has {len(component.children)} children" if component.children else "   No children")
    
    # Convert to dict and print JSON sample
    data_dict = component.model_dump()
    print("\n📦 Sample JSON structure:")
    print(json.dumps(data_dict, indent=2)[:500] + "...")
    
    return True

if __name__ == "__main__":
    try:
        test_classroom_generator()
        print("\n🎉 All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
