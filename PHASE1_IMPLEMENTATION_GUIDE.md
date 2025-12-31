# Phase 1 Implementation Guide: Ambient Presence & Proactive Companion

This guide walks you through integrating Phase 1 of the Indispensable AI Architecture into your LyoApp backend.

## What's Included

Phase 1 adds two core systems:

1. **Ambient Presence System** - Makes Lyo always accessible
   - Quick access from anywhere (Cmd+K palette)
   - Contextual inline help
   - Presence tracking

2. **Proactive Intervention System** - Makes Lyo reach out first
   - Time-based interventions (morning rituals, evening reflections)
   - Event-based interventions (streak preservation, milestones)
   - Smart notification management

## Prerequisites

- PostgreSQL database
- FastAPI backend
- SQLAlchemy with async support
- Existing auth system (JWT)

## Step 1: Run Database Migration

First, update the Alembic migration file to point to your latest migration:

```bash
# Edit alembic/versions/phase1_001_ambient_and_proactive.py
# Change this line:
down_revision = None  # Update this to your latest migration ID

# For example:
down_revision = 'production_001_initial_schema'  # Your latest migration
```

Then run the migration:

```bash
# Apply migration
alembic upgrade head

# Verify tables were created
psql -d your_database -c "\dt *ambient*"
psql -d your_database -c "\dt *intervention*"
```

You should see these new tables:
- `ambient_presence_states`
- `inline_help_logs`
- `intervention_logs`
- `user_notification_preferences`

## Step 2: Register Routes

Add the new routes to your main FastAPI application.

### Option A: Update `app_factory.py` (Recommended)

```python
# lyo_app/app_factory.py

from lyo_app.ambient.routes import router as ambient_router
from lyo_app.proactive.routes import router as proactive_router

def create_app(...):
    app = FastAPI(...)

    # ... existing routers ...

    # Phase 1: Ambient Presence & Proactive Interventions
    app.include_router(ambient_router)
    app.include_router(proactive_router)

    return app
```

### Option B: Update `main.py` Directly

```python
# lyo_app/main.py

from fastapi import FastAPI
from lyo_app.ambient.routes import router as ambient_router
from lyo_app.proactive.routes import router as proactive_router

app = FastAPI()

# ... existing routers ...

app.include_router(ambient_router)
app.include_router(proactive_router)
```

## Step 3: Start Background Scheduler

The proactive intervention system needs a background job to evaluate interventions every 5 minutes.

### Option A: Using FastAPI Startup Event

```python
# lyo_app/main.py or app_factory.py

import asyncio
from lyo_app.proactive.scheduler import start_proactive_scheduler

@app.on_event("startup")
async def startup_event():
    # Start proactive scheduler in background
    asyncio.create_task(start_proactive_scheduler())
    logger.info("Proactive intervention scheduler started")
```

### Option B: Separate Background Process

For production, you may want to run the scheduler in a separate process:

```python
# scheduler_worker.py (new file in root)

import asyncio
import logging
from lyo_app.proactive.scheduler import start_proactive_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting proactive intervention scheduler worker...")
    asyncio.run(start_proactive_scheduler())
```

Then run it separately:

```bash
python scheduler_worker.py &
```

### Option C: Using Celery (if you have it)

```python
# lyo_app/tasks/proactive_tasks.py

from celery import shared_task
from lyo_app.proactive.scheduler import proactive_scheduler
import asyncio

@shared_task
def evaluate_interventions():
    """Run every 5 minutes via Celery Beat"""
    asyncio.run(proactive_scheduler.run_intervention_evaluation())

@shared_task
def daily_reset():
    """Run once per day at midnight"""
    asyncio.run(proactive_scheduler.run_daily_reset())
```

Configure in Celery Beat:

```python
# celeryconfig.py

beat_schedule = {
    'evaluate-interventions': {
        'task': 'lyo_app.tasks.proactive_tasks.evaluate_interventions',
        'schedule': 300.0,  # Every 5 minutes
    },
    'daily-reset': {
        'task': 'lyo_app.tasks.proactive_tasks.daily_reset',
        'schedule': crontab(hour=0, minute=0),  # Midnight UTC
    },
}
```

## Step 4: Frontend Integration

### 4.1 Ambient Presence Widget

Update user's presence as they navigate:

