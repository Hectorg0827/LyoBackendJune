
import sys
import os
import json

# Ensure we can import lyo_app
sys.path.append(os.getcwd())

from fastapi.testclient import TestClient
from lyo_app.enhanced_main import app

from lyo_app.auth.routes import get_current_user
from lyo_app.models.enhanced import User
from unittest.mock import MagicMock

def verify_beacons():
    print("🚀 Starting Community Beacons Verification...")
    
    # Mock User
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.email = "test@example.com"
    
    # Override Dependency
    app.dependency_overrides[get_current_user] = lambda: mock_user
    
    client = TestClient(app)
    
    # Define test coordinates (San Francisco)
    lat = 37.7749
    lng = -122.4194
    radius = 50
    
    print(f"\n📍 Fetching beacons for Lat: {lat}, Lng: {lng}, Radius: {radius}km")
    
    response = client.get(f"/api/v1/community/beacons?lat={lat}&lng={lng}&radius_km={radius}&include_events=true&include_users=false&include_questions=true")
    
    if response.status_code == 200:
        beacons = response.json()
        print(f"✅ Success! Found {len(beacons)} beacons.")
        
        # Validate structure
        for b in beacons:
            if "type" not in b:
                print(f"❌ Error: Beacon missing 'type' field: {b}")
                sys.exit(1)
            
            b_type = b["type"]
            print(f"   - Beacon Type: {b_type}, ID: {b.get('id')}")
            
            # Check specific fields based on type
            if b_type == "event":
                if "title" not in b or "latitude" not in b:
                     print(f"❌ Error: Event beacon missing fields: {b}")
            elif b_type == "user_activity":
                if "display_name" not in b:
                     print(f"❌ Error: User beacon missing display_name: {b}")
                     
        print("\n✅ All beacon structures appear valid.")
        
    else:
        print(f"❌ Failed to fetch beacons. Status: {response.status_code}")
        print(response.text)
        sys.exit(1)

if __name__ == "__main__":
    verify_beacons()
