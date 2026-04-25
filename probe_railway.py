import requests

patterns = [
    "lyobackendjune-production.up.railway.app",
    "lyo-backend-production.up.railway.app",
    "lyo-backend.up.railway.app",
    "lyobackend.up.railway.app",
    "lyo-production.up.railway.app",
    "lyo.up.railway.app"
]

for p in patterns:
    url = f"https://{p}/health"
    try:
        r = requests.get(url, timeout=3)
        print(f"Checking {url}: {r.status_code}")
        if r.status_code == 200:
            print(f"✅ FOUND LIVE ENDPOINT: {url}")
            print(r.json())
            break
    except Exception as e:
        print(f"Checking {url}: FAILED ({e})")
