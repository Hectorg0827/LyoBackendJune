# Firebase Authentication Fix - January 6, 2026

## Critical Issues Identified

### 1. Backend Configuration Error ✅ FIXED
**Error**: `name 'PostgresDsn' is not defined` in `/lyo_app/core/config_v2.py`

**Root Cause**: Missing imports for Pydantic types

**Fix Applied**: Added missing imports to `config_v2.py`:
```python
from pydantic import PostgresDsn, RedisDsn
```

### 2. API Endpoint Mismatch ⚠️ NEEDS iOS FIX
**Error**: iOS calling `/api/v1/posts/feed` returns 404

**Root Cause**: Backend has `/api/v1/feed` NOT `/api/v1/posts/feed`

**Available Endpoints**:
- ✅ `/api/v1/feed` - Main feed endpoint
- ✅ `/feed` - Alternative feed endpoint  
- ❌ `/api/v1/posts/feed` - Does NOT exist

**iOS Fix Required**: Update [LyoRepository.swift](file:///Users/hectorgarcia/LYO_Da_ONE/Sources/Services/LyoRepository.swift) line ~1108:
```swift
// WRONG:
return try await get(endpoint: "/api/v1/posts/feed?\(query)")

// CORRECT:
return try await get(endpoint: "/api/v1/feed?\(query)")
```

### 3. Authentication Flow Issue
**Problem**: User not logged in on backend after Firebase auth

**Flow**:
1. ✅ Firebase auth succeeds on iOS
2. ❌ `/auth/firebase` endpoint fails with PostgresDsn error
3. ❌ Fallback login fails (401 - invalid credentials)
4. ❌ Registration fails (400 - email already registered)
5. ❌ User ends up unauthenticated

**Result**: All protected endpoints return 401

## Deployment Steps

### Step 1: Deploy Backend Fix
```bash
cd /Users/hectorgarcia/Desktop/LyoBackendJune
gcloud builds submit --config=cloudbuild.yaml --project=lyoapp-460f2
```

### Step 2: Fix iOS Endpoint
Update `Sources/Services/LyoRepository.swift`:
```swift
// Line ~1108 - Fix feed endpoint
func getPosts(page: Int, limit: Int, algorithm: String?) async throws -> RepoFeedResponse {
    var query = "limit=\(limit)&offset=\((page - 1) * limit)"
    if let alg = algorithm { query += "&algorithm=\(alg)" }
    // FIX: Change from /api/v1/posts/feed to /api/v1/feed
    return try await get(endpoint: "/api/v1/feed?\(query)")
}
```

### Step 3: Test Authentication Flow
After deployment:
1. Clear app data (delete and reinstall)
2. Sign in with Google
3. Verify backend auth succeeds
4. Check feed loads successfully

## Backend Endpoints (Reference)

### Working Endpoints
- ✅ `/api/v1/chat/courses` - Returns empty array (working)
- ✅ `/api/v1/ai/chat` - Public endpoint (working)
- ✅ `/api/v1/feed` - Feed endpoint (correct path)

### Broken Endpoints (404)
- ❌ `/api/v1/posts/feed` - Does not exist

### Protected Endpoints (Require Auth)
- 🔒 `/stack/items` - Returns 401 if not authenticated
- 🔒 `/api/v1/ai/recommendations/profile` - Returns 401 if not authenticated

## Expected Behavior After Fix

1. ✅ Firebase authentication succeeds
2. ✅ Backend `/auth/firebase` returns JWT token
3. ✅ User authenticated on backend
4. ✅ Protected endpoints return data
5. ✅ Feed loads successfully
6. ✅ Stack items load
7. ✅ App fully functional

## Testing Checklist

- [ ] Backend deployed with config fix
- [ ] iOS feed endpoint updated  
- [ ] Firebase auth returns 200 (not 500)
- [ ] User receives JWT token
- [ ] `/stack/items` returns 200 (not 401)
- [ ] `/api/v1/feed` returns 200 (not 404)
- [ ] Feed displays content
- [ ] No 401/404 errors in logs

## Root Cause Analysis

The production backend was using `config_v2.py` which had incomplete Pydantic imports. This caused a runtime error during Firebase authentication initialization, breaking the entire auth flow and leaving users unable to log in.

The iOS app also had endpoint mismatches from outdated API documentation.

## Prevention

1. Add type checking to CI/CD
2. Keep iOS endpoint constants in sync with backend OpenAPI spec
3. Add integration tests for auth flow
4. Monitor Firebase auth error rates in production
