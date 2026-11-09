from app.core.delivery import get_delivery_provider
from app.core.delivery.mock import MockDeliveryProvider
from app.core.delivery.smtp import SmtpDeliveryProvider
from app.core.config import settings


def test_default_provider_is_mock(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)
    assert isinstance(get_delivery_provider(), MockDeliveryProvider)


def test_smtp_selected_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_user", "u")
    monkeypatch.setattr(settings, "smtp_password", "p")
    monkeypatch.setattr(settings, "smtp_from", "from@example.com")
    assert isinstance(get_delivery_provider(), SmtpDeliveryProvider)


def test_smtp_returns_failed_without_sending_secrets(monkeypatch):
    # No real send: provider returns failed on empty config; assert no secret leak.
    prov = SmtpDeliveryProvider("bad-host", 587, "u", "p", "f@x.com")
    result = prov.send("r@x.com", "s", b"%PDF", "application/pdf", {"consultation_id": 1})
    assert result.status == "failed"
    assert "smtp" in result.message.lower()
    assert "p" not in result.message  # password never leaked
