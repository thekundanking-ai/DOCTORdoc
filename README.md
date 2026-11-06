# DoctorDoc 2.0

## Setup

### Environment variables
Copy `.env.example` to a local `.env` (gitignored) and set at least `SECRET_KEY` to a long random value before starting the backend in production mode (`DEBUG=false`). With `DEBUG=true`, an ephemeral key is generated at startup (sessions reset on restart).

### Backend
```
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```
cd frontend
npm install
npm run dev
```
The Vite dev server proxies `/api` to the backend (default `http://localhost:8000`, override with `VITE_BACKEND_URL`). The JWT is held in an httpOnly cookie; JavaScript never reads the token.

### Docker
```
# ensure SECRET_KEY is set in the environment (or in a local .env)
docker compose up --build
```
Run database migrations against the running stack:
```
docker compose exec backend alembic upgrade head
```

## Auth

- `POST /api/auth/bootstrap` — creates the initial clinic + clinic owner. Allowed only while the database has zero users.
- `POST /api/auth/login` — returns the user and sets an httpOnly JWT cookie.
- `POST /api/auth/logout` — clears the cookie.
- `GET /api/auth/me` — requires auth; returns the current user.
- `GET /api/auth/owner-only` — requires `clinic_owner`/`admin` role.

Protected routes redirect to `/login` when unauthenticated.

## Health

- Backend: http://localhost:8000/health, `/health/ready`
- Frontend: http://localhost:5173

## Tests

```
cd backend && python -m pytest
cd frontend && npm test && npm run build
```

Backend auth tests run against a real PostgreSQL database named `doctordoc_test`.
