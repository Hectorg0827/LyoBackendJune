"""
Quick test script to verify community module integration.
"""

import sys
import traceback

# Test imports
def test_imports():
    """Test that all community components can be imported."""
    try:
        print("Testing imports...")
        
        # Test community models
        from lyo_app.community.models import StudyGroup, CommunityEvent
        print("✅ Community models imported")
        
        # Test community schemas
        from lyo_app.community.schemas import StudyGroupCreate, CommunityEventCreate
        print("✅ Community schemas imported")
        
        # Test community service
        from lyo_app.community.service import CommunityService
        print("✅ Community service imported")
        
        # Test community routes
        from lyo_app.community.routes import router
        print("✅ Community routes imported")
        print(f"   Router has {len(router.routes)} endpoints")
        
        # Test main app with community enabled
        from lyo_app.main import app
        print("✅ Main app with community routes imported")
        
        # Check community routes in main app
        community_paths = [route.path for route in app.routes if '/community/' in route.path]
        print(f"✅ Found {len(community_paths)} community routes in main app")
        
        return True
        
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        traceback.print_exc()
        return False

def test_basic_functionality():
    """Test basic functionality without database."""
    try:
        print("\nTesting basic functionality...")
        
        from lyo_app.community.schemas import StudyGroupCreate
        from lyo_app.community.models import StudyGroupPrivacy
        
        # Test schema creation
        group_data = StudyGroupCreate(
            name="Test Group",
            description="Test description",
            privacy=StudyGroupPrivacy.PUBLIC
        )
        print("✅ StudyGroup schema validation works")
        
        from lyo_app.community.service import CommunityService
        service = CommunityService()
        print("✅ CommunityService instantiation works")
        
        return True
        
    except Exception as e:
        print(f"❌ Functionality test failed: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Quick Community Module Test\n")
    
    import_success = test_imports()
    func_success = test_basic_functionality()
    
    if import_success and func_success:
        print("\n🎉 Community module integration successful!")
        print("✅ All components are properly connected")
        print("✅ Ready for full testing and usage")
    else:
        print("\n❌ Community module integration has issues")
        sys.exit(1)
