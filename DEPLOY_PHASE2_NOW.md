# 🚀 Deploy Phase 2 - Step by Step Guide

**Current Status:** ✅ Code ready, tests passed
**Branch:** claude/analyze-test-coverage-0L5Nz
**Latest Commit:** 499ff6b

---

## Pre-Deployment Checklist

```bash
# Verify you're on the right branch
git branch --show-current
# Should show: claude/analyze-test-coverage-0L5Nz

# Verify all commits are present
git log --oneline -3
# Should show:
# 499ff6b docs: Add comprehensive Phase 2 test and validation report
# 75b95fc fix: Replace numpy dependency with Python stdlib statistics
# 5aea348 feat: Implement Phase 2 - Predictive Intelligence System
```

---

## Option 1: Quick Deploy (Development/Staging)

### Step 1: Install Dependencies

```bash
# Install Python dependencies
pip install sqlalchemy[asyncio] aiosqlite alembic

# Or if you have a requirements.txt:
pip install -r requirements.txt
```

### Step 2: Run Database Migration

```bash
# Check current migration status
python -m alembic current

# Run Phase 2 migration
python -m alembic upgrade phase2_001

# Verify migration succeeded
python -m alembic current
# Should show: phase2_001 (head)
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade phase1_001 -> phase2_001
INFO  Created table struggle_predictions
INFO  Created table dropout_risk_scores
INFO  Created table user_timing_profiles
INFO  Created table learning_plateaus
INFO  Created table skill_regressions
```

### Step 3: Restart Application

```bash
# If using systemd
sudo systemctl restart lyo-backend

# If using Docker
docker-compose restart lyo-backend

# If running manually with uvicorn
# Press Ctrl+C to stop, then:
python -m uvicorn lyo_app.app_factory:create_app --reload --host 0.0.0.0 --port 8000
```

### Step 4: Verify Deployment

Check application logs for Phase 2 initialization:

```bash
# If using systemd
journalctl -u lyo-backend -f | grep "Phase 2"

# If using Docker
docker logs lyo-backend -f | grep "Phase 2"

# If running manually
# Check console output for:
# ✅ Phase 2: Predictive Intelligence enabled
```

You should see:
```
INFO: ✅ Phase 2: Predictive Intelligence enabled
```

### Step 5: Test API Endpoint

```bash
# Get a valid auth token first (use your existing user credentials)
TOKEN="your_jwt_token_here"

# Test the insights endpoint
curl -X GET "http://localhost:8000/api/v1/predictive/insights" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

Expected response (for new users with minimal data):
```json
{
  "user_id": 123,
  "dropout_risk": {
    "risk_score": 0.0,
    "risk_level": "low",
    "risk_factors": []
  },
  "active_plateaus": [],
  "skill_regressions": [],
  "timing_profile": null,
  "is_good_time_now": false,
  "total_insights": 0,
  "priority_actions": [],
  "generated_at": "2025-01-01T12:00:00Z"
}
```

---

## Option 2: Production Deploy (Recommended)

### Step 1: Merge to Main Branch

```bash
# Switch to main branch
git checkout main

# Merge Phase 2 changes
git merge claude/analyze-test-coverage-0L5Nz

# Push to remote
git push origin main
```

### Step 2: Create Production Release

```bash
# Tag the release
git tag -a v2.0.0-phase2 -m "Phase 2: Predictive Intelligence System"

# Push tags
git push origin v2.0.0-phase2
```

### Step 3: Deploy to Production Server

```bash
# SSH to production server
ssh your-production-server

# Navigate to app directory
cd /path/to/LyoBackendJune

# Pull latest code
git pull origin main

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt

# Backup database (IMPORTANT!)
pg_dump lyo_production > backup_before_phase2_$(date +%Y%m%d).sql

# Run migration
alembic upgrade phase2_001

# Restart application
sudo systemctl restart lyo-backend

# Monitor logs
tail -f /var/log/lyo/application.log
```

### Step 4: Verify Production Deployment

```bash
# Check health endpoint
curl https://your-domain.com/health

# Check Phase 2 enabled
curl -H "Authorization: Bearer $TOKEN" \
  https://your-domain.com/api/v1/predictive/insights
```

---

## Option 3: Docker Deployment

### Step 1: Update Docker Image

```bash
# Build new image with Phase 2
docker build -t lyo-backend:phase2 .

# Or if using docker-compose:
docker-compose build
```

### Step 2: Run Migration in Container

```bash
# Run migration
docker-compose run lyo-backend alembic upgrade phase2_001

# Or with docker:
docker run --rm lyo-backend:phase2 alembic upgrade phase2_001
```

### Step 3: Restart Services

```bash
# Restart with new image
docker-compose down
docker-compose up -d

# Check logs
docker-compose logs -f lyo-backend | grep "Phase 2"
```

---

## Rollback Plan (If Needed)

If something goes wrong:

### Rollback Migration

```bash
# Downgrade to Phase 1
alembic downgrade phase1_001

