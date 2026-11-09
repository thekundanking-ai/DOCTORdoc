import uuid
from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.core.stt.base import ProviderError
from app.core.stt.mock import MockSpeechToTextProvider
from app.core.stt import get_provider
from app.core.transcription_worker import process_pending
from app.db import SessionLocal
from app.models import AudioAttachment, Clinic, Consultation, Transcription, TranscriptionStatus, User

BOOT = {
    "email": "owner@example.com",
    "password": "super-secret-1",
    "full_name": "Owner User",
    "clinic_name": "Test Clinic",
}

WAV_BYTES = b"RIFF0000WAVE" + b"\x00" * 64


def _bootstrap(client) -> None:
    assert client.post("/auth/bootstrap", json=BOOT).status_code == 201


def _login(client, email: str = BOOT["email"], password: str = BOOT["password"]) -> None:
    assert client.post("/auth/login", json={"email": email, "password": password}).status_code == 200


def _setup_patient_with_audio(client) -> int:
    patient_resp = client.post("/patients", json={"full_name": "STT Patient", "mobile": "+19991112233"})
    assert patient_resp.status_code == 201
    patient_id = patient_resp.json()["id"]

    cons_resp = client.post("/consultations", json={"patient_id": patient_id})
    consultation_id = cons_resp.json()["id"]

    up = client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": str(uuid.uuid4()), "duration_seconds": 3},
        files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
    )
    assert up.status_code == 201
    return patient_id, consultation_id


def _pump(consultation_id: int, max_iter: int = 8) -> None:
    """Drive the worker across create -> start -> poll (10s gaps) until terminal."""
    for _ in range(max_iter):
        process_pending()
        with SessionLocal() as db:
            transcription = db.query(Transcription).filter(
                Transcription.consultation_id == consultation_id
            ).one_or_none()
            if transcription is None or transcription.status in ("completed", "failed"):
                return
            transcription.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()


def _create_other_clinic_user() -> None:
    with SessionLocal() as db:
        clinic = Clinic(name="Other Clinic", slug="other-clinic")
        db.add(clinic)
        db.flush()
        user = User(
            email="other@example.com",
            hashed_password=hash_password("other-pass-1"),
            full_name="Other Staff",
            role="staff",
            clinic_id=clinic.id,
        )
        db.add(user)
        db.commit()


def test_start_transcription_creates_local_record(client, monkeypatch):
    _bootstrap(client)
    _login(client)
    _, consultation_id = _setup_patient_with_audio(client)

    resp = client.post(f"/consultations/{consultation_id}/transcription")
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "submitting"
    assert body["consultation_id"] == consultation_id

    # duplicate not allowed
    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 409


def test_transcription_requires_audio(client):
    _bootstrap(client)
    _login(client)
    pat = client.post("/patients", json={"full_name": "No Audio", "mobile": "+19990001122"}).json()
    cons = client.post("/consultations", json={"patient_id": pat["id"]}).json()
    assert client.post(f"/consultations/{cons['id']}/transcription").status_code == 409


def test_worker_completes_and_deletes_audio(client, monkeypatch):
    _bootstrap(client)
    _login(client)
    _, consultation_id = _setup_patient_with_audio(client)

    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: MockSpeechToTextProvider("completed"))

    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201
    _pump(consultation_id)

    result = client.get(f"/consultations/{consultation_id}/transcription").json()
    assert result["status"] == "completed"
    assert "mock transcript" in result["transcript_text"]
    assert result["detected_language"] == "en-IN"
    assert result["provider"] == "MockSpeechToTextProvider"

    # audio deleted after transcript persisted
    with SessionLocal() as db:
        assert db.query(AudioAttachment).filter(AudioAttachment.consultation_id == consultation_id).count() == 0
        consultation = db.get(Consultation, consultation_id)
        assert consultation.status == "completed"


def test_worker_failure_preserves_audio(client, monkeypatch):
    _bootstrap(client)
    _login(client)
    _, consultation_id = _setup_patient_with_audio(client)

    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: MockSpeechToTextProvider("failed"))
    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201
    _pump(consultation_id)

    result = client.get(f"/consultations/{consultation_id}/transcription").json()
    assert result["status"] == "failed"

    # audio preserved for retry
    with SessionLocal() as db:
        assert db.query(AudioAttachment).filter(AudioAttachment.consultation_id == consultation_id).count() == 1


def test_transient_start_failure_is_recoverable(client, monkeypatch):
    _bootstrap(client)
    _login(client)
    _, consultation_id = _setup_patient_with_audio(client)

    class TransientStartFail(MockSpeechToTextProvider):
        def start_job(self, job_id):
            raise ProviderError("PROVIDER_TIMEOUT", "timeout", retryable=True)

    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: TransientStartFail("completed"))
    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201

    assert process_pending() >= 1  # create + start (transient -> backoff scheduled)

    result = client.get(f"/consultations/{consultation_id}/transcription").json()
    assert result["status"] == "submitting"  # recoverable, not failed
    assert result["error_code"] is None

    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.retry_count == 1
        assert transcription.next_retry_at is not None


def test_duplicate_transcription_prevented_after_timeout(client, monkeypatch):
    _bootstrap(client)
    _login(client)
    _, consultation_id = _setup_patient_with_audio(client)

    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: MockSpeechToTextProvider("completed"))
    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201
    # A second submission attempt (ambiguous timeout scenario) must not create a second job.
    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 409


def test_transcription_requires_auth(client):
    assert client.post("/consultations/1/transcription").status_code == 401
    assert client.get("/consultations/1/transcription").status_code == 401


def test_cross_clinic_transcription_isolation(client):
    _bootstrap(client)
    _login(client)
    _, consultation_id = _setup_patient_with_audio(client)
    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201

    _create_other_clinic_user()
    _login(client, "other@example.com", "other-pass-1")

    assert client.get(f"/consultations/{consultation_id}/transcription").status_code == 404
    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 404
    assert client.post(f"/consultations/{consultation_id}/transcription/retry").status_code == 404


def test_worker_handles_multiple_transcriptions_without_collision(client, monkeypatch):
    """Deterministic mock job ids used to collide on the unique provider_job_id constraint."""
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: MockSpeechToTextProvider("completed"))
    _bootstrap(client)
    _login(client)

    consultation_ids = []
    for i in range(3):
        mobile = f"+1999{i}000{i}0"
        patient_id = client.post("/patients", json={"full_name": f"STT Patient {i}", "mobile": mobile}).json()["id"]
        consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]
        up = client.post(
            f"/consultations/{consultation_id}/audio",
            data={"upload_id": str(uuid.uuid4()), "duration_seconds": 2},
            files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
        )
        assert up.status_code == 201
        assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201
        consultation_ids.append(consultation_id)

    for consultation_id in consultation_ids:
        _pump(consultation_id)

    for consultation_id in consultation_ids:
        result = client.get(f"/consultations/{consultation_id}/transcription").json()
        assert result["status"] == "completed", result
        assert result["transcript_text"]


def test_restart_recovery_claims_pending(client, monkeypatch):
    _bootstrap(client)
    _login(client)
    _, consultation_id = _setup_patient_with_audio(client)

    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: MockSpeechToTextProvider("completed"))
    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201

    # Simulate a process restart: a pending record sits unprocessed.
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        transcription.status = TranscriptionStatus.processing.value
        transcription.provider_job_id = None
        transcription.processing_started_at = None
        db.commit()

    _pump(consultation_id)
    result = client.get(f"/consultations/{consultation_id}/transcription").json()
    assert result["status"] == "completed"
