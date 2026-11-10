import random
import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.stt.base import ProviderError
from app.core.transcription_worker import _schedule_transient, process_pending
from app.db import SessionLocal
from app.models import Transcription

WAV_BYTES = b"RIFF0000WAVE" + b"\x00" * 64

BOOT = {
    "email": "owner@timeout.com",
    "password": "pw-timeout-1",
    "full_name": "Owner",
    "clinic_name": "Clinic",
}


class StubProvider:
    def __init__(self):
        self.creates = 0
        self.starts = 0
        self.polls = 0
        self.poll_outcomes = []
        self.job_id = "job-x"

    def create_job(self, audio_bytes, mime_type):
        self.creates += 1
        return self.job_id

    def start_job(self, job_id):
        self.starts += 1

    def get_status(self, job_id):
        self.polls += 1
        if self.poll_outcomes:
            item = self.poll_outcomes.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return "COMPLETED"

    def retrieve_transcript(self, job_id):
        raise AssertionError("should not retrieve")


def _bootstrap(client):
    assert client.post("/auth/bootstrap", json=BOOT).status_code == 201


def _login(client):
    assert client.post("/auth/login", json={"email": BOOT["email"], "password": BOOT["password"]}).status_code == 200


def _seed_processing_transcription(client, status="processing", retry_count=0, job_id="job-x"):
    mobile = f"+1888{random.randint(100000, 999999)}"
    patient_id = client.post("/patients", json={"full_name": "Timeout Patient", "mobile": mobile}).json()["id"]
    consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]
    up = client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": str(uuid.uuid4()), "duration_seconds": 2},
        files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
    )
    assert up.status_code == 201
    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201

    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        transcription.status = status
        transcription.provider_job_id = job_id if job_id else None
        transcription.retry_count = retry_count
        transcription.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        transcription.processing_started_at = None
        db.commit()
    return consultation_id


def _expire(db, consultation_id):
    transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
    transcription.submitted_at = datetime.now(timezone.utc) - timedelta(seconds=7200)
    transcription.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=60)
    db.commit()


def _fresh(db, consultation_id):
    transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
    transcription.submitted_at = datetime.now(timezone.utc)
    transcription.deadline_at = datetime.now(timezone.utc) + timedelta(seconds=3600)
    db.commit()


def _get(db, consultation_id):
    return db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()


def test_expired_http429_fails_with_timeout(client, monkeypatch):
    stub = StubProvider()
    stub.poll_outcomes = [ProviderError("RATE_LIMITED", "rate", retryable=True, retry_after=30)]
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)
    with SessionLocal() as db:
        _expire(db, consultation_id)

    assert process_pending() == 1
    with SessionLocal() as db:
        t = _get(db, consultation_id)
        assert t.status == "failed"
        assert t.error_code == "PROCESSING_TIMEOUT"
        assert t.next_retry_at is None
        assert t.retry_count == settings.gnani_max_retries
        assert stub.creates == 0
        assert stub.polls == 0  # top-of-turn guard fires before polling


def test_expired_provider_timeout_fails_with_timeout(client, monkeypatch):
    stub = StubProvider()
    stub.poll_outcomes = [ProviderError("REQUEST_TIMEOUT", "timeout", retryable=True, retry_after=None)]
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)
    with SessionLocal() as db:
        _expire(db, consultation_id)

    assert process_pending() == 1
    with SessionLocal() as db:
        t = _get(db, consultation_id)
        assert t.status == "failed"
        assert t.error_code == "PROCESSING_TIMEOUT"
        assert t.next_retry_at is None
        assert t.retry_count == settings.gnani_max_retries
        assert stub.creates == 0


def test_expired_generic_exception_fails_with_timeout(client, monkeypatch):
    stub = StubProvider()
    stub.poll_outcomes = [ConnectionError("connection refused")]
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)
    with SessionLocal() as db:
        _expire(db, consultation_id)

    assert process_pending() == 1
    with SessionLocal() as db:
        t = _get(db, consultation_id)
        assert t.status == "failed"
        assert t.error_code == "PROCESSING_TIMEOUT"
        assert t.next_retry_at is None
        assert t.retry_count == settings.gnani_max_retries
        assert t.provider_status is None  # top-of-turn guard fires before polling
        assert stub.creates == 0


def test_non_expired_http429_retries(client, monkeypatch):
    stub = StubProvider()
    stub.poll_outcomes = [ProviderError("RATE_LIMITED", "rate", retryable=True, retry_after=30)]
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)
    with SessionLocal() as db:
        _fresh(db, consultation_id)

    assert process_pending() == 1
    with SessionLocal() as db:
        t = _get(db, consultation_id)
        assert t.status == "processing"
        assert t.error_code is None
        assert t.retry_count == 1
        assert t.next_retry_at is not None
        assert t.next_retry_at > datetime.now(timezone.utc)
        assert stub.creates == 0


def test_already_completed_is_noop(client, monkeypatch):
    stub = StubProvider()
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)
    with SessionLocal() as db:
        t = _get(db, consultation_id)
        t.status = "completed"
        t.transcript_text = "existing transcript"
        t.next_retry_at = None
        db.commit()

    assert process_pending() == 0
    with SessionLocal() as db:
        t = _get(db, consultation_id)
        assert t.status == "completed"
        assert t.transcript_text == "existing transcript"
    assert stub.polls == 0


def test_already_failed_is_not_reclaimed(client, monkeypatch):
    stub = StubProvider()
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)
    with SessionLocal() as db:
        t = _get(db, consultation_id)
        t.status = "failed"
        t.error_code = "EARLIER_FAILURE"
        t.retry_count = settings.gnani_max_retries
        t.next_retry_at = None
        db.commit()

    assert process_pending() == 0
    with SessionLocal() as db:
        t = _get(db, consultation_id)
        assert t.status == "failed"
        assert t.error_code == "EARLIER_FAILURE"
        assert t.retry_count == settings.gnani_max_retries
    assert stub.polls == 0



def test_schedule_transient_refuses_expired_job(client, monkeypatch):
    stub = StubProvider()
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)
    with SessionLocal() as db:
        _expire(db, consultation_id)
        t = _get(db, consultation_id)
        before = t.next_retry_at
        _schedule_transient(db, t, 30)
        assert t.status == "failed"
        assert t.error_code == "PROCESSING_TIMEOUT"
        assert t.next_retry_at is None
        assert t.retry_count == settings.gnani_max_retries
        assert stub.creates == 0
        assert before is None or t.next_retry_at is None
