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

## Consultations (Phase 4)

- Open a patient → **New consultation** → consent confirmation → record with the browser microphone (MediaRecorder), preview, discard or upload.
- `POST /api/consultations`, `GET /api/consultations?patient_id=`, `GET /api/consultations/{id}`, `POST /api/consultations/{id}/audio` (multipart, idempotent via `upload_id`), `GET /api/consultations/{id}/audio` (authenticated playback), `POST /api/consultations/{id}/cancel`.
- Audio is stored in PostgreSQL (bytea) via `audio_attachment`; clinic scoping applied on every operation.
- Unprocessed audio auto-purges after `AUDIO_RETENTION_DAYS`; deletion after processing is deferred to the Phase 5 transcription flow.

## Transcription (Phase 5)

- After audio is uploaded, a consultation shows an **Transcribe audio** action (requires doctor confirmation that audio will be sent to Gnani AI).
- Gnani Prisma v3.0 Batch: create job → start → poll → download transcript. The full transcript is stored on the `transcription` row; temporary audio is deleted after the transcript is persisted.
- `no GNANI_API_KEY` is configured, the app uses a non-billable mock provider for development. Set `GNANI_API_KEY` (backend-only) to enable the real provider.
- Endpoints: `POST /api/consultations/{id}/transcription`, `GET /api/consultations/{id}/transcription`, `POST /api/consultations/{id}/transcription/retry`.

## Reports (Phase 6)

- On a completed transcription, **Generate Consultation Report** sends the transcript to Inception Mercury 3 and produces a structured draft.
- The doctor reviews/edits sections, saves drafts, regenerates (confirm), and explicitly approves (records approver + timestamp). Approved reports are immutable.
- No `MERCURY_API_KEY` → a non-billable mock provider is used for development. Set it (backend-only) to enable the real provider.
- Endpoints: `POST/GET /api/consultations/{id}/report`, `PATCH /api/consultations/{id}/report`, `POST /api/consultations/{id}/report/approve`.

## Health

- Backend: http://localhost:8000/health, `/health/ready`
- Frontend: http://localhost:5173

## Tests

```
cd backend && python -m pytest
cd frontend && npm test && npm run build
```

Backend auth tests run against a real PostgreSQL database named `doctordoc_test`.
