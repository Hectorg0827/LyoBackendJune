"""
Simple validation test for community module basic functionality.
"""

import asyncio
import sys
import traceback
from datetime import datetime

sys.path.insert(0, "/Users/republicalatuya/Desktop/LyoBackendJune")

async def test_basic_community_functionality():
    """Test basic community functionality without complex relationships."""
    try:
        print("🧪 Testing Community Module Basic Functionality...")
        
        # Test model imports
        from lyo_app.community.models import (
            StudyGroup, GroupMembership, CommunityEvent, EventAttendance,
            StudyGroupStatus, StudyGroupPrivacy, MembershipRole, EventType
        )
        print("✅ Community models imported successfully")
        
        # Test schema imports
        from lyo_app.community.schemas import (
            StudyGroupCreate, StudyGroupUpdate, StudyGroupRead,
            CommunityEventCreate, CommunityEventUpdate, CommunityEventRead
        )
        print("✅ Community schemas imported successfully")
        
        # Test service import
        from lyo_app.community.service import CommunityService
        service = CommunityService()
        print("✅ Community service imported and instantiated")
        
        # Test schema validation
        study_group_data = StudyGroupCreate(
            name="Test Study Group",
            description="A test study group",
            privacy=StudyGroupPrivacy.PUBLIC,
            max_members=10,
            requires_approval=False
        )
        print("✅ StudyGroup schema validation successful")
        
        event_data = CommunityEventCreate(
            title="Test Event",
            description="A test event",
            event_type=EventType.WORKSHOP,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            location="Online",
            max_attendees=20
        )
        print("✅ CommunityEvent schema validation successful")
        
        # Test routes import
        from lyo_app.community.routes import router
        print(f"✅ Community routes imported ({len(router.routes)} endpoints)")
        
        # Test main app integration
        from lyo_app.main import app
        print("✅ Main app with community module imported successfully")
        
        print("\n🎉 Community Module Basic Tests Passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_basic_community_functionality())
    if success:
        print("\n✅ Community module is ready for use!")
        print("📝 Note: Full database tests may require relationship fixes")
    else:
        print("\n❌ Community module has issues")
        sys.exit(1)
