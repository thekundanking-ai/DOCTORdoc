import json
import uuid
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser

import httpx
import pytest

from app.core.config import settings
from app.core.stt.base import ProviderError
from app.core.stt.gnani import GnaniPrismaV3Provider
from app.core.transcription_worker import process_pending
from app.db import SessionLocal
from app.models import Transcription

WAV_BYTES = b"RIFF0000WAVE" + b"\x00" * 32


def extract_multipart_parts(body: bytes, content_type: str) -> dict:
    head = b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n"
    msg = BytesParser(policy=policy.default).parsebytes(head + body)
    parts: dict[str, dict] = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name is None:
            continue
        parts[name] = {
            "filename": part.get_filename(),
            "content_type": part.get_content_type(),
            "payload": part.get_payload(decode=True) or b"",
        }
    return parts

BOOT = {
    "email": "owner@example.com",
    "password": "super-secret-1",
    "full_name": "Owner User",
    "clinic_name": "Test Clinic",
}


def _bootstrap(client) -> None:
    assert client.post("/auth/bootstrap", json=BOOT).status_code == 201


def _login(client) -> None:
    assert client.post("/auth/login", json={"email": BOOT["email"], "password": BOOT["password"]}).status_code == 200


class FakeResp:
    status_code = 201

    def json(self):
        return {"job_id": "j-1", "status": "CREATED"}


class PermanentFailProvider:
    def create_job(self, audio_bytes: bytes, mime_type: str) -> str:
        raise ProviderError("INVALID_CONFIG", "invalid configuration", retryable=False)

    def start_job(self, job_id: str) -> None:
        raise AssertionError("should not start")

    def get_status(self, job_id: str) -> str:
        return "CREATED"

    def retrieve_transcript(self, job_id: str):
        raise AssertionError("should not retrieve")


def _transient_response(retry_after: str | None, status: int = 429) -> httpx.Response:
    headers = {}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    return httpx.Response(
        status, headers=headers, json={"error": "RATE_LIMITED", "message": "rate limit"}
    )


def _raise_on_transient(provider, resp):
    try:
        provider._check(resp)
    except ProviderError as exc:
        return exc
    raise AssertionError("expected ProviderError")


def test_retry_after_numeric_seconds(monkeypatch):
    monkeypatch.setattr(settings, "gnani_api_key", "k")
    provider = GnaniPrismaV3Provider()
    exc = _raise_on_transient(provider, _transient_response("30"))
    assert exc.retryable is True
    assert exc.retry_after == 30


def test_retry_after_future_http_date(monkeypatch):
    monkeypatch.setattr(settings, "gnani_api_key", "k")
    provider = GnaniPrismaV3Provider()
    future = datetime.now(timezone.utc) + timedelta(seconds=45)
    date_str = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    exc = _raise_on_transient(provider, _transient_response(date_str))
    assert exc.retryable is True
    assert 40 <= exc.retry_after <= 50


def test_retry_after_past_http_date_clamps_to_zero(monkeypatch):
    monkeypatch.setattr(settings, "gnani_api_key", "k")
    provider = GnaniPrismaV3Provider()
    past = datetime.now(timezone.utc) - timedelta(seconds=60)
    date_str = past.strftime("%a, %d %b %Y %H:%M:%S GMT")
    exc = _raise_on_transient(provider, _transient_response(date_str))
    assert exc.retry_after == 0


def test_retry_after_invalid_http_date_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "gnani_api_key", "k")
    provider = GnaniPrismaV3Provider()
    exc = _raise_on_transient(provider, _transient_response("not-a-date"))
    assert exc.retry_after is None


def test_retry_after_missing_header(monkeypatch):
    monkeypatch.setattr(settings, "gnani_api_key", "k")
    provider = GnaniPrismaV3Provider()
    exc = _raise_on_transient(provider, _transient_response(None))
    assert exc.retry_after is None