```typescript
// Frontend: Track user presence

class PresenceTracker {
  private startTime: number = Date.now();
  private scrollCount: number = 0;

  async updatePresence(page: string, topic?: string, contentId?: string) {
    const timeOnPage = (Date.now() - this.startTime) / 1000; // seconds

    await fetch('/ambient/presence/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        page,
        topic,
        content_id: contentId,
        time_on_page: timeOnPage,
        scroll_count: this.scrollCount,
        mouse_hesitations: 0
      })
    });
  }

  onScroll() {
    this.scrollCount++;
  }
}

// Initialize on each page
const presenceTracker = new PresenceTracker();

// Update presence every 10 seconds
setInterval(() => {
  presenceTracker.updatePresence(
    getCurrentPage(),
    getCurrentTopic(),
    getCurrentContentId()
  );
}, 10000);
```

### 4.2 Inline Help

Check if inline help should be shown:

```typescript
// Frontend: Check for inline help

async function checkInlineHelp() {
  const response = await fetch('/ambient/inline-help/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_behavior: {
        time_on_section: 35, // seconds
        scroll_count: 4
      },
      current_context: {
        page: 'lesson',
        topic: 'calculus_derivatives'
      }
    })
  });

  const data = await response.json();

  if (data.should_show) {
    // Show inline help tooltip
    showInlineHelp(data.help_message);
  }
}
```

### 4.3 Quick Actions (Cmd+K Palette)

Get contextual quick actions:

```typescript
// Frontend: Quick actions palette

async function getQuickActions() {
  const response = await fetch('/ambient/quick-actions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      current_page: 'lesson',
      current_content: {
        current_concept: 'Derivatives'
      }
    })
  });

  const data = await response.json();
  return data.actions; // Show in Cmd+K palette
}

// Example Cmd+K implementation
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    showQuickActionsPalette(await getQuickActions());
  }
});
```

### 4.4 Proactive Interventions

Check for proactive interventions:

```typescript
// Frontend: Check for interventions

async function checkInterventions() {
  const response = await fetch('/proactive/interventions');
  const data = await response.json();

  if (data.count > 0) {
    // Show intervention(s) to user
    data.interventions.forEach(intervention => {
      showInterventionNotification(intervention);
    });
  }
}

// Check every minute
setInterval(checkInterventions, 60000);

// Or check on app focus
window.addEventListener('focus', checkInterventions);
```

### 4.5 Record User Response

When user interacts with intervention:

```typescript
// Frontend: Record intervention response

async function recordInterventionResponse(logId: number, response: string) {
  await fetch('/proactive/interventions/response', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      intervention_log_id: logId,
      user_response: response // 'engaged', 'dismissed', 'ignored', 'snoozed'
    })
  });
}

// Example: User clicks on intervention
interventionButton.onclick = async () => {
  await recordInterventionResponse(interventionLogId, 'engaged');
  // Navigate to action
  router.push(intervention.action);
};
```

## Step 5: User Notification Preferences

Allow users to customize their notification preferences:

```typescript
// Frontend: Notification preferences UI

async function getNotificationPreferences() {
  const response = await fetch('/proactive/preferences');
  return await response.json();
}

async function updateNotificationPreferences(prefs) {
  await fetch('/proactive/preferences', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dnd_enabled: prefs.dndEnabled,
      quiet_hours_start: prefs.quietStart, // "22:00:00"
      quiet_hours_end: prefs.quietEnd, // "08:00:00"
      max_notifications_per_day: prefs.maxPerDay,
      disabled_intervention_types: prefs.disabledTypes
    })
  });
}
```

## Step 6: Testing

### 6.1 Test Ambient Presence

```bash
# Update presence
curl -X POST http://localhost:8000/ambient/presence/update \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "page": "lesson",
    "topic": "calculus",
    "time_on_page": 35.5,
    "scroll_count": 4
  }'

# Check inline help
curl -X POST http://localhost:8000/ambient/inline-help/check \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_behavior": {"time_on_section": 35, "scroll_count": 4},
    "current_context": {"page": "lesson", "topic": "calculus"}
  }'

# Get quick actions
curl -X POST http://localhost:8000/ambient/quick-actions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "current_page": "lesson",
    "current_content": {"current_concept": "Derivatives"}
  }'
```

### 6.2 Test Proactive Interventions

