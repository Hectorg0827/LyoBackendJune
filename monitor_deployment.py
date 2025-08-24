#!/usr/bin/env python3
"""
Monitor your Cloud Run deployment health and metrics
Usage: python monitor_deployment.py <service-name> <region>
Example: python monitor_deployment.py lyo-backend us-central1
"""

import subprocess
import json
import time
from datetime import datetime
import sys

def run_gcloud_command(command):
    """Execute gcloud command and return output"""
    try:
        result = subprocess.run(
            command.split(),
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr}")
        return None

def get_service_url(service_name, region):
    """Get the service URL"""
    try:
        url = run_gcloud_command(
            f"gcloud run services describe {service_name} --region={region} --format=value(status.url)"
        )
        return url.strip() if url else None
    except:
        return None

def test_endpoint(url, endpoint="/health"):
    """Test if endpoint is responding"""
    try:
        import requests
        response = requests.get(f"{url}{endpoint}", timeout=10)
        return response.status_code == 200
    except:
        return False

def monitor_service(service_name, region):
    """Monitor Cloud Run service"""
    print(f"📊 Monitoring {service_name} in {region}")
    print("=" * 60)
    
    service_url = get_service_url(service_name, region)
    if service_url:
        print(f"🔗 Service URL: {service_url}")
    else:
        print("❌ Could not retrieve service URL")
    
    print("Press Ctrl+C to stop monitoring")
    print("-" * 60)
    
    try:
        while True:
            # Get service details
            service_json = run_gcloud_command(
                f"gcloud run services describe {service_name} --region={region} --format=json"
            )
            
            if service_json:
                service = json.loads(service_json)
                
                # Extract metrics
                status = service.get('status', {})
                conditions = status.get('conditions', [])
                
                print(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"📈 Latest Revision: {status.get('latestCreatedRevisionName', 'N/A')}")
                
                # Check conditions
                for condition in conditions:
                    status_icon = "✅" if condition.get('status') == 'True' else "❌"
                    condition_type = condition.get('type', 'Unknown')
                    print(f"{status_icon} {condition_type}: {condition.get('status', 'Unknown')}")
                
                # Test health endpoint
                if service_url:
                    health_ok = test_endpoint(service_url, "/health")
                    health_icon = "✅" if health_ok else "❌"
                    print(f"{health_icon} Health Check: {'PASS' if health_ok else 'FAIL'}")
                
                # Get recent logs (last 5 entries)
                print("\n📝 Recent Logs:")
                logs = run_gcloud_command(
                    f"gcloud run logs read --service={service_name} --region={region} --limit=3"
                )
                if logs:
                    log_lines = [line for line in logs.split('\n') if line.strip()]
                    for line in log_lines[-3:]:
                        if line.strip():
                            # Truncate long lines
                            display_line = line[:120] + "..." if len(line) > 120 else line
                            print(f"  {display_line}")
                else:
                    print("  No recent logs available")
            
            print("\n" + "-" * 60)
            time.sleep(30)  # Check every 30 seconds
            
    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python monitor_deployment.py <service-name> <region>")
        print("Example: python monitor_deployment.py lyo-backend us-central1")
        sys.exit(1)
    
    service_name = sys.argv[1]
    region = sys.argv[2]
    
    # Check if requests is available
    try:
        import requests
    except ImportError:
        print("⚠️ 'requests' library not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
        import requests
    
    monitor_service(service_name, region)
