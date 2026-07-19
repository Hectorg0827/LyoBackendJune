# Production deployment (Railway)

Railway is the single production target for this repository.

## Required Railway resources

- One backend service connected to this repository's `main` branch
- Railway PostgreSQL, exposed to the service as `DATABASE_URL`
- Railway Redis, exposed to the service as `REDIS_URL`
- A generated Railway domain initially; attach the production API domain only after health checks pass

## Required variables

Set these in Railway, never in Git or a local deployment script:

- `ENVIRONMENT=production`
- `DEBUG=false`
- `SECRET_KEY` (at least 64 random characters)
- `JWT_SECRET_KEY` (at least 64 random characters)
- `DATABASE_URL` (provided by Railway PostgreSQL)
- `REDIS_URL` (provided by Railway Redis)
- `GEMINI_API_KEY` (a newly generated key; do not reuse the revoked key)
- `GOOGLE_API_KEY` (set to the same new Gemini key only if legacy code still requires it)
- `CORS_ORIGINS` (the exact web application origins, as a comma-separated list)

Optional provider keys should be added only when their feature is enabled.

## Deployment gate

A deployment is successful only when all of the following are true:

1. Railway reports the deployment Active.
2. `GET /health` returns HTTP 200 from the real FastAPI application.
3. `GET /docs` returns HTTP 200.
4. A production smoke test can register or authenticate a test account.
5. An authenticated AI chat request succeeds with the new Gemini key.
6. Community and classroom read endpoints return non-5xx responses.

The container now starts `lyo_app.enhanced_main:app` directly. If imports,
database migrations, or required configuration fail, Railway will mark the
deployment failed instead of accepting a health-only bootloader.

## Domain cutover

Keep clients on the generated Railway domain until the deployment gate passes.
Then attach the production API hostname in Railway, configure the DNS record
Railway provides, wait for TLS issuance, and update all web/iOS/Android base URLs
to that one hostname.
