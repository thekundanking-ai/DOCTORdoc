import random
import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.stt.base import ProviderError, TranscriptResult
from app.core.transcription_worker import (_active_poll_interval, _active_stall_counts, process_pending)
from app.db import SessionLocal
from app.models import Transcription

WAV_BYTES = b"RIFF0000WAVE" + b"\x00" * 64

BOOT = {
    "email": "owner@example.com",
    "password": "super-secret-1",
    "full_name": "Owner User",
    "clinic_name": "Test Clinic",
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
        return TranscriptResult(transcript_text="hello hello", detected_language="en-IN")


def _bootstrap(client):
    assert client.post("/auth/bootstrap", json=BOOT).status_code == 201


def _login(client):
    assert client.post("/auth/login", json={"email": BOOT["email"], "password": BOOT["password"]}).status_code == 200


def _seed_processing_transcription(client, status="processing", retry_count=0, job_id="job-x"):
    mobile = f"+1888{random.randint(100000, 999999)}"
    patient_id = client.post("/patients", json={"full_name": "Poll Patient", "mobile": mobile}).json()["id"]
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


def test_first_poll_delay_at_least_10_seconds(client, monkeypatch):
    stub = StubProvider()
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client, status="submitting", job_id=None)

    assert process_pending() >= 1  # create + start
    assert process_pending() == 0  # nothing due yet (first poll scheduled in future)

    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "processing"
        assert transcription.provider_job_id == "job-x"
        assert stub.creates == 1
        assert stub.starts == 1
        assert stub.polls == 0
        wait = (transcription.next_retry_at - datetime.now(timezone.utc)).total_seconds()
        assert wait >= 9.0


def test_transient_429_respects_retry_after(client, monkeypatch):
    stub = StubProvider()
    stub.poll_outcomes = [ProviderError("RATE_LIMITED", "rate", retryable=True, retry_after=30)]
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)

    assert process_pending() == 1
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "processing"  # transient poll failure != job failure
        assert transcription.error_code is None
        assert transcription.retry_count == 1
        wait = (transcription.next_retry_at - datetime.now(timezone.utc)).total_seconds()
        assert 20 <= wait <= 38  # respects Retry-After=30 with jitter


def test_transient_429_then_success(client, monkeypatch):
    stub = StubProvider()
    stub.poll_outcomes = [
        ProviderError("RATE_LIMITED", "rate", retryable=True, retry_after=10),
        "COMPLETED",
    ]
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)

    assert process_pending() == 1  # 429 -> backoff, still processing
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "processing"
        transcription.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    assert process_pending() == 1  # now completes
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "completed"
        assert transcription.transcript_text == "hello hello"
        assert stub.creates == 0  # job reused, no re-upload
        assert stub.starts == 0  # already started
        assert transcription.next_retry_at is None


def test_bounded_backoff_cap(client, monkeypatch):
    stub = StubProvider()
    stub.poll_outcomes = [ProviderError("RATE_LIMITED", "rate", retryable=True, retry_after=100000)]
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)

    assert process_pending() == 1
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "processing"
        wait = (transcription.next_retry_at - datetime.now(timezone.utc)).total_seconds()
        assert 10 <= wait <= 301  # bounded cap


def test_permanent_4xx_fails_and_stops(client, monkeypatch):
    stub = StubProvider()
    stub.poll_outcomes = [ProviderError("INVALID_CONFIG", "bad config", retryable=False)]
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)

    assert process_pending() == 1
    assert process_pending() == 0  # not re-claimed
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "failed"
        assert transcription.error_code == "INVALID_CONFIG"
        assert transcription.retry_count == settings.gnani_max_retries
        assert transcription.next_retry_at is None


def test_restart_recovery_reuses_existing_job(client, monkeypatch):
    stub = StubProvider()
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)  # status=processing, job_id=job-x

    assert process_pending() == 1
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "completed"
        assert transcription.provider_job_id == "job-x"
        assert stub.creates == 0  # no duplicate job creation
        assert stub.starts == 0  # no duplicate start
        assert stub.polls == 1