# Verify
alembic current
# Should show: phase1_001
```

### Rollback Code

```bash
# Switch back to previous commit
git checkout 5ca011e  # Before Phase 2

# Or revert the merge
git revert -m 1 <merge_commit_hash>
```

---

## Post-Deployment Monitoring

### Week 1: Monitor These Metrics

```sql
-- Check prediction activity (run daily)
SELECT
    DATE(predicted_at) as date,
    COUNT(*) as predictions,
    AVG(confidence) as avg_confidence
FROM struggle_predictions
WHERE predicted_at > CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(predicted_at)
ORDER BY date;

-- Check for errors in predictions
SELECT COUNT(*) as error_count
FROM struggle_predictions
WHERE confidence < 0.5
  AND predicted_at > CURRENT_DATE - INTERVAL '1 day';

-- Monitor timing profile generation
SELECT
    CASE
        WHEN confidence >= 0.7 THEN 'High'
        WHEN confidence >= 0.5 THEN 'Medium'
        ELSE 'Low'
    END as confidence_level,
    COUNT(*) as users
FROM user_timing_profiles
GROUP BY confidence_level;
```

### Application Logs to Watch

```bash
# Watch for Phase 2 errors
tail -f /var/log/lyo/application.log | grep -E "(Phase 2|predictive|ERROR)"

# Monitor intervention generation
tail -f /var/log/lyo/application.log | grep "behavioral_triggers"
```

---

## Troubleshooting

### Issue: Migration fails with "relation already exists"

**Solution:** Tables may already exist from a previous partial migration
```bash
# Check what tables exist
psql -d lyo_db -c "\dt *predictions*"
psql -d lyo_db -c "\dt *dropout*"

# If tables exist but migration wasn't recorded:
alembic stamp phase2_001
```

### Issue: "Phase 2: Predictive Intelligence enabled" not in logs

**Cause:** Import error or module not found

**Solution:**
```bash
# Test imports manually
python3 << 'EOF'
from lyo_app.predictive import struggle_predictor, dropout_predictor, timing_optimizer
print("✅ All predictive modules import successfully")
EOF

# Check for import errors
python3 -c "from lyo_app.predictive.routes import router; print('✅ Routes OK')"
```

### Issue: API returns 500 errors

**Cause:** Database tables not created or missing dependencies

**Solution:**
```bash
# Verify tables exist
psql -d lyo_db -c "
SELECT tablename
FROM pg_tables
WHERE tablename IN (
    'struggle_predictions',
    'dropout_risk_scores',
    'user_timing_profiles',
    'learning_plateaus',
    'skill_regressions'
);
"

# Should return 5 rows

# If tables missing, run migration again:
alembic upgrade phase2_001
```

### Issue: Predictions always return neutral values

**Cause:** Insufficient user data (this is expected for new/inactive users)

**Expected:** Users need:
- 10+ lesson completions for struggle predictions
- 2+ weeks of activity for dropout risk
- 10+ sessions for timing profiles

**Not a bug** - System will learn as users generate more data

---

## Quick Verification Checklist

After deployment, verify:

- [ ] Migration completed successfully (`alembic current` shows `phase2_001`)
- [ ] Application started without errors
- [ ] Logs show "✅ Phase 2: Predictive Intelligence enabled"
- [ ] API endpoint `/api/v1/predictive/insights` returns 200 OK
- [ ] No errors in application logs
- [ ] Database tables exist (5 new tables)
- [ ] Phase 1 still works (ambient/proactive endpoints respond)

---

## Success Criteria

Phase 2 is successfully deployed when:

1. ✅ All 5 database tables created
2. ✅ Application starts with "Phase 2 enabled" in logs
3. ✅ API endpoints return valid responses (even if empty data)
4. ✅ No import or startup errors
5. ✅ Phase 1 functionality unchanged
6. ✅ First predictions generated within 24 hours (for active users)

---

## Next Steps After Deployment

### Day 1-7: Monitor & Validate
- Check logs daily for errors
- Verify predictions are being generated
- Monitor database table growth
- Test all 9 API endpoints manually

### Week 2-4: Collect Data
- Let system run to gather user behavior data
- Track prediction accuracy (when outcomes recorded)
- Monitor intervention engagement rates
- Identify any performance issues

### Month 2: Optimize
- Tune prediction weights based on actual accuracy
- Adjust risk thresholds based on intervention effectiveness
- Implement caching if needed
- Add background jobs for batch processing

---

## Support & Documentation

- **Implementation Guide:** `PHASE2_IMPLEMENTATION_GUIDE.md`
- **Quick Start:** `PHASE2_DEPLOYMENT_QUICKSTART.md`
- **Test Report:** `PHASE2_TEST_REPORT.md`
- **Architecture:** `INDISPENSABLE_AI_ARCHITECTURE.md`

---

## Ready to Deploy? 🚀

Choose your deployment option above and follow the steps carefully.

**Recommended for first-time deploy:** Start with **Option 1 (Quick Deploy)** on a staging/development environment to verify everything works before moving to production.

Good luck! 🎉
