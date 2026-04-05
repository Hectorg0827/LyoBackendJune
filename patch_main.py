import re

with open("lyo_app/enhanced_main.py", "r") as f:
    content = f.read()

inject = """
import os
print(f">>> [PID {pid}] OS ENVIRON AT BOOTSTRAP START:")
for k, v in os.environ.items():
    if "KEY" in k or "SECRET" in k or "URL" in k:
        print(f"    {k}: {len(v)} chars")
    else:
        print(f"    {k}: {v}")
print(f">>> [PID {pid}] ========================")
"""

if "OS ENVIRON" not in content:
    content = content.replace("from fastapi import FastAPI", inject + "\nfrom fastapi import FastAPI")
    with open("lyo_app/enhanced_main.py", "w") as f:
        f.write(content)