def test_create_job_multipart_shape_is_correct(monkeypatch):
    """Byte-level check of the outgoing multipart body (never contacts Gnani)."""
    monkeypatch.setattr(settings, "gnani_api_key", "k")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        req = __import__("httpx").Request(
            "POST", url, headers=kwargs.get("headers", {}), files=kwargs["files"]
        )
        req.read()
        captured["body"] = req.content
        captured["content_type"] = req.headers["content-type"]
        return FakeResp()

    monkeypatch.setattr("httpx.post", fake_post)

    provider = GnaniPrismaV3Provider()
    job_id = provider.create_job(WAV_BYTES, "audio/wav")
    assert job_id == "j-1"
    assert captured["headers"]["X-API-Key-ID"] == "k"

    parts = extract_multipart_parts(captured["body"], captured["content_type"])
    assert set(parts.keys()) == {"config", "files"}

    config = parts["config"]
    assert config["filename"] is None  # form field, not file
    assert config["content_type"] == "application/json"
    cfg = json.loads(config["payload"])
    assert cfg == {
        "model": "prisma-v3.0",
        "language_code": "indic-auto",
        "format": "transcribe",
        "mode": "transcribe",
    }

    audio = parts["files"]
    assert audio["filename"] == "recording.wav"
    assert audio["content_type"] == "audio/wav"
    assert audio["payload"] == WAV_BYTES


def _setup_transcription(client) -> int:
    patient_id = client.post("/patients", json={"full_name": "Gnani Patient", "mobile": "+18881234599"}).json()["id"]
    consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]
    up = client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": str(uuid.uuid4()), "duration_seconds": 2},
        files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
    )
    assert up.status_code == 201
    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201
    return consultation_id


def test_permanent_failure_is_not_reprocessed(client, monkeypatch):
    monkeypatch.setattr("app.core.transcription_worker.get_provider", lambda: PermanentFailProvider())

    _bootstrap(client)
    _login(client)
    consultation_id = _setup_transcription(client)

    assert process_pending() >= 1
    assert process_pending() == 0  # must NOT be re-claimed

    result = client.get(f"/consultations/{consultation_id}/transcription").json()
    assert result["status"] == "failed"
    assert result["error_code"] == "INVALID_CONFIG"

    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one()
        assert transcription.retry_count == settings.gnani_max_retries


def _make_provider(monkeypatch):
    monkeypatch.setattr(settings, "gnani_api_key", "k")
    return GnaniPrismaV3Provider()


def test_retrieve_transcript_valid_document(monkeypatch):
    provider = _make_provider(monkeypatch)
    files_resp = httpx.Response(200, json={"files": [{"transcript_url": "https://x/transcript.json"}]})
    monkeypatch.setattr(provider, "_get", lambda path, **kw: files_resp)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, timeout=60.0: httpx.Response(
            200, json={"full_transcript": "good text", "language_code": "hi-IN", "model": "prisma-v3.0"}
        ),
    )
    result = provider.retrieve_transcript("j-1")
    assert result.transcript_text == "good text"
    assert result.detected_language == "hi-IN"


def test_retrieve_transcript_data_shape(monkeypatch):
    """Actual documented Prisma v3 response: completed files under 'data'."""
    provider = _make_provider(monkeypatch)
    files_resp = httpx.Response(
        200,
        json={
            "data": [
                {
                    "file_id": "abc",
                    "status": "COMPLETED",
                    "transcript_url": "https://x/transcript.json",
                }
            ],
            "pagination": {"total_count": 1},
        },
    )
    monkeypatch.setattr(provider, "_get", lambda path, **kw: files_resp)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, timeout=60.0: httpx.Response(
            200, json={"full_transcript": "good text", "language_code": "hi-IN", "model": "prisma-v3.0"}
        ),
    )
    result = provider.retrieve_transcript("j-1")
    assert result.transcript_text == "good text"
    assert result.detected_language == "hi-IN"


def test_retrieve_transcript_data_takes_priority_over_files(monkeypatch):
    provider = _make_provider(monkeypatch)
    files_resp = httpx.Response(
        200,
        json={
            "data": [{"status": "COMPLETED", "transcript_url": "https://x/data.json"}],
            "files": [{"transcript_url": "https://x/files.json"}],
        },
    )
    monkeypatch.setattr(provider, "_get", lambda path, **kw: files_resp)
    monkeypatch.setattr(
        httpx, "get", lambda url, timeout=60.0: httpx.Response(200, json={"full_transcript": "from data"})
    )
    result = provider.retrieve_transcript("j-1")
    assert result.transcript_text == "from data"


