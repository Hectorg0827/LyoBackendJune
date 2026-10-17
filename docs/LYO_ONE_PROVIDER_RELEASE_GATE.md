# Lyo One: final provider-backed release gate

## Proven in isolated staging

The authenticated Chromium journey smoke has passed on web frontend #140,
including Coach to Classroom and back, distinct Test Prep profile selection,
simulated 429/503 verification failures with retry, and structured Coach in
Chat. Backend #136 has passed ownership checks and a rehearsal of migrations
on the pre-existing main schema. These checks **do not** establish that a
provider-backed Classroom lesson can teach, recover, score and persist evidence.

## Remaining AI Classroom release test

1. Configure a **separate** Gemini credential in the *isolated*
   `LyoOne-Journey-Staging` backend service, not in production. Verify
   actual provider acceptance, quotas and desired model routing. Do not
   copy credentials, traffic, learner accounts or databases from production.
2. Confirm staging backend and staging frontend are deployed at the exact
   intended PR commits. Use staging synthetic learners only.
3. In GitHub Actions on the backend candidate branch, manually dispatch
   **Lyo One live Classroom provider rehearsal (isolated)**, selecting the
   scenario and learner profile and explicitly confirming provider readiness.
   The run hard-pins the staging API host. It creates a synthetic learner and
   exercises the deployed Chat/Classroom/Learning OS APIs via the existing
   live teacher-quality harness.
4. Require the redacted report to show real Classroom scenes and *positive
   persisted learning-evidence delta*. A healthy `/health` endpoint,
   Chat response or mock scene alone does not satisfy this criterion.
5. Repeat with:
   - `math_fractions` / `struggling` to check reteaching
   - `biology_photosynthesis` / `interrupter` to test interruption
   - `spanish_past_tense` / `curious` to test a non-math subject
   - `physics_newton2` / `confident_wrong` to test misconception handling
6. Review each report's scene transcript and learning-evidence changes.
   Do not equate an AI passing HTTP checks with sound pedagogy.
7. Run the Classroom recovery-specific matrix on real Gemini as a distinct
   gate: provider escalation, repeated failure/reteach, saved/reopened
   recovery, duplicate-answer handling. Keep `CLASSROOM_STRICT_SCHEMA=0`
   until the real provider schema contracts pass.

## Additional gates before enabling Lyo One in production

- **Test Prep:** a selected scheduled study session is persisted across
  Classroom detours, but the product does not yet expose a standalone
  persistent in-exam graded question. Question-level restoration is not
  complete. Do not infer it from the session round-trip checks.
- **Physical iOS and Android:** inspect actual navigation/voice, reconnection,
  background/foreground, long pauses, and session restoration. CI builds
  alone are not device validation.
- **Data:** keep source-branch order (backend first, web next, then mobile)
  and rehearse Alembic migrations on an existing database before production.
- **Authentication:** real 429/503 responses must be retryable; only proven
  invalid credentials clear the learner session.
- **Rollout:** retain feature flags and a rollback plan. Draft PRs must not
  be merged on the basis of staging navigation alone.

## Interpretation

The manual gate must remain red or unrun while no working model provider is
configured on isolated staging. If the provider is unavailable, the next
step is provider configuration and live validation, not a product-ready claim.
