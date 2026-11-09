import uuid
from datetime import datetime, timedelta, timezone

from app.core.stt.mock import MockSpeechToTextProvider
from app.db import SessionLocal
from app.models import Transcription, TranscriptionStatus

WAV_BYTES = b"RIFF0000WAVE" + b"\x00" * 64

BOOT = {
    "email": "owner@deadline.com",
    "password": "pw-deadline-1",
    "full_name": "Owner",
    "clinic_name": "Clinic",
}


def _bootstrap(client):
    assert client.post("/auth/bootstrap", json=BOOT).status_code == 201


def _login(client):
    assert client.post("/auth/login", json={"email": BOOT["email"], "password": BOOT["password"]}).status_code == 200


def _setup_patient_with_audio(client) -> int:
    patient_id = client.post("/patients", json={"full_name": "P", "mobile": "+18889997771"}).json()["id"]
    consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]
    up = client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": str(uuid.uuid4()), "duration_seconds": 2},
        files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
    )
    assert up.status_code == 201
    return consultation_id


def test_retry_preserves_persistent_deadline_timestamp(client, monkeypatch):
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: MockSpeechToTextProvider("completed"))
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_patient_with_audio(client)

    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201

    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        transcription.status = TranscriptionStatus.failed.value
        transcription.error_code = "NO_TRANSCRIPT"
        transcription.error_message = "no transcript"
        transcription.retry_count = 0
        transcription.poll_count = 7
        transcription.provider_job_id = "job-x"
        transcription.submitted_at = datetime.now(timezone.utc) - timedelta(seconds=100)
        transcription.deadline_at = datetime.now(timezone.utc) + timedelta(seconds=3500)
        db.commit()
        submitted_before = transcription.submitted_at
        deadline_before = transcription.deadline_at

    resp = client.post(f"/consultations/{consultation_id}/transcription/retry")
    assert resp.status_code == 200

    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.submitted_at == submitted_before  # persistent, never reset
        assert transcription.deadline_at == deadline_before  # persistent, never reset
        assert transcription.provider_job_id == "job-x"  # no duplicate Gnani job
        assert transcription.poll_count == 0  # M2: fresh per-attempt poll budget
        assert transcription.retry_count == 1  # attempt counter incremented


def test_retry_rejected_when_past_deadline(client, monkeypatch):
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: MockSpeechToTextProvider("completed"))
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_patient_with_audio(client)

    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201

    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        transcription.status = TranscriptionStatus.failed.value
        transcription.error_code = "NO_TRANSCRIPT"
        transcription.error_message = "no transcript"
        transcription.retry_count = 0
        transcription.poll_count = 3
        transcription.provider_job_id = "job-x"
        transcription.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.commit()

    resp = client.post(f"/consultations/{consultation_id}/transcription/retry")
    assert resp.status_code == 409

    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "failed"  # unchanged
        assert transcription.retry_count == 0  # not incremented
        assert transcription.poll_count == 3  # unchanged
        assert transcription.provider_job_id == "job-x"
