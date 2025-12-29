"""
Quick integration script to add Gemini enhancement routers to enhanced_main.py

Run this script to automatically add the streaming and analytics routers.
"""

import re

def integrate_routers():
    main_file = "/Users/hectorgarcia/Desktop/LyoBackendJune/lyo_app/enhanced_main.py"
    
    # Code to insert
    new_routers = '''    
    # Multi-Agent V2 - Streaming Support (NEW - Gemini Enhancements)
    try:
        from lyo_app.ai_agents.multi_agent_v2.routes_streaming import streaming_router
        app.include_router(streaming_router)
        logger.info("✅ Multi-agent v2 streaming routes loaded - Real-time progress updates!")
    except ImportError as e:
        logger.warning(f"⚠️ Streaming routes not available: {e}")
    
    # Multi-Agent V2 - Analytics (NEW - Gemini Enhancements)
    try:
        from lyo_app.ai_agents.multi_agent_v2.routes_analytics import analytics_router
        app.include_router(analytics_router)
        logger.info("✅ Multi-agent v2 analytics routes loaded - Usage tracking active!")
    except ImportError as e:
        logger.warning(f"⚠️ Analytics routes not available: {e}")
'''
    
    # Read the file
    with open(main_file, 'r') as f:
        content = f.read()
    
    # Find the insertion point (after AI Tutor routes, before Tenant routes)
    pattern = r'(logger\.warning\(f"AI Tutor v2 routes not available: {e}"\)\s+# Multi-Tenant SaaS API)'
    
    # Insert the new routers
    new_content = re.sub(
        pattern,
        r'logger.warning(f"AI Tutor v2 routes not available: {e}")\n' + new_routers + '\n    # Multi-Tenant SaaS API',
        content,
        count=1
    )
    
    if new_content != content:
        # Backup original
        with open(main_file + '.backup', 'w') as f:
            f.write(content)
        
        # Write updated file
        with open(main_file, 'w') as f:
            f.write(new_content)
        
        print("✅ Successfully integrated streaming and analytics routers!")
        print(f"📁 Backup saved to: {main_file}.backup")
        print("\nAdded routers:")
        print("  - /api/v2/courses/generate/stream")
        print("  - /api/v2/courses/analytics/*")
    else:
        print("⚠️ Could not find insertion point. Please add manually.")
        print("\nAdd these lines after the AI Tutor routes section:")
        print(new_routers)

if __name__ == "__main__":
    integrate_routers()
