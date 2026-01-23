#!/usr/bin/env python3

import sys
import os
import json
sys.path.insert(0, '/Users/hectorgarcia/Desktop/LyoBackendJune')

# Test imports
from lyo_app.chat.a2ui_recursive import A2UIFactory

# Test basic creation
print("🧪 Testing A2UI Factory...")

text = A2UIFactory.text("Hello World!", style="title")
button = A2UIFactory.button("Click Me", "test_action", variant="primary")

ui = A2UIFactory.vstack(
    text,
    button,
    A2UIFactory.divider(),
    spacing=16.0
)

print("✅ Components created successfully!")

# Convert to JSON
json_data = ui.model_dump()
json_str = json.dumps(json_data, indent=2)

print(f"✅ JSON serialization successful: {len(json_str)} characters")
print("\n📋 Sample JSON Output:")
print(json_str[:500] + "..." if len(json_str) > 500 else json_str)

print("\n🎉 Backend A2UI implementation is working!")