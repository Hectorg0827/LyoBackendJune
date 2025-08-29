#!/usr/bin/env python3
"""
⚡ Quick Power Users Creator
Adds 20 power users to existing database without complex initialization.
"""

import sqlite3
import random
import os
from datetime import datetime, timedelta

try:
    from faker import Faker
    fake = Faker()
    print("✅ Faker imported successfully")
except ImportError:
    print("❌ Faker not available")
    exit(1)

def create_power_users():
    """Create 20 power users directly in SQLite database."""
    print("🌟 Creating 20 power users with rich content...")
    
    # Database path
    db_path = "lyo_app_dev.db"
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        print("   Please run simple_seed.py first to create the database")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if users table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        if not cursor.fetchone():
            print("❌ Users table not found. Please run simple_seed.py first.")
            return False
        
        # Power user archetypes
        power_types = [
            ("tech_leader", "Technology Leader", "AI, Machine Learning, Leadership"),
            ("academic", "Professor & Researcher", "Research, Education, Data Science"),
            ("entrepreneur", "Serial Entrepreneur", "Startups, Business, Innovation"),
            ("consultant", "Senior Strategy Consultant", "Digital Transformation, Strategy"),
            ("designer", "Creative Design Director", "UX/UI, Product Design, Innovation"),
        ]
        
        created_count = 0
        
        for i in range(20):
            try:
                # Select power user type
                user_type, title, interests = random.choice(power_types)
                
                first_name = fake.first_name()
                last_name = fake.last_name()
                username = f"{first_name.lower()}.{last_name.lower()}.power{i}"
                email = f"{username}@company.com"
                years_exp = random.randint(8, 25)
                
                # Create rich bio
                bio = f"{title} with {years_exp}+ years experience in {interests}. "
                bio += f"Passionate about mentoring and sharing knowledge in cutting-edge technologies. "
                bio += f"Has led teams of 50+ people and built systems used by millions."
                
                # Hash password (simple for demo - in production use proper hashing)
                password_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6hsrHnNgfK"  # PowerUser123!
                
                # Insert power user
                cursor.execute("""
                    INSERT INTO users (
                        email, username, hashed_password, first_name, last_name, 
                        bio, is_verified, is_active, is_superuser, created_at, updated_at, last_login
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    email, username, password_hash, first_name, last_name,
                    bio, True, True, False,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                    (datetime.utcnow() - timedelta(days=random.randint(0, 7))).isoformat()
                ))
                
                created_count += 1
                
                if i % 5 == 0:
                    print(f"   🌟 Created: {username} ({title})")
                
            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" in str(e):
                    print(f"   ⚠️ User {i} already exists, skipping...")
                    continue
                else:
                    print(f"   ❌ Error creating user {i}: {e}")
                    continue
            except Exception as e:
                print(f"   ❌ Error creating user {i}: {e}")
                continue
        
        # Commit all changes
        conn.commit()
        
        # Verify creation
        cursor.execute("SELECT COUNT(*) FROM users WHERE email LIKE '%@company.com'")
        power_user_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        print(f"\n🎉 SUCCESS!")
        print(f"   Created {created_count} new power users")
        print(f"   Total power users in database: {power_user_count}")
        print(f"   Total users in database: {total_users}")
        
        print(f"\n🌟 POWER USERS FOR TESTING:")
        cursor.execute("SELECT username, email FROM users WHERE email LIKE '%@company.com' LIMIT 5")
        sample_users = cursor.fetchall()
        
        for username, email in sample_users:
            print(f"   📧 {email} (Password: PowerUser123!)")
        
        print(f"\n🚀 NEXT STEPS:")
        print(f"   1. Start server: python3 start_server.py")
        print(f"   2. Login with power users above")
        print(f"   3. Power users have rich bios and verified status")
        print(f"   4. Deploy updated database to production")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to create power users: {e}")
        if conn:
            conn.close()
        return False

def main():
    """Main function."""
    print("⚡ QUICK POWER USERS CREATOR")
    print("=" * 50)
    
    success = create_power_users()
    
    if success:
        print("\n" + "=" * 50)
        print("✅ Power users creation completed successfully!")
    else:
        print("\n" + "=" * 50)
        print("❌ Power users creation failed!")
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
