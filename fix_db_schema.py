#!/usr/bin/env python3
"""Fix missing columns in production DB to match SQLAlchemy models."""
import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5433,
    user='lyoapp_user', password='LyoAppSecurePass2025',
    database='lyo_app'
)
conn.autocommit = True
cur = conn.cursor()

# Missing lesson columns
stmts = [
    "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS topic VARCHAR(200)",
    "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS tags JSONB",
    "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS difficulty_score FLOAT",
    "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS generation_prompt TEXT",
    "CREATE INDEX IF NOT EXISTS ix_lessons_topic ON lessons (topic)",
]

for s in stmts:
    print(f"  Running: {s[:60]}...")
    cur.execute(s)

# Verify
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'lessons' ORDER BY ordinal_position")
lesson_cols = [r[0] for r in cur.fetchall()]
print(f"\nLessons columns ({len(lesson_cols)}): {lesson_cols}")

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'courses' ORDER BY ordinal_position")
course_cols = [r[0] for r in cur.fetchall()]
print(f"Courses columns ({len(course_cols)}): {course_cols}")

print("\nDone!")
conn.close()