def test_retrieve_transcript_bare_list_shape(monkeypatch):
    provider = _make_provider(monkeypatch)
    files_resp = httpx.Response(200, json=[{"transcript_url": "https://x/t.json"}])
    monkeypatch.setattr(provider, "_get", lambda path, **kw: files_resp)
    monkeypatch.setattr(
        httpx, "get", lambda url, timeout=60.0: httpx.Response(200, json={"full_transcript": "text"})
    )
    result = provider.retrieve_transcript("j-1")
    assert result.transcript_text == "text"


def test_retrieve_transcript_data_empty_raises_no_transcript(monkeypatch):
    provider = _make_provider(monkeypatch)
    for payload in ({"data": []}, {"data": None}, {"data": "nope"}):
        resp = httpx.Response(200, json=payload)
        monkeypatch.setattr(provider, "_get", lambda path, **kw: resp)
        with pytest.raises(ProviderError) as ei:
            provider.retrieve_transcript("j-1")
        assert ei.value.code == "NO_TRANSCRIPT"


def test_retrieve_transcript_data_missing_url_is_malformed(monkeypatch):
    provider = _make_provider(monkeypatch)
    files_resp = httpx.Response(200, json={"data": [{"file_id": "x", "status": "COMPLETED"}]})
    monkeypatch.setattr(provider, "_get", lambda path, **kw: files_resp)
    with pytest.raises(ProviderError) as ei:
        provider.retrieve_transcript("j-1")
    assert ei.value.code == "NO_TRANSCRIPT_URL"


def test_retrieve_transcript_malformed_files_response(monkeypatch):
    provider = _make_provider(monkeypatch)
    for payload in (None, 42, {"data": [{"transcript_url": 123}]}):
        resp = httpx.Response(200, json=payload)
        monkeypatch.setattr(provider, "_get", lambda path, **kw: resp)
        with pytest.raises(ProviderError) as ei:
            provider.retrieve_transcript("j-1")
        assert ei.value.code in ("NO_TRANSCRIPT", "NO_TRANSCRIPT_URL")


def test_retrieve_transcript_empty_files_raises_no_transcript(monkeypatch):
    provider = _make_provider(monkeypatch)
    for payload in ({"files": []}, [], {"files": "nope"}, "oops"):
        resp = httpx.Response(200, json=payload)
        monkeypatch.setattr(provider, "_get", lambda path, **kw: resp)
        with pytest.raises(ProviderError) as ei:
            provider.retrieve_transcript("j-1")
        assert ei.value.code == "NO_TRANSCRIPT"


def test_retrieve_transcript_missing_url_is_malformed(monkeypatch):
    provider = _make_provider(monkeypatch)
    files_resp = httpx.Response(200, json={"files": [{"file_id": "x"}]})
    monkeypatch.setattr(provider, "_get", lambda path, **kw: files_resp)
    with pytest.raises(ProviderError) as ei:
        provider.retrieve_transcript("j-1")
    assert ei.value.code == "NO_TRANSCRIPT_URL"


def test_retrieve_transcript_empty_or_malformed_document(monkeypatch):
    provider = _make_provider(monkeypatch)
    files_resp = httpx.Response(200, json={"files": [{"transcript_url": "https://x/t.json"}]})
    monkeypatch.setattr(provider, "_get", lambda path, **kw: files_resp)

    monkeypatch.setattr(httpx, "get", lambda url, timeout=60.0: httpx.Response(200, json={"language_code": "en"}))
    with pytest.raises(ProviderError) as ei:
        provider.retrieve_transcript("j-1")
    assert ei.value.code == "EMPTY_TRANSCRIPT"

    monkeypatch.setattr(httpx, "get", lambda url, timeout=60.0: httpx.Response(200, content=b"not-json"))
    with pytest.raises(ProviderError) as ei:
        provider.retrieve_transcript("j-1")
    assert ei.value.code == "EMPTY_TRANSCRIPT"


def test_get_status_classifies_invalid_response(monkeypatch):
    provider = _make_provider(monkeypatch)

    invalid = httpx.Response(200, content=b"not-json")
    monkeypatch.setattr(provider, "_get", lambda path, **kw: invalid)
    with pytest.raises(ProviderError) as ei:
        provider.get_status("j-1")
    assert ei.value.code == "INVALID_RESPONSE"

    missing = httpx.Response(200, json={"foo": "bar"})
    monkeypatch.setattr(provider, "_get", lambda path, **kw: missing)
    with pytest.raises(ProviderError) as ei:
        provider.get_status("j-1")
    assert ei.value.code == "UNKNOWN_STATUS"
