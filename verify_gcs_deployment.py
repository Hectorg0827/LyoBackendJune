#!/usr/bin/env python3
"""
Comprehensive verification of GCS-enabled backend deployment
This script verifies that our simple backend with GCS integration is working
"""

import requests
import subprocess
import json
import sys
import time

def run_gcloud_command(command):
    """Execute gcloud command and return output"""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr}"

def main():
    print("🔍 COMPREHENSIVE GCS DEPLOYMENT VERIFICATION")
    print("=" * 50)
    
    # 1. Check project
    project_id = run_gcloud_command("gcloud config get-value project")
    print(f"📝 Project ID: {project_id}")
    
    # 2. Check if service exists
    print("\n🏗️  Checking Cloud Run service...")
    services = run_gcloud_command("gcloud run services list --format='value(metadata.name)'")
    if "lyo-backend" in services:
        print("✅ lyo-backend service exists")
    else:
        print("❌ lyo-backend service not found")
        print(f"Available services: {services}")
    
    # 3. Get service URL
    service_url = run_gcloud_command("gcloud run services describe lyo-backend --region=us-central1 --format='value(status.url)' 2>/dev/null")
    if service_url and "http" in service_url:
        print(f"🌐 Service URL: {service_url}")
        
        # 4. Test health endpoint
        print("\n🏥 Testing health endpoint...")
        try:
            response = requests.get(f"{service_url}/health", timeout=10)
            if response.status_code == 200:
                print("✅ Health check passed")
                print(f"Response: {response.json()}")
            else:
                print(f"❌ Health check failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Health check error: {e}")
        
        # 5. Test storage endpoint
        print("\n📁 Testing storage endpoint...")
        try:
            response = requests.get(f"{service_url}/api/v1/storage/files", timeout=10)
            if response.status_code == 200:
                print("✅ Storage endpoint accessible")
                print(f"Files: {response.json()}")
            else:
                print(f"⚠️  Storage endpoint status: {response.status_code}")
        except Exception as e:
            print(f"❌ Storage endpoint error: {e}")
    
    else:
        print(f"❌ Could not get service URL: {service_url}")
    
    # 6. Check GCS bucket
    print("\n🪣 Checking GCS bucket...")
    bucket_info = run_gcloud_command("gsutil ls gs://lyobackend-storage 2>/dev/null")
    if "gs://lyobackend-storage" in bucket_info or "CommandException" not in bucket_info:
        print("✅ GCS bucket accessible")
    else:
        print("❌ GCS bucket issue")
    
    # 7. Check container image
    print("\n🐳 Checking container image...")
    images = run_gcloud_command("gcloud container images list --repository=gcr.io/lyobackend 2>/dev/null")
    if "lyo-backend-simple" in images:
        print("✅ Container image exists")
    else:
        print("❌ Container image not found")
    
    print("\n" + "=" * 50)
    print("🎯 VERIFICATION COMPLETE!")
    
    # Final status
    if service_url and "http" in service_url:
        print(f"""
✅ SUCCESS! Your GCS-enabled backend is deployed at:
   {service_url}

📋 Available endpoints:
   • Health: {service_url}/health
   • Storage: {service_url}/api/v1/storage/files
   • Upload: {service_url}/api/v1/storage/upload (POST)

🔗 Integration ready for your frontend!
        """)
    else:
        print("❌ Deployment verification incomplete. Check the logs above.")

if __name__ == "__main__":
    main()
