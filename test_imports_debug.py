import sys
import logging

logging.basicConfig(level=logging.DEBUG)
print("Importing chat...", flush=True)

import lyo_app.api.v1.chat

print("Done importing chat", flush=True)
