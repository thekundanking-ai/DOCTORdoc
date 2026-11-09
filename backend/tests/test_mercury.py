import json

import httpx

from app.core.ai.base import ReportProviderError
from app.core.ai.mercury_provider import MercuryReportProvider
from app.core.config import settings


class FakeMercuryResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


def _req_ok(content: str, status=200) -> FakeMercuryResp:
    return FakeMercuryResp(status, {"choices": [{"message": {"content": content}}]})


def test_mercury_payload_and_success(monkeypatch):
    monkeypatch.setattr(settings, "mercury_api_key", "k")
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["json"] = kwargs.get("json")
        return _req_ok('{"chief_complaint":"Fever","unclear_or_missing":[]}')

    monkeypatch.setattr("httpx.post", fake_post)
    provider = MercuryReportProvider()
    result = provider.generate_report("transcript text", {"name": "N"})

    assert captured["url"] == "https://api.inceptionlabs.ai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer k"
    payload = captured["json"]
    assert payload["model"] == "mercury-3"
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["schema"]["type"] == "object"
    assert result.structured["chief_complaint"] == "Fever"


def test_mercury_timeout_retryable(monkeypatch):
    monkeypatch.setattr(settings, "mercury_api_key", "k")

    def fake_post(url, **kwargs):
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr("httpx.post", fake_post)
    provider = MercuryReportProvider()
    try:
        provider.generate_report("t", {})
        raise AssertionError("expected error")
    except ReportProviderError as exc:
        assert exc.retryable is True
        assert exc.code == "PROVIDER_TIMEOUT"


def test_mercury_invalid_json_retryable(monkeypatch):
    monkeypatch.setattr(settings, "mercury_api_key", "k")

    def fake_post(url, **kwargs):
        return _req_ok("{not json")  # invalid JSON content

    monkeypatch.setattr("httpx.post", fake_post)
    provider = MercuryReportProvider()
    try:
        provider.generate_report("t", {})
        raise AssertionError("expected error")
    except ReportProviderError as exc:
        assert exc.retryable is True
        assert exc.code == "INVALID_RESPONSE"


def test_mercury_permanent_auth_not_retryable(monkeypatch):
    monkeypatch.setattr(settings, "mercury_api_key", "k")

    def fake_post(url, **kwargs):
        return FakeMercuryResp(401, {"error": "unauthorized"})

    monkeypatch.setattr("httpx.post", fake_post)
    provider = MercuryReportProvider()
    try:
        provider.generate_report("t", {})
        raise AssertionError("expected error")
    except ReportProviderError as exc:
        assert exc.retryable is False
        assert exc.code == "PROVIDER_PERMANENT"