class InProgressProvider(StubProvider):
    def get_status(self, job_id):
        self.polls += 1
        return "IN_PROGRESS"


class NetworkErrorProvider(StubProvider):
    def get_status(self, job_id):
        self.polls += 1
        raise ConnectionError("connection refused")


def _set_deadline_past(db, consultation_id):
    tx = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
    tx.submitted_at = datetime.now(timezone.utc) - timedelta(seconds=7200)
    tx.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=60)
    db.commit()


def test_processing_timeout_when_deadline_exceeded(client, monkeypatch):
    stub = StubProvider()
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)

    with SessionLocal() as db:
        _set_deadline_past(db, consultation_id)

    assert process_pending() == 1
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "failed"
        assert transcription.error_code == "PROCESSING_TIMEOUT"
        assert transcription.provider_job_id == "job-x"  # job id preserved on timeout


def test_poll_count_cap_terminates_processing(client, monkeypatch):
    stub = InProgressProvider()
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    monkeypatch.setattr(settings, "gnani_max_polls", 1)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)

    assert process_pending() == 1
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "failed"
        assert transcription.error_code == "PROCESSING_TIMEOUT"
        assert transcription.provider_status == "IN_PROGRESS"  # latest status persisted


def test_provider_status_persisted_while_processing(client, monkeypatch):
    stub = InProgressProvider()
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)

    assert process_pending() == 1
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "processing"
        assert transcription.provider_status == "IN_PROGRESS"
        assert transcription.poll_count == 1


def test_network_error_is_transient_not_fatal(client, monkeypatch):
    stub = NetworkErrorProvider()
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)

    assert process_pending() == 1
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "processing"
        assert transcription.error_code is None
        assert transcription.provider_status == "POLL_ERROR"


def test_first_poll_delay_uses_configured_interval(client, monkeypatch):
    stub = StubProvider()
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    monkeypatch.setattr(settings, "gnani_poll_interval_seconds", 25)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client, status="submitting", job_id=None)

    assert process_pending() >= 1  # create + start
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.status == "processing"
        wait = (transcription.next_retry_at - datetime.now(timezone.utc)).total_seconds()
        assert wait >= 24.0  # authoritative configured interval is used

class QueuedProvider(StubProvider):
    def get_status(self, job_id):
        self.polls += 1
        return "QUEUED"


def test_active_poll_interval_helper_escalation_bounded(monkeypatch):
    monkeypatch.setattr(settings, "gnani_poll_interval_seconds", 10)
    monkeypatch.setattr(settings, "gnani_poll_max_interval_seconds", 30)
    tid = 999001
    seq = [_active_poll_interval(tid) for _ in range(14)]
    assert seq[0] == 10
    assert seq[4] == 10
    assert seq[5] == 20  # 6th consecutive active poll escalates
    assert seq[10] == 20
    assert seq[11] == 30  # capped at max interval
    assert seq[13] == 30
    assert all(a <= b for a, b in zip(seq, seq[1:]))
    assert min(seq) >= settings.gnani_poll_interval_seconds
    _active_stall_counts.pop(tid, None)


def test_active_poll_interval_escalates_for_stalled_job(client, monkeypatch):
    stub = QueuedProvider()
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: stub)
    _bootstrap(client)
    _login(client)
    consultation_id = _seed_processing_transcription(client)
    waits = []
    for _ in range(7):
        with SessionLocal() as db:
            tx = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
            tx.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        assert process_pending() == 1
        with SessionLocal() as db:
            tx = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
            waits.append((tx.next_retry_at - datetime.now(timezone.utc)).total_seconds())
    assert waits[0] >= 9.0
    assert waits[0] < 15.0
    assert waits[5] >= 19.0  # escalated to ~20s after stall window
    assert waits[5] <= 31.0  # bounded cap
    assert stub.polls == 7
