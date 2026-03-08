import os
import re

directories_to_scan = ["lyo_app", "../Sources", "."]

replacements = [
    (r"gemini-2\.[0-5]-flash-lite", "gemini-3.1-pro-preview-customtools"),
    (r"gemini-2\.[0-5]-flash", "gemini-3.1-pro-preview-customtools"),
    (r"gemini-2\.[0-5]-pro", "gemini-3.1-pro-preview-customtools")
]

modified_files = []

for base_dir in directories_to_scan:
    if not os.path.exists(base_dir):
        continue
    for root, dirs, files in os.walk(base_dir):
        # Exclude directories
        dirs[:] = [d for d in dirs if d not in ("venv", ".venv", "__pycache__", ".git", "tests")]
        for file in files:
            if file.endswith((".py", ".swift", ".json", ".md")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    new_content = content
                    for pattern, repl in replacements:
                        new_content = re.sub(pattern, repl, new_content)
                    
                    if new_content != content:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        modified_files.append(file_path)
                except Exception as e:
                    pass

print(f"Updated {len(modified_files)} files:")
for f in modified_files:
    print(f" - {f}")
