import random
import uuid

from app.core.ai.mock import MockReportProvider
from app.core.delivery.base import DeliveryResult
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Clinic, DeliveryStatus, ReportDelivery, Transcription, User

BOOT = {
    "email": "owner@example.com",
    "password": "super-secret-1",
    "full_name": "Owner User",
    "clinic_name": "Test Clinic",
}
WAV_BYTES = b"RIFF0000WAVE" + b"\x00" * 64
PATIENT_EMAIL = "patient@example.com"


def _bootstrap(client):
    assert client.post("/auth/bootstrap", json=BOOT).status_code == 201


def _login(client, email=BOOT["email"], password=BOOT["password"]):
    assert client.post("/auth/login", json={"email": email, "password": password}).status_code == 200


def _setup_approved_report(client, email: str | None = PATIENT_EMAIL):
    mobile = f"+1888{random.randint(100000,999999)}"
    payload = {"full_name": "Delivery Patient", "mobile": mobile}
    if email is not None:
        payload["email"] = email
    patient_id = client.post("/patients", json=payload).json()["id"]
    consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]
    up = client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": str(uuid.uuid4()), "duration_seconds": 3},
        files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
    )
    assert up.status_code == 201
    with SessionLocal() as db:
        db.add(Transcription(
            consultation_id=consultation_id,
            clinic_id=1,
            provider="mock",
            provider_model="mock",
            status="completed",
            transcript_text="Patient reports cough and cold. Paracetamol advised.",
        ))
        db.commit()
    assert client.post(f"/consultations/{consultation_id}/report/generate").status_code == 200
    assert client.post(f"/consultations/{consultation_id}/report/approve").status_code == 200
    return consultation_id


def _create_other_clinic_user():
    with SessionLocal() as db:
        clinic = Clinic(name="Other Clinic", slug="other-clinic")
        db.add(clinic)
        db.flush()
        db.add(User(
            email="other@example.com",
            hashed_password=hash_password("other-pass-1"),
            full_name="Other Staff",
            role="staff",
            clinic_id=clinic.id,
            email_verified=True,
        ))
        db.commit()


def test_deliver_approved_report_success(client, monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_approved_report(client)

    resp = client.post(f"/consultations/{consultation_id}/report/deliver")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "sent"
    assert body["channel"] == "email"
    assert body["delivered_at"] is not None

    with SessionLocal() as db:
        rows = db.query(ReportDelivery).filter(ReportDelivery.report_id == body["report_id"]).all()
        assert len(rows) == 1
        assert rows[0].status == DeliveryStatus.sent.value


def test_deliver_requires_approved_report(client, monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    _bootstrap(client)
    _login(client)
    mobile = f"+1888{random.randint(100000,999999)}"
    patient_id = client.post("/patients", json={"full_name": "Not Approved", "mobile": mobile, "email": PATIENT_EMAIL}).json()["id"]
    consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]
    client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": str(uuid.uuid4()), "duration_seconds": 2},
        files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
    )
    with SessionLocal() as db:
        db.add(Transcription(
            consultation_id=consultation_id, clinic_id=1, provider="mock",
            provider_model="mock", status="completed", transcript_text="x",
        ))
        db.commit()
    assert client.post(f"/consultations/{consultation_id}/report/generate").status_code == 200
    assert client.post(f"/consultations/{consultation_id}/report/deliver").status_code == 409


def test_deliver_requires_patient_email(client, monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_approved_report(client, email=None)

    resp = client.post(f"/consultations/{consultation_id}/report/deliver")
    assert resp.status_code == 409
    assert "email" in resp.json()["detail"].lower()

    with SessionLocal() as db:
        assert db.query(ReportDelivery).filter(ReportDelivery.report_id == 1).count() == 0


def test_deliver_duplicate_sent_blocked(client, monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_approved_report(client)

    assert client.post(f"/consultations/{consultation_id}/report/deliver").status_code == 200
    dup = client.post(f"/consultations/{consultation_id}/report/deliver")
    assert dup.status_code == 409
    assert "already" in dup.json()["detail"].lower()


def test_deliver_failure_allows_reattempt(client, monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_approved_report(client)

    def failing_provider():
        class Failing:
            def send(self, *a, **k):
                return DeliveryResult("failed", "SMTP error: SMTPServerDisconnected")
        return Failing()

    monkeypatch.setattr("app.services.report_service.get_delivery_provider", failing_provider)
    first = client.post(f"/consultations/{consultation_id}/report/deliver")
    assert first.status_code == 200
    assert first.json()["status"] == "failed"
    assert "SMTPServerDisconnected" in first.json()["error_message"]
    assert "smtp" in first.json()["error_message"].lower()

    monkeypatch.setattr("app.services.report_service.get_delivery_provider", lambda: MockReportProvider("ok"))
    # re-attempt allowed after failure: replace provider with a successful mock provider
    class GoodProvider:
        def send(self, *a, **k):
            return DeliveryResult("sent", None)
    monkeypatch.setattr("app.services.report_service.get_delivery_provider", lambda: GoodProvider())
    second = client.post(f"/consultations/{consultation_id}/report/deliver")
    assert second.status_code == 200
    assert second.json()["status"] == "sent"


def test_delivery_list_endpoint(client, monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_approved_report(client)
    client.post(f"/consultations/{consultation_id}/report/deliver")

    resp = client.get(f"/consultations/{consultation_id}/report/deliveries")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["status"] == "sent"
    assert items[0]["channel"] == "email"
    assert items[0]["report_id"] == 1


def test_deliver_cross_clinic_isolation(client, monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_approved_report(client)

    _create_other_clinic_user()
    _login(client, "other@example.com", "other-pass-1")
    assert client.post(f"/consultations/{consultation_id}/report/deliver").status_code == 404
    assert client.get(f"/consultations/{consultation_id}/report/pdf").status_code == 404
    assert client.get(f"/consultations/{consultation_id}/report/deliveries").status_code == 404


def test_deliver_requires_auth(client):
    assert client.post("/consultations/1/report/deliver").status_code == 401
    assert client.get("/consultations/1/report/deliveries").status_code == 401
