# Unified Test Prep

All authenticated entry points use `GET /api/v1/me/study_plans/state`,
`POST /intake/turn`, and idempotent `POST /plans/generate`. Chat delegates to
the same intake and generation handlers; iOS no longer runs its local funnel.

## Contract

- Opening a screen reads state without creating a profile or posting a turn.
- A turn without a profile ID resumes the account's latest profile.
- Intake accepts a stable `request_id`, IANA `timezone`, and uploaded media
  references. Retry receipts are stored in `TestProfile.workflow_state`.
- The server locks the user for first-profile creation and the profile for
  generation and editing. A second generation call returns the existing plan.
- `PATCH /profiles/{id}` requires `expected_revision`; stale edits return 409.
  Schedule edits archive the old plan and cancel its pending reminders.
  Completed sessions and canonical mastery evidence are retained.
- The planner validates dates, daily minutes and weekly availability. If its
  output is unusable, a deterministic schedule uses the saved real topics and
  availability. It never saves an empty plan or invents a generic subject.
- Session timestamps are stored in UTC; today and countdown use an explicit
  IANA timezone. Clients interpret legacy naive timestamps as UTC.
- Readiness and session scores remain server-derived. Unassessed is not zero.

## Deployment order

1. Deploy backend and apply migration `testprep_001` before clients.
2. Deploy web and release native builds after their build checks pass.
3. Enable reminders only after provider credentials and a consenting test
   device are verified. Set `STUDY_REMINDERS_ENABLED=true` to run the lifecycle
   worker every minute. Multiple replicas claim rows with `SKIP LOCKED`.

## Reminder prerequisites and limits

The previous push implementation returned success without contacting a
provider. The new service uses Firebase Admin for FCM and HTTP/2 for APNs.
`sent` means provider acceptance, not confirmation that a person saw it.
Zero accepted deliveries are retried, then marked failed; stale, closed-session
and inactive-plan reminders are cancelled. Collapse IDs reduce duplicate
notifications after a process interruption, but delivery is not exactly-once.

APNs needs `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_BUNDLE_ID`, and either
`APNS_PRIVATE_KEY` or a mounted `APNS_KEY_FILE`/`APNS_KEY_PATH`. FCM needs a
service-account credential (`FIREBASE_CREDENTIALS_JSON`,
`FIREBASE_CREDENTIALS_PATH`, or configured ADC) with messaging permissions.
A legacy `FCM_SERVER_KEY` alone is not sufficient for this adapter.

Production configuration inspection found APNs identifiers and a legacy FCM
key, but not the private key or service-account settings. These secrets were
not invented or copied from unrelated services. Push delivery remains a
release gate. Native device registration/permissions and a real notification
must be checked before enabling the worker for users.

## Validation

Targeted suites: `test_test_prep_workflow.py`, `test_study_plan_readiness.py`,
`test_test_prep_evidence.py`, `test_study_reminders.py`.
They exercise account resume, replay after a provider failure, ownership,
idempotent plan creation, stale edits, preservation of completed work, DST
boundaries, schedule validation, and truthful reminder outcomes.

SQLite tests do not prove concurrent PostgreSQL locking. Production-like
concurrency and physical-device delivery must be verified before release.

## Device registration and delivery verification

The production `/api/v1/push` registration endpoints now use the actual
`PushDevice.platform`, `created_at`, and integer ID fields. Registering a token
deactivates its registrations under other accounts. Notification preferences
are persisted in the user's learning profile; reminders respect the off switch
and quiet hours. The test endpoint reports provider acceptance and returns 503
when no provider accepts delivery. Android uses data messages so the client can
suppress reminders after logout or an account change.

Verification sequence: supply provider credentials and the Android Firebase app
configuration, sign in and allow notifications on a test device, register it,
then call the authenticated `/api/v1/push/test` and confirm physical receipt.
Test background, foreground, tap navigation, permission denial, and logout.
Only then enable `STUDY_REMINDERS_ENABLED` and confirm a due scheduled reminder
with its saved timezone. The feature flag is still off in production.
