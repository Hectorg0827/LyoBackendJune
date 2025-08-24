#!/usr/bin/env python3
"""
Simple Production Test Runner
"""

import os
import sys
import subprocess
from datetime import datetime

def run_test():
    print("="*60)
    print("🚀 LYOBACKEND PRODUCTION SMOKE TEST".center(60))
    print("="*60)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    base_url = "http://localhost:8001"
    
    tests = [
        ("Root Endpoint", f'curl -s "{base_url}/" | grep -q "Production backend is running"'),
        ("Health Endpoint", f'curl -s "{base_url}/health" | grep -q "healthy"'),
        ("API Info", f'curl -s "{base_url}/api/v1" | grep -q "operational"'),
        ("Features", f'curl -s "{base_url}/api/v1/features" | grep -q "production_ready"'),
        ("Smoke Test", f'curl -s "{base_url}/api/v1/smoke-test" | grep -q "PASSED"'),
        ("Swagger Docs", f'curl -s -I "{base_url}/docs" | grep -q "200 OK"'),
        ("OpenAPI Schema", f'curl -s -I "{base_url}/openapi.json" | grep -q "200 OK"')
    ]
    
    passed = 0
    failed = 0
    
    print("\n" + "="*50)
    print("SERVER TESTS".center(50))
    print("="*50)
    
    for test_name, command in tests:
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ {test_name}")
                passed += 1
            else:
                print(f"❌ {test_name}")
                failed += 1
        except Exception as e:
            print(f"❌ {test_name}: {str(e)}")
            failed += 1
    
    print("\n" + "="*50)
    print("DATABASE/REDIS TESTS".center(50))
    print("="*50)
    
    # Test PostgreSQL connection
    try:
        result = subprocess.run(
            'psql postgresql://lyo_user:securepassword@localhost/lyo_production -c "SELECT 1;" >/dev/null 2>&1',
            shell=True, capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✅ PostgreSQL Connection")
            passed += 1
        else:
            print("❌ PostgreSQL Connection")
            failed += 1
    except:
        print("⚠️ PostgreSQL Connection (skipped - psql not available)")
    
    # Test Redis connection
    try:
        result = subprocess.run(
            'redis-cli ping >/dev/null 2>&1',
            shell=True, capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✅ Redis Connection")
            passed += 1
        else:
            print("❌ Redis Connection")
            failed += 1
    except:
        print("⚠️ Redis Connection (skipped - redis-cli not available)")
    
    print("\n" + "="*50)
    print("RESULTS SUMMARY".center(50))
    print("="*50)
    
    total = passed + failed
    success_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"📊 Success Rate: {success_rate:.1f}%")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Total: {total}")
    
    if failed == 0:
        print(f"\n🎉 ALL TESTS PASSED!")
        print("🚀 Production backend is ready for deployment!")
        return 0
    else:
        print(f"\n⚠️ Some tests failed.")
        print("🔧 Please review issues above.")
        return 1

if __name__ == "__main__":
    exit_code = run_test()
    sys.exit(exit_code)
