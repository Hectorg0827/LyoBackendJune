# LyoApp Backend

A Scalable, Offline-First Modular Monolith for AI-driven EdTech and social platform.

## 🚀 Quick Deploy to Google Cloud

Deploy your LyoBackend to Google Cloud Run in one command:

```bash
./one-click-gcp-deploy.sh
```

**That's it!** The script automatically handles:
- ✅ Google Cloud SDK setup and authentication
- ✅ Project configuration and API enablement  
- ✅ Docker image building and registry push
- ✅ Secret management and service accounts
- ✅ Cloud Run deployment with auto-scaling
- ✅ Health checks and monitoring setup

[📖 **See Google Cloud Quick Start Guide →**](GOOGLE_CLOUD_QUICK_START.md)

---

## Architecture

This application follows a **Modular Monolith** architecture with strict module boundaries:

- **`/auth`** - Authentication and user management
- **`/learning`** - Course and lesson management
- **`/feeds`** - Social feeds and posts
- **`/community`** - Study groups and community events
- **`/gamification`** - XP, achievements, and streaks
- **`/core`** - Shared infrastructure and utilities

## Tech Stack

- **FastAPI** - Modern, fast web framework
- **SQLAlchemy** - Async ORM with PostgreSQL
- **Alembic** - Database migrations
- **Celery** - Background task processing
- **Redis** - Caching and message broker
- **Poetry** - Dependency management
- **Pytest** - Testing framework

## Development Setup

1. **Install dependencies:**
   ```bash
   poetry install
   ```

2. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start PostgreSQL and Redis:**
   ```bash
   # Using Docker
   docker run --name lyo-postgres -e POSTGRES_USER=lyo_user -e POSTGRES_PASSWORD=lyo_password -e POSTGRES_DB=lyo_db -p 5432:5432 -d postgres:15
   docker run --name lyo-redis -p 6379:6379 -d redis:7-alpine
   ```

4. **Run database migrations:**
   ```bash
   poetry run alembic upgrade head
   ```

5. **Start the development server:**
   ```bash
   poetry run uvicorn lyo_app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Testing

Run all tests:
```bash
poetry run pytest
```

Run tests with coverage:
```bash
poetry run pytest --cov=lyo_app --cov-report=html
```

## API Documentation

Once running, visit:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Module Guidelines

1. **No direct imports between modules** - Use service interfaces
2. **All I/O operations must be async**
3. **Write tests before implementing features (TDD)**
4. **Security and ethics are built-in requirements**

## Project Structure

```
lyo_app_backend/
├── lyo_app/
│   ├── auth/           # Authentication module
│   ├── learning/       # Learning management
│   ├── feeds/          # Social feeds
│   ├── community/      # Community features
│   ├── gamification/   # XP and achievements
│   ├── core/          # Shared utilities
│   └── main.py        # FastAPI app
├── tests/             # Test modules
├── alembic/           # Database migrations
├── pyproject.toml     # Dependencies
└── README.md
```
