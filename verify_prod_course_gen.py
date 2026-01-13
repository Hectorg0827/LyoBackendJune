
import urllib.request
import json
import ssl
import sys

# URL from the deployment log and user report
URL = "https://lyo-backend-830162750094.us-central1.run.app/api/v1/classroom/chat"
API_KEY = "lyo_sk_live_S5ALtW3WDjhF-TAgn767ORCCga4Nx52xBlAkMHg2-TQ"

def verify_prod():
    print(f"🧪 Verifying Production Fix at: {URL}")
    
    # Simulate a long topic request to test the truncation fix
    # "Create a course on " + 100 chars
    long_topic = "Advanced Quantum Mechanics and the Unified Field Theory Application in Modern Computing Architectures and Beyond"
    payload = {
        "message": f"Create a course on {long_topic}",
        "stream": False
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        "X-Platform": "iOS"
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(URL, data=data, headers=headers, method='POST')
    
    try:
        # Create unverified context to avoid SSL cert issues in some python envs
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, context=context, timeout=30) as response:
            status = response.getcode()
            response_body = response.read().decode('utf-8')
            json_response = json.loads(response_body)
            
            print(f"✅ Status Code: {status}")
            
            if status != 200:
                print(f"❌ Failed: Expected 200, got {status}")
                print(f"Response: {response_body}")
                sys.exit(1)
                
            # Check for OPEN_CLASSROOM
            response_type = json_response.get("response_type")
            print(f"ℹ️  Response Type: {response_type}")
            
            if response_type != "OPEN_CLASSROOM":
                print(f"❌ Failed: Expected response_type 'OPEN_CLASSROOM', got '{response_type}'")
                print(f"Full Response: {json_response}")
                sys.exit(1)
                
            # Check for OpenClassroom Payload
            payload = json_response.get("openClassroomPayload")
            if not payload:
                # Fallback: check metadata?
                metadata = json_response.get("metadata", {})
                payload = metadata.get("openClassroomPayload")
            
            if payload:
                print("✅ Found 'openClassroomPayload'")
                print(f"Payload Content: {payload}")
                
                # Verify ID presence (Critical Fix)
                course_data = payload.get("course", {})
                if not course_data.get("id"):
                    print("❌ Failed: 'id' missing from course payload")
                    sys.exit(1)
                print("✅ Found 'course.id' in payload")
            else:
                print("❌ Failed: 'openClassroomPayload' missing from response")
                print(f"Full Response: {json_response}")
                sys.exit(1)

            print("\n🎉 SUCCESS: Live production verification passed!")
            print("- No 500 Error (Safety truncation worked)")
            print("- Correct 'OPEN_CLASSROOM' response type returned")
            
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error: {e.code}")
        print(e.read().decode('utf-8'))
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_prod()
