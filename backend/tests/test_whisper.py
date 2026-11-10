import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.stt import get_provider
from app.core.stt.whisper import WhisperProvider, _map_language
from app.core.transcription_worker import process_pending
from app.db import SessionLocal
from app.models import Transcription

BOOT = {
    "email": "owner@whisper.com",
    "password": "super-secret-1",
    "full_name": "Owner User",
    "clinic_name": "Test Clinic",
}

WAV_BYTES = b"RIFF0000WAVE" + b"\x00" * 64


def _bootstrap(client) -> None:
    assert client.post("/auth/bootstrap", json=BOOT).status_code == 201


def _login(client) -> None:
    assert client.post("/auth/login", json={"email": BOOT["email"], "password": BOOT["password"]}).status_code == 200


def _setup_patient_with_audio(client) -> int:
    patient_id = client.post("/patients", json={"full_name": "STT Patient", "mobile": "+19991112233"}).json()["id"]
    consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]
    up = client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": str(uuid.uuid4()), "duration_seconds": 3},
        files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
    )
    assert up.status_code == 201
    return consultation_id


class FakeWhisper(WhisperProvider):
    def __init__(self):
        super().__init__()

    def _transcribe(self, path):
        return "the patient reports a fever and a mild cough", "en"


def _pump(consultation_id: int, max_iter: int = 8) -> None:
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


def test_map_language():
    assert _map_language(None) is None
    assert _map_language("") is None
    assert _map_language("auto") is None
    assert _map_language("indic-auto") is None
    assert _map_language("hi-IN") == "hi"
    assert _map_language("en") == "en"


def test_get_provider_whisper_selection(monkeypatch):
    monkeypatch.setattr(settings, "stt_provider", "whisper")
    provider = get_provider()
    assert isinstance(provider, WhisperProvider)
    assert provider.provider_model == "faster-whisper-small"


def test_whisper_provider_roundtrip(monkeypatch):
    provider = FakeWhisper()
    job_id = provider.create_job(WAV_BYTES, "audio/wav")
    assert job_id.startswith("whisper-")
    assert provider.get_status(job_id) == "COMPLETED"
    result = provider.retrieve_transcript(job_id)
    assert result.transcript_text == "the patient reports a fever and a mild cough"
    assert result.detected_language == "en"
    assert result.model == "faster-whisper-small"


def test_whisper_provider_empty_text_fails(monkeypatch):
    provider = FakeWhisper()
    provider._transcribe = lambda path: ("   ", None)
    job_id = provider.create_job(WAV_BYTES, "audio/wav")
    from app.core.stt.base import ProviderError

    try:
        provider.retrieve_transcript(job_id)
        raise AssertionError("expected empty-transcript failure")
    except ProviderError as exc:
        assert exc.code == "EMPTY_TRANSCRIPT"


def test_worker_completes_via_whisper(client, monkeypatch):
    monkeypatch.setattr(settings, "stt_provider", "whisper")
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_patient_with_audio(client)

    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: FakeWhisper())

    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201
    _pump(consultation_id)

    result = client.get(f"/consultations/{consultation_id}/transcription").json()
    assert result["status"] == "completed"
    assert result["provider"] == "WhisperProvider"
    assert result["provider_model"] == "faster-whisper-small"
    assert "fever" in result["transcript_text"]
    assert result["detected_language"] == "en"
