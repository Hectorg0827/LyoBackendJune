# 🌱 LyoBackend Database Seeding System

**Create realistic fake users and comprehensive test data for your LyoApp development and testing.**

## 🚀 Quick Start (Recommended)

```bash
# Create demo environment with essential test data
python3 quick_seed.py

# OR create comprehensive test environment 
python3 quick_seed.py --full
```

## 📋 What Gets Created

### 👥 Users
- **Demo Users**: 5 specific users with different roles for easy testing
- **Fake Users**: 15-50 realistic users with diverse profiles and interests
- **User Roles**: Students, Instructors, and Entrepreneurs with appropriate permissions

### 📚 Learning Content
- **Courses**: 5+ comprehensive courses across different subjects
- **Lessons**: 6+ lessons per course with realistic content
- **Enrollments**: Users enrolled in courses based on their interests
- **Completions**: Realistic lesson completion patterns

### 💬 Social Features
- **Posts**: Engaging social media posts with relevant hashtags
- **Comments**: Thoughtful comments and discussions
- **Reactions**: Likes and reactions on posts and comments
- **Follows**: Users following others with similar interests

### 🎮 Gamification
- **XP System**: Experience points for various activities
- **Achievements**: 8+ achievements with different rarity levels
- **Streaks**: Learning and engagement streak tracking
- **Levels**: User levels based on total XP earned

### 👥 Community
- **Study Groups**: Active study groups for different subjects
- **Memberships**: Users joined to relevant study groups
- **Events**: Community events and workshops
- **Attendance**: Realistic event attendance patterns

### 🤖 AI Study Features
- **Study Sessions**: AI tutoring sessions with conversation history
- **Messages**: Realistic student questions and AI responses
- **Topics**: Diverse subjects matching user interests

## 🎭 Demo Users (Easy Testing)

After seeding, you can immediately test with these pre-created users:

| Email | Username | Role | Password | Description |
|-------|----------|------|----------|-------------|
| `john.doe@demo.com` | johndoe | Student | `DemoPass123!` | CS student interested in AI |
| `jane.smith@demo.com` | janesmith | Instructor | `DemoPass123!` | Data Science professor |
| `alex.chen@demo.com` | alexchen | Student | `DemoPass123!` | Entrepreneur building apps |
| `maria.gonzalez@demo.com` | mariagonzalez | Instructor | `DemoPass123!` | Language learning expert |
| `david.kim@demo.com` | davidkim | Student | `DemoPass123!` | Medical student using AI |

## 📖 Detailed Usage

### Basic Seeding Script

```bash
# Create 30 fake users with all content types
python3 seed_db.py

# Create 50 users and clear existing data
python3 seed_db.py --users 50 --clear-existing

# Create demo preset (5 demo users + 20 fake users)
python3 seed_db.py --preset demo

# Create comprehensive test environment
python3 seed_db.py --preset testing

# Skip certain content types
python3 seed_db.py --skip-social --skip-gamification
```

### Advanced Options

```bash
# Full help
python3 seed_db.py --help

# Verbose logging for debugging
python3 seed_db.py --verbose

# Development preset with balanced data
python3 seed_db.py --preset development
```

## ✅ Validation

Validate that seeding was successful:

```bash
# Run comprehensive validation
python3 validate_seed.py
```

This checks:
- Data integrity and relationships
- User authentication readiness
- Content completeness
- Gamification system functionality

## 🔧 Integration with GCP

After seeding your local database, upload to Google Cloud:

```bash
# Build and deploy with seeded data
docker build -t gcr.io/lyobackend/lyo-backend-seeded .
gcloud builds submit --tag gcr.io/lyobackend/lyo-backend-seeded

# Deploy to Cloud Run
gcloud run deploy lyo-backend \
  --image gcr.io/lyobackend/lyo-backend-seeded \
  --region us-central1 \
  --allow-unauthenticated
```

## 📊 Data Statistics

**Quick Seed (Default):**
- 20 total users (5 demo + 15 fake)
- 5 courses with 30+ lessons
- 50+ social posts with comments
- 200+ XP records and achievements
- 6 study groups with events
- 25+ AI study sessions

**Full Seed:**
- 55 total users (5 demo + 50 fake)
- 5 courses with comprehensive content
- 150+ social interactions
- 500+ gamification records
- Active community with events
- Rich AI interaction history

## 🛠️ Customization

### Adding New User Archetypes

Edit `seed_db.py` and modify the `archetypes` list:

```python
archetypes = [
    {"role": "your_role", "age_range": (20, 30), "interests": ["your", "interests"]},
    # ... existing archetypes
]
```

### Custom Course Content

Modify the `course_templates` in the `create_learning_content()` method:

```python
course_templates = [
    {
        "title": "Your Custom Course",
        "description": "Your course description",
        "category": "your_category",
        "difficulty": "beginner|intermediate|advanced",
        "lessons": ["Lesson 1", "Lesson 2", ...]
    }
]
```

### Adding Achievement Types

Edit the `achievements_data` in `_create_default_achievements()`:

```python
achievements_data = [
    {
        "name": "Your Achievement",
        "description": "Achievement description",
        "type": AchievementType.LEARNING,
        "rarity": AchievementRarity.COMMON,
        "xp_reward": 100,
        "criteria": {"your_criteria": 1}
    }
]
```

## 🐛 Troubleshooting

### Common Issues

1. **"ModuleNotFoundError"**: Make sure you're in the project root directory
2. **"Database connection failed"**: Ensure your database is set up and running
3. **"Foreign key constraint"**: Run `python3 setup_database.py` first
4. **"Faker import error"**: Install requirements: `pip install -r requirements.txt`

### Getting Help

1. Check validation results: `python3 validate_seed.py`
2. Look at seed logs: `tail -f seed_db.log`
3. Reset everything: Delete `lyo_app_dev.db` and run setup again

## 📈 Performance Tips

- Use `--clear-existing` to avoid duplicate data
- Start with demo preset for quick testing
- Use full preset only for comprehensive testing
- Run validation after seeding to ensure data quality

## 🎯 Best Practices

1. **Always validate** after seeding
2. **Use demo users** for initial testing
3. **Clear data** before re-seeding
4. **Backup production** data before seeding
5. **Test authentication** with demo accounts

## 🚀 Next Steps After Seeding

1. **Start the server**: `python3 start_server.py`
2. **Access API docs**: http://localhost:8000/docs
3. **Test with demo users** listed above
4. **Explore your populated app** with realistic data
5. **Deploy to production** when ready

---

**Happy Testing! 🎉**

Your LyoBackend is now populated with realistic users and comprehensive test data, ready for development and user testing!
