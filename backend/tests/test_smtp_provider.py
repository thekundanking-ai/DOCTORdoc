import smtplib

import pytest

from app.core.delivery.smtp import SmtpDeliveryProvider


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.starttls_called = False
        self.login_called = False
        self.sent = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        self.starttls_called = True

    def login(self, user, password):
        self.login_called = (user, password)

    def send_message(self, msg):
        self.sent = msg


class FailingSMTP(FakeSMTP):
    def send_message(self, msg):
        raise smtplib.SMTPServerDisconnected("closed")


def _walk_pdf(msg):
    if msg.is_multipart():
        for part in msg.iter_parts():
            found = _walk_pdf(part)
            if found:
                return found
        return None
    if msg.get_content_type() == "application/pdf":
        return msg.get_payload(decode=True)
    return None


def _make_provider(**kwargs):
    defaults = dict(host="smtp.example.com", port=587, user="u", password="p",
                    sender="from@example.com", sender_name="Clinic", starttls=True)
    defaults.update(kwargs)
    return SmtpDeliveryProvider(**defaults)


def test_smtp_success_sends_pdf_with_recipient(monkeypatch):
    fake_cls = FakeSMTP
    monkeypatch.setattr(smtplib, "SMTP", fake_cls)
    prov = _make_provider()
    result = prov.send("patient@example.com", "Report", b"%PDF-1.4", "application/pdf",
                       {"consultation_id": 3})
    assert result.status == "sent"
    inst = FakeSMTP.instances[-1]
    assert inst.port == 587
    assert inst.starttls_called is True
    assert inst.login_called == ("u", "p")
    assert inst.sent["To"] == "patient@example.com"
    assert inst.sent["From"] == "Clinic <from@example.com>"
    assert _walk_pdf(inst.sent) == b"%PDF-1.4"


def test_smtp_starttls_disabled(monkeypatch):
    fake_cls = FakeSMTP
    monkeypatch.setattr(smtplib, "SMTP", fake_cls)
    prov = _make_provider(starttls=False)
    prov.send("a@x.com", "s", b"%PDF", "application/pdf", {"consultation_id": 1})
    assert FakeSMTP.instances[-1].starttls_called is False


def test_smtp_failure_is_sanitized(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", FailingSMTP)
    prov = _make_provider()
    result = prov.send("a@x.com", "s", b"%PDF", "application/pdf", {"consultation_id": 1})
    assert result.status == "failed"
    assert "SMTPServerDisconnected" in result.message
    assert "p" not in result.message
    assert "from@example.com" not in result.message
