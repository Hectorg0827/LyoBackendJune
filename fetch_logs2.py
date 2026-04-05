from google.cloud import logging
client = logging.Client()
entries = client.list_entries(
    filter_='resource.type="cloud_run_revision" AND resource.labels.service_name="lyo-backend"',
    order_by=logging.DESCENDING,
    max_results=100
)

for entry in entries:
    txt = entry.payload if isinstance(entry.payload, str) else str(entry.payload)
    if "OS ENVIRON" in txt or "chars" in txt or "http" in txt or "Traceback" in txt:
        print(f"Time: {entry.timestamp} | {entry.severity}")
        print(f"Log: {txt[:200]}")
        print("-" * 50)
