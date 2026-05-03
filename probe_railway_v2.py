import requests

patterns = [
    "lyo-production.up.railway.app",
    "lyo-backend-production.up.railway.app",
    "lyobackendjune-production.up.railway.app",
    "production-lyo.up.railway.app",
    "lyo-api-production.up.railway.app"
]

for p in patterns:
    url = f"https://{p}/health"
    try:
        r = requests.get(url, timeout=3)
        print(f"Checking {url}: {r.status_code}")
        print(f"Body: {r.text}")
        if r.status_code == 200 and "features" in r.text:
            print(f"✅ FOUND ENHANCED BACKEND: {url}")
            break
    except Exception as e:
        print(f"Checking {url}: FAILED ({e})")
