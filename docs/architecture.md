# DoctorDoc Architecture

## Layout

```
backend/     FastAPI app
frontend/    React + Vite + TypeScript + Tailwind
docker/      Docker assets
docs/        Documentation
```

## Backend

- FastAPI app in `backend/app/main.py`.
- Config via `backend/app/core/config.py` (pydantic-settings, env-driven).
- Structured logging in `backend/app/core/logging.py`.
- PostgreSQL via SQLAlchemy ORM; migrations with Alembic (`backend/migrations`).
- Endpoints:
  - `GET /health` — liveness, returns `{status: "ok"}`.
  - `GET /health/ready` — readiness, checks DB connectivity.
- Uniform error responses; unhandled exceptions map to 500 JSON.

## Frontend

- React SPA scaffolded with Vite + TypeScript.
- Tailwind CSS for styling.
- Tests: Vitest + React Testing Library.

## Local Dev

`docker compose up` starts db, backend (port 8000), frontend (port 5173).
Frontend origin is allowlisted via CORS config.
