# DoctorDoc Deployment Note

## Database & migrations
- PostgreSQL 16 via `docker compose up -d db`. Data persists in the `pgdata` volume.
- Current migration head: `0008` (apply with `python -m alembic upgrade head` from `backend/`).
- Do not edit existing migrations; add new alembic revisions if the schema changes.

## Required environment variables (production, `DEBUG=false`)
| Env | Purpose | Required |
|---|---|---|
| `SECRET_KEY` | JWT signing key (long random string) | Yes (startup fails without it) |
| `DATABASE_URL` | e.g. `postgresql+psycopg2://user:pass@host:5432/doctordoc` | Yes |
| `GNANI_API_KEY` | Real Gnani Prisma v3 STT provider | Yes for real transcription |
| `MERCURY_API_KEY` | Real Inception Mercury 3 report provider | Yes for real report generation |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | Real delivery (email) provider | Yes for real delivery |

## Provider safety guard (no silent mock)
When `DEBUG=false` and `ALLOW_MOCK_PROVIDERS` is unset (default `false`), provider selection
**fails explicitly** instead of silently using a mock:

- Report generation without `MERCURY_API_KEY` -> HTTP 502 "Report provider is not configured."
- Transcription without `GNANI_API_KEY` -> the transcription row is marked `failed` with `PROVIDER_NOT_CONFIGURED`.
- Delivery without SMTP config -> delivery is recorded as `failed` with a clear error message.

Dev/test runs **must** use mocks explicitly:
- `DEBUG=true` (dev), or
- `ALLOW_MOCK_PROVIDERS=true` (staging/preview with mocks).

Never set `DEBUG=true` in production.

## Build & run commands (Windows PowerShell)
```powershell
# 1. Database
docker compose up -d db

# 2. Migrations (from backend/)
cd backend
$env:DATABASE_URL='postgresql+psycopg2://doctordoc:doctordoc@localhost:5432/doctordoc'
python -m alembic upgrade head

# 3. Backend (production-like; keys come from root .env)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3b. Backend (dev with mocks)
$env:DEBUG='true'; $env:GNANI_API_KEY=''; $env:MERCURY_API_KEY=''
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 4. Frontend
cd ../frontend
npm run dev -- --port 5174 --strictPort   # development
npm run build                            # production bundle (dist/)

# Tests
cd backend; python -m pytest
cd frontend; npm test
```

## Notes
- Frontend dev server proxies `/api` to `http://localhost:8000`.
- Approved reports are immutable: `PATCH`/`generate` return 409 after approval.
- Live provider calls are one-way and billable; use synthetic data for any verification.