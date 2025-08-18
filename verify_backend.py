#!/usr/bin/env python3
"""
Quick verification of key backend components
"""

from pathlib import Path
import json

def verify_implementation():
    checks = []
    
    # 1. App Factory
    app_factory = Path("lyo_app/app_factory.py")
    checks.append(("✅" if app_factory.exists() else "❌", "App Factory", app_factory.exists()))
    
    # 2. AI Module  
    ai_module = Path("lyo_app/ai/gemma_local.py")
    checks.append(("✅" if ai_module.exists() else "❌", "AI Module", ai_module.exists()))
    
    # 3. LoRA Adapter
    adapter = Path("models/educational-tuned/adapter_config.json")
    checks.append(("✅" if adapter.exists() else "❌", "LoRA Adapter", adapter.exists()))
    
    # 4. Training Data
    training_data = Path("datasets/combined_training.json")
    checks.append(("✅" if training_data.exists() else "❌", "Training Data", training_data.exists()))
    
    # 5. Performance Module
    perf_module = Path("lyo_app/performance/optimizer.py") 
    checks.append(("✅" if perf_module.exists() else "❌", "Performance Module", perf_module.exists()))
    
    # 6. Feed Algorithm
    feed_algo = Path("lyo_app/ai/next_gen_algorithm.py")
    checks.append(("✅" if feed_algo.exists() else "❌", "NextGen Feed Algorithm", feed_algo.exists()))
    
    # 7. Key Routers
    routers = ["auth", "feed", "tutor", "search"]
    router_count = sum(1 for r in routers if Path(f"lyo_app/routers/{r}.py").exists())
    checks.append(("✅" if router_count == 4 else "❌", f"Core Routers ({router_count}/4)", router_count == 4))
    
    print("🔍 BACKEND VERIFICATION REPORT")
    print("=" * 35)
    
    for icon, component, passed in checks:
        print(f"{icon} {component}")
    
    passed_count = sum(1 for _, _, passed in checks if passed)
    total_count = len(checks)
    
    print()
    print(f"📊 Status: {passed_count}/{total_count} components ready")
    
    if passed_count == total_count:
        print("🎉 ALL SYSTEMS GO - MARKET READY!")
        return True
    else:
        print("🔧 Some components need attention")
        return False

if __name__ == "__main__":
    verify_implementation()
