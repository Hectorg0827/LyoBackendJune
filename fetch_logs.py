from google.cloud import logging
import re

client = logging.Client()
logger = client.logger("run.googleapis.com/stderr")

entries = client.list_entries(
    filter_='resource.type="cloud_run_revision" AND resource.labels.service_name="lyo-backend" AND severity>=ERROR',
    order_by=logging.DESCENDING,
    max_results=50
)

for entry in entries:
    txt = entry.payload if isinstance(entry.payload, str) else str(entry.payload)
    if "pydantic" in txt or "EnhancedSettings" in txt or "environ" in txt.lower():
        print(f"Time: {entry.timestamp}")
        print(f"Log: {txt}")
        print("-" * 50)
