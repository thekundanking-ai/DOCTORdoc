import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app

from app.core.cleanup import purge_expired_audio
from app.core.config import settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import AudioAttachment, Clinic, Consultation, User

BOOT = {
    "email": "owner@example.com",
    "password": "super-secret-1",
    "full_name": "Owner User",
    "clinic_name": "Test Clinic",
}

WAV_BYTES = b"RIFF0000WAVE" + b"\x00" * 32
WEBM_BYTES = b"\x1a\x45\xdf\xa3" + b"\x00" * 32
MP4_BYTES = b"\x00\x00\x00\x18ftyp" + b"\x00" * 32


def _bootstrap(client) -> None:
    assert client.post("/auth/bootstrap", json=BOOT).status_code == 201


def _login(client, email: str = BOOT["email"], password: str = BOOT["password"]) -> None:
    assert client.post("/auth/login", json={"email": email, "password": password}).status_code == 200


def _create_patient(client, name: str = "Alice Smith") -> int:
    resp = client.post("/patients", json={"full_name": name, "mobile": "+15551234567"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_consultation(client, patient_id: int) -> int:
    resp = client.post("/consultations", json={"patient_id": patient_id})
    assert resp.status_code == 201
    return resp.json()["id"]


def _upload(client, consultation_id: int, data: bytes = WAV_BYTES, upload_id: str | None = None) -> "Response":
    return client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": upload_id or str(uuid.uuid4())},
        files={"file": ("recording.bin", data, "application/octet-stream")},
    )


def _create_other_clinic_user() -> dict:
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
            email_verified=True,
        )
        db.add(user)
        db.commit()
        return {"email": user.email, "password": "other-pass-1"}


def test_create_and_list_consultation(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client)
    consultation_id = _create_consultation(client, patient_id)

    detail = client.get(f"/consultations/{consultation_id}").json()
    assert detail["status"] == "open"
    assert detail["patient_id"] == patient_id
    assert detail["audio"] is None

    history = client.get("/consultations", params={"patient_id": patient_id}).json()
    assert history["total"] == 1
    assert history["items"][0]["id"] == consultation_id


def test_create_consultation_rejects_invalid_or_foreign_patient(client):
    _bootstrap(client)
    _login(client)
    assert client.post("/consultations", json={"patient_id": 9999}).status_code == 404

    other = _create_other_clinic_user()
    other_patient = _create_patient(client)  # created by owner in clinic 1
    _login(client, other["email"], other["password"])
    assert client.post("/consultations", json={"patient_id": other_patient}).status_code == 404


def test_unauthenticated_denied(client):
    assert client.post("/consultations", json={"patient_id": 1}).status_code == 401
    assert client.get("/consultations", params={"patient_id": 1}).status_code == 401


def test_audio_upload_success(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client)
    consultation_id = _create_consultation(client, patient_id)

    resp = _upload(client, consultation_id)
    assert resp.status_code == 201
    body = resp.json()
    assert body["mime_type"] == "audio/wav"
    assert body["file_size_bytes"] == len(WAV_BYTES)

    detail = client.get(f"/consultations/{consultation_id}").json()
    assert detail["status"] == "awaiting_transcription"
    assert detail["audio"]["mime_type"] == "audio/wav"


def test_audio_upload_rejects_empty_unsupported_oversized(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client)
    consultation_id = _create_consultation(client, patient_id)

    assert _upload(client, consultation_id, data=b"").status_code == 422
    assert _upload(client, consultation_id, data=b"not-audio").status_code == 415
    assert _upload(client, consultation_id, data=b"<html>not audio</html>").status_code == 415

    old = settings.max_audio_bytes
    settings.max_audio_bytes = 64
    try:
        assert _upload(client, consultation_id, data=b"\x00" * 128).status_code == 413
    finally:
        settings.max_audio_bytes = old


def test_upload_detects_formats(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client)

    webm_cid = _create_consultation(client, patient_id)
    assert _upload(client, webm_cid, WEBM_BYTES).json()["mime_type"] == "audio/webm"

    mp4_cid = _create_consultation(client, patient_id)
    assert _upload(client, mp4_cid, MP4_BYTES).json()["mime_type"] == "audio/mp4"


def test_upload_retry_is_idempotent(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client)
    consultation_id = _create_consultation(client, patient_id)

    upload_id = str(uuid.uuid4())
    first = _upload(client, consultation_id, upload_id=upload_id)
    assert first.status_code == 201

    second = _upload(client, consultation_id, upload_id=upload_id)
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    with SessionLocal() as db:
        count = db.query(AudioAttachment).filter(AudioAttachment.consultation_id == consultation_id).count()
    assert count == 1

    assert _upload(client, consultation_id).status_code == 409


def test_audio_access_requires_auth_and_clinic(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client)
    consultation_id = _create_consultation(client, patient_id)
    _upload(client, consultation_id)

    fresh = TestClient(app)
    assert fresh.get(f"/consultations/{consultation_id}/audio").status_code == 401

    other = _create_other_clinic_user()
    _login(client, other["email"], other["password"])
    assert client.get(f"/consultations/{consultation_id}/audio").status_code == 404

    _login(client)
    playback = client.get(f"/consultations/{consultation_id}/audio")
    assert playback.status_code == 200
    assert playback.content == WAV_BYTES
    assert playback.headers["content-type"] == "audio/wav"


def test_cancel_consultation_flow(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client)
    consultation_id = _create_consultation(client, patient_id)

    cancelled = client.post(f"/consultations/{consultation_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    assert client.post(f"/consultations/{consultation_id}/cancel").status_code == 409

    with_audio = _create_consultation(client, patient_id)
    _upload(client, with_audio)
    assert client.post(f"/consultations/{with_audio}/cancel").status_code == 409


def test_cross_clinic_consultation_isolation(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client)
    consultation_id = _create_consultation(client, patient_id)
    _upload(client, consultation_id)

    other = _create_other_clinic_user()
    _login(client, other["email"], other["password"])
    assert client.get(f"/consultations/{consultation_id}").status_code == 404
    assert client.post(f"/consultations/{consultation_id}/cancel").status_code == 404
    assert client.get(f"/consultations/{consultation_id}/audio").status_code == 404


def test_purge_expired_audio(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client)
    consultation_id = _create_consultation(client, patient_id)
    _upload(client, consultation_id)

    with SessionLocal() as db:
        row = db.query(AudioAttachment).filter(AudioAttachment.consultation_id == consultation_id).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.add(row)
        db.commit()

    with SessionLocal() as db:
        assert purge_expired_audio(db) == 1
        assert db.query(AudioAttachment).filter(AudioAttachment.consultation_id == consultation_id).count() == 0
