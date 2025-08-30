#!/usr/bin/env python3
"""
🚀 Quick Database Seeding Script
One-click solution to populate your LyoBackend with realistic test data.

This creates everything you need for app development and testing:
- Demo users with different roles (student, instructor, admin)
- Diverse learning content (courses, lessons, enrollments)
- Social interactions (posts, comments, likes, follows)
- Study groups and community events
- Gamification data (XP, achievements, streaks)
- AI study sessions and interactions

Usage:
    python3 quick_seed.py           # Creates demo environment
    python3 quick_seed.py --full    # Creates comprehensive test data
"""

import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from seed_db import DatabaseSeeder
import logging

# Simple logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


async def quick_demo_seed():
    """Create a quick demo environment."""
    logger.info("🌟 Creating LyoBackend Demo Environment...")
    logger.info("This will create demo users and essential test data.")
    
    seeder = DatabaseSeeder()
    
    try:
        # Initialize
        if not await seeder.initialize():
            logger.error("❌ Failed to initialize database")
            return False
        
        # Clear existing data
        logger.info("\n🗑️  Clearing existing data...")
        await seeder.clear_existing_data()
        
        # Create demo users
        logger.info("\n👥 Creating demo users...")
        await seeder.create_demo_users()
        
        # Add some fake users for diversity
        logger.info("\n🎭 Adding additional test users...")
        await seeder.create_fake_users(15)
        
        # Create essential content
        logger.info("\n📚 Creating learning content...")
        await seeder.create_learning_content(len(seeder.created_users))
        
        logger.info("\n💬 Creating social content...")
        await seeder.create_social_content()
        
        logger.info("\n🎮 Creating gamification data...")
        await seeder.create_gamification_data()
        
        logger.info("\n👥 Creating study groups...")
        await seeder.create_study_groups()
        
        logger.info("\n🤖 Creating AI study data...")
        await seeder.create_ai_study_data()
        
        # Print summary
        await seeder.print_summary()
        
        logger.info("\n✨ SUCCESS! Your LyoBackend is now populated with demo data!")
        logger.info("🚀 You can now start your server and begin testing!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Demo seeding failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await seeder.close()


async def full_test_seed():
    """Create comprehensive test environment."""
    logger.info("🏗️  Creating Comprehensive Test Environment...")
    logger.info("This will create a large dataset for thorough testing.")
    
    seeder = DatabaseSeeder()
    
    try:
        # Initialize
        if not await seeder.initialize():
            logger.error("❌ Failed to initialize database")
            return False
        
        # Clear existing data
        logger.info("\n🗑️  Clearing existing data...")
        await seeder.clear_existing_data()
        
        # Create demo users first
        logger.info("\n🎭 Creating demo users...")
        await seeder.create_demo_users()
        
        # Create many fake users
        logger.info("\n👥 Creating 50 diverse users...")
        await seeder.create_fake_users(50)
        
        # Create all content types
        logger.info("\n📚 Creating comprehensive learning content...")
        await seeder.create_learning_content(len(seeder.created_users))
        
        logger.info("\n💬 Creating rich social content...")
        await seeder.create_social_content()
        
        logger.info("\n🎮 Creating complete gamification system...")
        await seeder.create_gamification_data()
        
        logger.info("\n👥 Creating active study groups...")
        await seeder.create_study_groups()
        
        logger.info("\n🤖 Creating AI study interactions...")
        await seeder.create_ai_study_data()
        
        # Print summary
        await seeder.print_summary()
        
        logger.info("\n🎉 SUCCESS! Comprehensive test environment created!")
        logger.info("🔬 Perfect for load testing and feature development!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Full seeding failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await seeder.close()


def print_help():
    """Print usage information."""
    print("""
🌱 LyoBackend Quick Seeding Tool

Usage:
    python3 quick_seed.py           # Demo environment (20 users)
    python3 quick_seed.py --full    # Full test environment (55 users)
    python3 quick_seed.py --help    # Show this help

What gets created:
✅ Realistic fake users with different roles and profiles
✅ Comprehensive learning content (courses, lessons, enrollments)
✅ Social interactions (posts, comments, likes, follows)
✅ Study groups and community events
✅ Gamification data (XP, achievements, streaks, levels)
✅ AI study sessions and interactions

Demo users created (for easy testing):
📧 john.doe@demo.com (Student)
📧 jane.smith@demo.com (Instructor) 
📧 alex.chen@demo.com (Entrepreneur)
📧 maria.gonzalez@demo.com (Language Teacher)
📧 david.kim@demo.com (Medical Student)

All demo users have password: DemoPass123!

After running:
1. Start your server: python3 start_server.py
2. Access API docs: http://localhost:8000/docs
3. Login with demo users above
4. Explore your populated app!
""")


async def main():
    """Main function."""
    if len(sys.argv) > 1:
        if sys.argv[1] in ["--help", "-h"]:
            print_help()
            return True
        elif sys.argv[1] == "--full":
            return await full_test_seed()
        else:
            logger.error(f"Unknown argument: {sys.argv[1]}")
            logger.info("Use --help for usage information")
            return False
    else:
        return await quick_demo_seed()


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n👋 Seeding cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)
