import os
print("=== OS ENVIRON ===")
for k, v in os.environ.items():
    if "KEY" in k or "SECRET" in k or "URL" in k:
        print(f"{k}: {len(v)} chars")
    else:
        print(f"{k}: {v}")
print("==================")
