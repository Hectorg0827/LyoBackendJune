#!/usr/bin/env python3
# API Validator - Quick validation tool for Lyo APIs
import requests
import json

def validate_api_endpoint(url, expected_status=200):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == expected_status:
            print(f"✅ {url} - Status {response.status_code}")
            return True
        else:
            print(f"❌ {url} - Status {response.status_code} (expected {expected_status})")
            return False
    except Exception as e:
        print(f"💥 {url} - Error: {e}")
        return False

if __name__ == "__main__":
    # Test main endpoints
    base_url = "http://localhost:8000"
    endpoints = ["/health", "/api/v1/status", "/api/v1/components"]

    print("🔍 Validating API endpoints...")
    results = [validate_api_endpoint(f"{base_url}{ep}") for ep in endpoints]
    success_rate = sum(results) / len(results) * 100
    print(f"\n📊 Validation complete: {success_rate}% success rate")
