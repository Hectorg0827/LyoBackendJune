# Lyo One: Isolated staging validation

The isolated Railway project **LyoOne-Journey-Staging** has a separate
PostgreSQL instance, synthetic-only user accounts, and no production domain
or production database references. It hosts the branch
\`feature/lyo-one-coach-chat-current\`.

## Preconditions

- Existing production services are never repointed to the staging database.
- The repository's \`coach_002\` and \`coach_003\` migrations are tested on
  a fresh PostgreSQL schema in GitHub CI.
- Fresh databases initialized by the runtime also ensure the default Chat
  organization exists before accepting chat messages.
- A database already initialized using \`Base.metadata.create_all\` cannot
  safely replay the full Alembic migration history from base without schema
  reconciliation. Do not stamp or drop such a database to force the test.
- This isolated staging service uses runtime schema initialization; it
  intentionally has no Alembic pre-deploy command. A separate clean-db CI
  run covers Alembic migration safety.

## External HTTP checks

\`LYO_ONE_STAGING_SMOKE=1 python3 scripts/validate_lyo_one_staging_http.py\`

The script targets only a hard-coded dedicated staging hostname and:
- registers and authenticates two synthetic learners;
- creates one evidence-scoped learning goal and retrieves Coach's mission;
- persists Coach -> Classroom -> Chat, reloads and safely retries;
- rejects outdated revisions, unauthorized access and wrong exam links;
- creates and reopens distinct Test Prep exam profiles;
- verifies Chat's structured \`coach_mission\` and prose answer are both
  emitted on an explicitly requested coaching turn.

No real user documents, production tokens, production domains or provider
secrets are used. Synthetic test data is limited to the disposable staging DB.

## Not yet covered

The isolated staging environment intentionally has no Gemini provider key
or native client builds. Full AI Classroom teaching and evidence scoring,
voice interruption, persisted in-exam answer return, real-device behavior
and rollout of all web/mobile clients remain separate release gates.

Production merges and feature-flag activation remain blocked until those
gates have evidence. CI green by itself is not production deployment.
