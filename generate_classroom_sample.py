"""
Generate sample A2UI JSON for iOS testing
This creates a JSON file that iOS can try to decode
"""

import json
from lyo_app.a2ui.classroom_generator import classroom_a2ui_generator

def generate_sample_json():
    """Generate a sample lesson UI as JSON"""
    
    lesson_content = """
# Welcome to Python

Python is a beginner-friendly programming language.

## Your First Program

```python
print("Hello, World!")
```

Key features:
- Easy to read
- Powerful libraries  
- Great community
"""
    
    component = classroom_a2ui_generator.generate_lesson_ui(
        lesson_title="Introduction to Python",
        lesson_content=lesson_content,
        module_title="Python Basics",
        lesson_number=1,
        total_lessons=5,
        has_next=True,
        has_previous=False,
        quiz_data={
            "question": "What does print() do?",
            "options": [
                "Prints to console",
                "Deletes data",
                "Creates a file",
                "None of the above"
            ],
            "correct_index": 0,
            "explanation": "print() displays output to the console"
        }
    )
    
    # Convert to dict
    data = component.model_dump()
    
    # Save to file
    output_path = "sample_classroom_ui.json"
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Generated: {output_path}")
    print(f"   Component type: {data['type']}")
    print(f"   Children count: {len(data.get('children', []))}")
    print("\n📋 First 3 children types:")
    for i, child in enumerate(data.get('children', [])[:3]):
        print(f"   {i+1}. {child.get('type', 'unknown')}")
    
    return output_path

if __name__ == "__main__":
    generate_sample_json()
