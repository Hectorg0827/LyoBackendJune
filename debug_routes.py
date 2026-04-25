import subprocess
import sys

print("--- PIP LIST ---")
subprocess.run([sys.executable, "-m", "pip", "list"])

print("\n--- PIP SHOW google-cloud-aiplatform ---")
subprocess.run([sys.executable, "-m", "pip", "show", "-f", "google-cloud-aiplatform"])

print("\n--- CHECKING SITE-PACKAGES ---")
subprocess.run(["ls", "-la", "/opt/venv/lib/python3.11/site-packages"])

try:
    import vertexai
    print("\nVERTEXAI IMPORT SUCCESSFUL:", vertexai.__file__)
except Exception as e:
    print("\nVERTEXAI IMPORT FAILED:", repr(e))
