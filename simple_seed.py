#!/usr/bin/env python3
"""
🌱 Simple Database Seeder for LyoBackend
Creates essential fake users for testing without complex dependencies.
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
import random

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from faker import Faker
    fake = Faker()
    print("✅ Faker imported successfully")
except ImportError:
    print("❌ Faker not available, using simple fake data")
    fake = None

async def simple_seed():
    """Create simple fake users."""
    print("🌱 Starting Simple Database Seeding...")
    
    try:
        # Import database components
        from lyo_app.core.database import init_db, AsyncSessionLocal
        from lyo_app.auth.service import AuthService
        from lyo_app.auth.schemas import UserCreate
        
        print("✅ Database imports successful")
        
        # Initialize database
        await init_db()
        print("✅ Database initialized")
        
        # Create session
        async with AsyncSessionLocal() as session:
            auth_service = AuthService()
            
            # Demo users
            demo_users = [
                {
                    "email": "john.doe@demo.com",
                    "username": "johndoe", 
                    "first_name": "John",
                    "last_name": "Doe",
                    "password": "DemoPass123!"
                },
                {
                    "email": "jane.smith@demo.com",
                    "username": "janesmith",
                    "first_name": "Jane", 
                    "last_name": "Smith",
                    "password": "DemoPass123!"
                },
                {
                    "email": "alex.chen@demo.com",
                    "username": "alexchen",
                    "first_name": "Alex",
                    "last_name": "Chen", 
                    "password": "DemoPass123!"
                }
            ]
            
            created_users = []
            
            for user_data in demo_users:
                try:
                    user_create = UserCreate(
                        email=user_data["email"],
                        username=user_data["username"],
                        password=user_data["password"], 
                        confirm_password=user_data["password"],
                        first_name=user_data["first_name"],
                        last_name=user_data["last_name"]
                    )
                    
                    user = await auth_service.register_user(session, user_create)
                    created_users.append(user)
                    print(f"✅ Created user: {user.email}")
                    
                except Exception as e:
                    if "already" in str(e).lower():
                        print(f"⚠️  User already exists: {user_data['email']}")
                    else:
                        print(f"❌ Failed to create user {user_data['email']}: {e}")
                        continue
            
            # Create additional fake users if Faker is available
            if fake:
                print("\n🎭 Creating additional fake users...")
                
                for i in range(10):
                    try:
                        email = fake.email()
                        username = fake.user_name() + str(i)
                        first_name = fake.first_name()
                        last_name = fake.last_name()
                        
                        user_create = UserCreate(
                            email=email,
                            username=username,
                            password="TestPass123!",
                            confirm_password="TestPass123!",
                            first_name=first_name,
                            last_name=last_name
                        )
                        
                        user = await auth_service.register_user(session, user_create)
                        created_users.append(user)
                        
                        if i % 3 == 0:  # Log every 3rd user
                            print(f"✅ Created fake user: {user.email}")
                            
                    except Exception as e:
                        if "already" in str(e).lower():
                            continue  # Skip duplicates
                        else:
                            print(f"⚠️  Skipped user {i}: {e}")
                            continue
                
                # Create 20 power users with rich profiles
                print("\n🌟 Creating 20 power users with extensive content...")
                power_user_types = [
                    ("tech_leader", "Technology Leader", ["AI", "Machine Learning", "Leadership"]),
                    ("academic", "Professor", ["Research", "Education", "Science"]),
                    ("entrepreneur", "Serial Entrepreneur", ["Startups", "Business", "Innovation"]),
                    ("consultant", "Senior Consultant", ["Strategy", "Transformation", "Consulting"]),
                    ("designer", "Design Director", ["UX/UI", "Product Design", "Innovation"])
                ]
                
                power_users_created = 0
                for i in range(20):
                    try:
                        # Assign power user type
                        user_type, title, interests = random.choice(power_user_types)
                        
                        first_name = fake.first_name()
                        last_name = fake.last_name()
                        username = f"{first_name.lower()}.{last_name.lower()}.power{i}"
                        years_exp = random.randint(8, 25)
                        
                        # Create rich bio
                        bio = f"{title} with {years_exp}+ years experience in {', '.join(interests[:2])}. "
                        bio += f"Passionate about mentoring and sharing knowledge. "
                        bio += f"Specialist in {random.choice(interests)}."
                        
                        power_user_data = UserCreate(
                            email=f"{username}@company.com",
                            username=username,
                            password="PowerUser123!",
                            confirm_password="PowerUser123!",
                            first_name=first_name,
                            last_name=last_name
                        )
                        
                        user = await auth_service.register_user(session, power_user_data)
                        created_users.append(user)
                        
                        # Update user with bio and verification
                        user.bio = bio
                        user.is_verified = True
                        user.last_login = fake.date_time_between(start_date='-3d', end_date='now')
                        
                        await session.commit()
                        power_users_created += 1
                        
                        if i % 5 == 0:  # Log every 5th power user
                            print(f"   🌟 Created power user: {user.username} ({title})")
                        
                    except Exception as e:
                        print(f"   ⚠️ Failed to create power user {i}: {e}")
                        continue
                
                print(f"✅ Created {power_users_created} power users")
            
            print(f"\n🎉 SUCCESS! Created {len(created_users)} users")
            print("\n🎭 DEMO USERS FOR TESTING:")
            print("   📧 john.doe@demo.com (Password: DemoPass123!)")
            print("   📧 jane.smith@demo.com (Password: DemoPass123!)")
            print("   📧 alex.chen@demo.com (Password: DemoPass123!)")
            print("\n🌟 POWER USERS FOR TESTING:")
            print("   📧 Use any *.power*@company.com (Password: PowerUser123!)")
            print("   💡 Power users have rich bios and verified status")
            print("\n🚀 NEXT STEPS:")
            print("   1. Start server: python3 start_server.py")
            print("   2. Test with demo users above")
            print("   3. Access API: http://localhost:8000/docs")
            
            return True
    
    except Exception as e:
        print(f"❌ Seeding failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main function."""
    success = await simple_seed()
    return success

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 Seeding cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
