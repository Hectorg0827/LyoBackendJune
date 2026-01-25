# iOS Course Generation Fix - JSON Parsing Error Solution

## Problem Summary

The iOS app was experiencing a `keyNotFound(CodingKeys(stringValue: "job_id", intValue: nil))` error when trying to parse course generation responses from the backend. This was preventing the AI Classroom from generating and displaying course content, resulting in blank screens.

## Root Cause

1. **Backend validation was too restrictive**: Required 10+ characters but iOS sent short topics like "Biology" (7 characters)
2. **Missing Swift models**: The iOS app didn't have proper `Codable` structs to parse the course generation job response format
3. **Incorrect field mapping**: The backend returns `job_id` but the iOS models weren't configured to handle this field

## Backend Response Format

The backend course generation endpoint `/api/v2/courses/generate` returns:

```json
{
    "job_id": "cg_20260123015812_0f22c729",
    "status": "accepted",
    "quality_tier": "balanced",
    "estimated_cost_usd": 0.12,
    "message": "Course generation started. Poll /status/{job_id} for updates.",
    "poll_url": "/api/v2/courses/status/cg_20260123015812_0f22c729"
}
```

## Solution Implementation

### 1. Backend Fix (✅ Already Applied)

Changed validation in `/lyo_app/ai_agents/multi_agent_v2/routes.py`:
```python
# Before (causing 422 errors)
request: str = Field(..., min_length=10, max_length=2000)

# After (accepting short topics)
request: str = Field(..., min_length=3, max_length=2000)
```

### 2. iOS Swift Models (✅ Created)

Created proper Swift models in `CourseGenerationService.swift`:

```swift
struct CourseGenerationJobResponse: Codable {
    let jobId: String
    let status: String
    let qualityTier: String
    let estimatedCostUsd: Double
    let message: String
    let pollUrl: String

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"           // 🔑 Critical: Maps job_id to jobId
        case status
        case qualityTier = "quality_tier"
        case estimatedCostUsd = "estimated_cost_usd"
        case message
        case pollUrl = "poll_url"
    }
}
```

### 3. Complete Service Implementation (✅ Created)

The new `CourseGenerationService.swift` includes:

- ✅ **Proper JSON parsing** with `job_id` field mapping
- ✅ **Full course generation workflow** (submit → poll → retrieve)
- ✅ **Comprehensive models** for courses, modules, lessons, quizzes
- ✅ **Error handling** for network and parsing issues
- ✅ **Progress tracking** with real-time status updates

### 4. UI Integration (✅ Created)

The new `LiveClassroomView.swift` provides:

- ✅ **User-friendly interface** for course generation
- ✅ **Real-time progress tracking** with visual indicators
- ✅ **Rich course display** with modules and lessons
- ✅ **Proper error handling** and user feedback

## Integration Steps for iOS Developers

### Step 1: Add the Service Files

1. Copy `ios_integration/CourseGenerationService.swift` to your iOS project:
   ```
   Lyo/Services/CourseGenerationService.swift
   ```

2. Copy `ios_integration/LiveClassroomView.swift` to your iOS project:
   ```
   Lyo/Views/LiveClassroom/LiveClassroomView.swift
   ```

### Step 2: Update Your API Client

Ensure your `LyoAppAPIClient` has the base URL configured:

```swift
// In your existing LyoAppAPIClient
private let baseURL = "https://lyo-backend-production-830162750094.us-central1.run.app"

func createRequest(for endpoint: String, method: HTTPMethod) -> URLRequest {
    let url = URL(string: baseURL + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = method.rawValue
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("Bearer your-auth-token", forHTTPHeaderField: "Authorization")
    return request
}
```

### Step 3: Replace Existing Course Generation Logic

If you have existing course generation code causing the `job_id` error:

1. **Remove** any old course generation ViewModels or Services
2. **Replace** with the new `CourseGenerationViewModel`
3. **Update** any navigation to use `LiveClassroomView()`

### Step 4: Test the Integration

1. Launch the app and navigate to AI Classroom
2. Enter a short topic like "Biology" or "Math"
3. Verify the course generation starts without JSON parsing errors
4. Confirm the progress indicator shows real-time updates
5. Check that completed courses display with modules and lessons

## Backend Endpoints Used

- `POST /api/v2/courses/generate` - Submit course generation job
- `GET /api/v2/courses/status/{job_id}` - Poll job status
- `GET /api/v2/courses/{job_id}/result` - Get completed course

## Testing Commands

Test the backend is working:

```bash
# Test course generation (should return job_id)
curl -X POST "https://lyo-backend-production-830162750094.us-central1.run.app/api/v2/courses/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token" \
  -d '{"request": "Biology", "difficulty": "intermediate", "estimated_hours": 2.0}'

# Expected response:
# {"job_id":"cg_...", "status":"accepted", ...}
```

## Key Differences from Previous Implementation

| Issue | Before | After |
|-------|--------|-------|
| **Validation** | Required 10+ chars → 422 errors | Accepts 3+ chars ✅ |
| **JSON Parsing** | Missing job_id model → crash | Proper CodingKeys mapping ✅ |
| **Error Handling** | Silent failures | Clear error messages ✅ |
| **User Experience** | Blank screens | Rich progress tracking ✅ |
| **Course Display** | Plain text only | Interactive modules & lessons ✅ |

## Verification Checklist

- [ ] Backend accepts short topics (3+ characters) without 422 errors
- [ ] iOS app parses `job_id` field without JSON decoding crashes
- [ ] Course generation shows progress indicators
- [ ] Completed courses display with structured content
- [ ] Error messages are user-friendly and actionable
- [ ] Navigation and UI flow works smoothly

## Production Deployment

The backend fix is already deployed. iOS developers need to:

1. **Deploy the new Swift files** in your next app release
2. **Remove old course generation code** that was causing crashes
3. **Test thoroughly** with various topic lengths and difficulties
4. **Monitor** for any remaining JSON parsing issues

## Success Metrics

After implementing this fix, you should see:

- ✅ **Zero `job_id` JSON parsing errors** in crash reports
- ✅ **Successful course generation** for short topics like "Biology", "Math"
- ✅ **Rich interactive courses** instead of blank screens
- ✅ **Real-time progress tracking** during generation
- ✅ **Higher user engagement** with AI Classroom feature

The iOS app will now properly handle the complete course generation workflow from topic submission through course completion, with full error handling and progress tracking.