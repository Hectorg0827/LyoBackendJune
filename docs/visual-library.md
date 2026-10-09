# Lyo Visual Library: educational image discovery

This is a rights-aware retrieval layer, not an AI image generator.
It shares the existing TeachingVisual and SmartBlock contracts across
Chat, Classroom, Web, iOS and Android.

## Sources and rights filtering

- Wikimedia Commons: first general source. Only CC BY, CC BY-SA, CC0,
  and Public Domain metadata accepted. NC, ND and unknown licenses are rejected.
- NASA Image Library: prioritized for space and astronomy. Link to the NASA
  item and observe the NASA media usage rules and copyright caveats.
- Smithsonian Open Access: prioritized for museums, history and fossils
  when SMITHSONIAN_API_KEY is configured. Only CC0 image assets accepted.
- Pexels: prioritized for real-world photography when PEXELS_API_KEY is set.
  Display author credit and a link to the specific Pexels photo.
- Openverse: anonymous search fallback for cc0, pdm, by or by-sa licenses.
  Initial release only accepts Wikimedia-hosted image and landing URLs.

Model-authored URLs are never accepted. Returned image and source URLs must
pass strict approved HTTPS-host checks before being shown to students.

## Optional credentials

PEXELS_API_KEY: https://www.pexels.com/api/
SMITHSONIAN_API_KEY: https://www.si.edu/openaccess/devtools

Set secrets on Railway backend in the Lyo environment, NOT NEXT_PUBLIC_*
or native client config. Never commit them or send them to web/mobile users.
Wikimedia, Openverse and NASA do not need Lyo-owned keys.

## Limits and rollout

A composed Chat lesson retrieves at most one optional photograph. The
Classroom hydrates already-authorized visual beats. Both preserve accessible
text and never fail the lesson when an API is slow or unavailable. Providers
use bounded timeouts and only successful results are stored in a bounded
in-memory cache (128 items per process). There is not yet a durable shared
media database, global license audit, or cross-instance object-store cache.

Tests: tests/test_visual_library.py, tests/test_classroom_visual_teaching.py,
tests/test_lesson_blocks.py.

Post-deployment acceptance:
1. Confirm backend and Web builds pass; merge and deploy to Railway Lyo.
2. Verify exact deployed commit SHA, /healthz and runtime errors.
3. Test authenticated Chat with photosynthesis, a NASA space image, and
   a visual Classroom activity. Confirm real image + clickable attribution.
4. Test iOS and Android media links and diagram continuity.
5. Configure Pexels and Smithsonian keys separately, then test those
   providers' real API results and license/credit presentation.
6. Track quotas, rate limits and cache efficiency at production scale.

A green CI check or healthy deployment does not by itself verify that
an image is visible in an authenticated user session.