```bash
# Get interventions for current user
curl -X GET http://localhost:8000/proactive/interventions \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get notification preferences
curl -X GET http://localhost:8000/proactive/preferences \
  -H "Authorization: Bearer YOUR_TOKEN"

# Update preferences
curl -X PUT http://localhost:8000/proactive/preferences \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "quiet_hours_start": "22:00:00",
    "quiet_hours_end": "08:00:00",
    "max_notifications_per_day": 3
  }'
```

## Step 7: Monitoring & Analytics

### Track Key Metrics

```sql
-- Daily intervention stats
SELECT
  intervention_type,
  COUNT(*) as total_sent,
  SUM(CASE WHEN user_response = 'engaged' THEN 1 ELSE 0 END) as engaged,
  SUM(CASE WHEN user_response = 'dismissed' THEN 1 ELSE 0 END) as dismissed,
  SUM(CASE WHEN user_response IS NULL THEN 1 ELSE 0 END) as ignored
FROM intervention_logs
WHERE triggered_at >= NOW() - INTERVAL '24 hours'
GROUP BY intervention_type;

-- Inline help effectiveness
SELECT
  help_type,
  COUNT(*) as shown,
  SUM(CASE WHEN user_response = 'accepted' THEN 1 ELSE 0 END) as accepted,
  SUM(CASE WHEN user_response = 'dismissed' THEN 1 ELSE 0 END) as dismissed
FROM inline_help_logs
WHERE shown_at >= NOW() - INTERVAL '7 days'
GROUP BY help_type;

-- User engagement with ambient features
SELECT
  DATE(last_seen_at) as date,
  COUNT(DISTINCT user_id) as active_users,
  AVG(quick_access_count_today) as avg_quick_access,
  AVG(inline_help_count_today) as avg_inline_help
FROM ambient_presence_states
WHERE last_seen_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(last_seen_at)
ORDER BY date DESC;
```

## Step 8: Production Checklist

Before deploying to production:

- [ ] Database migration applied successfully
- [ ] Routes registered in FastAPI app
- [ ] Background scheduler running (check logs)
- [ ] Frontend integration tested
- [ ] Notification preferences UI implemented
- [ ] Push notification service connected (if applicable)
- [ ] Monitoring queries set up
- [ ] Error logging configured
- [ ] Rate limiting considered (if needed)
- [ ] GDPR compliance reviewed (data collection, user preferences)

## Common Issues & Solutions

### Issue: Interventions not being triggered

**Check:**
1. Is the scheduler running? Check logs for "Starting intervention evaluation job"
2. Are there active users? Check `_get_active_users()` query
3. Are users' preferences blocking interventions? Check `user_notification_preferences`

**Debug:**
```python
# Add to scheduler.py for debugging
logger.debug(f"Active users: {[u.id for u in active_users]}")
logger.debug(f"Interventions for user {user.id}: {interventions}")
```

### Issue: Inline help showing too frequently

**Solution:** Adjust thresholds in `presence_manager.py`:

```python
self.TIME_THRESHOLD_SECONDS = 45  # Increase from 30
self.DAILY_INLINE_LIMIT = 3  # Decrease from 5
```

### Issue: Database session errors in background job

**Solution:** Ensure proper session management:

```python
# Use AsyncSessionLocal, not get_db()
async with AsyncSessionLocal() as db:
    # Do work
    await db.commit()
# Session automatically closed
```

## Next Steps: Phase 2

Once Phase 1 is working:
- **Predictive Intelligence** - Struggle prediction, dropout prevention
- **Optimal Timing** - Learn user's peak learning times
- **Enhanced Interventions** - Behavioral and emotional triggers

See `INDISPENSABLE_AI_ARCHITECTURE.md` for full roadmap.

## API Documentation

Full API documentation available at `/docs` once server is running.

Key endpoints:
- `POST /ambient/presence/update` - Update user presence
- `POST /ambient/inline-help/check` - Check if help should be shown
- `POST /ambient/quick-actions` - Get contextual actions
- `GET /proactive/interventions` - Get interventions for user
- `GET /proactive/preferences` - Get notification preferences
- `PUT /proactive/preferences` - Update notification preferences

## Support

For issues or questions:
1. Check logs: `tail -f logs/lyo_app.log`
2. Review database: `psql -d lyo_app`
3. Test endpoints: `curl` commands above
4. Refer to `INDISPENSABLE_AI_ARCHITECTURE.md` for architecture details
