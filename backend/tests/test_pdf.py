import random
import uuid

from app.core.ai.mock import MockReportProvider
from app.db import SessionLocal
from app.models import Transcription

BOOT = {
    "email": "owner@example.com",
    "password": "super-secret-1",
    "full_name": "Owner User",
    "clinic_name": "Test Clinic",
}
WAV_BYTES = b"RIFF0000WAVE" + b"\x00" * 64


def _bootstrap(client):
    assert client.post("/auth/bootstrap", json=BOOT).status_code == 201


def _login(client):
    assert client.post("/auth/login", json={"email": BOOT["email"], "password": BOOT["password"]}).status_code == 200


def _setup_completed_consultation(client):
    mobile = f"+1888{random.randint(100000,999999)}"
    patient_id = client.post("/patients", json={"full_name": "PDF Patient", "mobile": mobile}).json()["id"]
    consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]
    up = client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": str(uuid.uuid4()), "duration_seconds": 3},
        files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
    )
    assert up.status_code == 201
    with SessionLocal() as db:
        transcription = Transcription(
            consultation_id=consultation_id,
            clinic_id=1,
            provider="mock",
            provider_model="mock",
            status="completed",
            transcript_text="Patient reports fever. Diagnosis: upper respiratory tract infection. Paracetamol 500 mg advised.",
        )
        db.add(transcription)
        db.commit()
    return patient_id, consultation_id


def _generate_and_approve(client, consultation_id):
    assert client.post(f"/consultations/{consultation_id}/report/generate").status_code == 200
    assert client.post(f"/consultations/{consultation_id}/report/approve").status_code == 200


def test_pdf_download_for_approved_report(client, monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    _bootstrap(client)
    _login(client)
    _, consultation_id = _setup_completed_consultation(client)
    _generate_and_approve(client, consultation_id)

    resp = client.get(f"/consultations/{consultation_id}/report/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert len(resp.content) > 500
    assert b"/Page" in resp.content


def test_pdf_requires_approved_report(client, monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    _bootstrap(client)
    _login(client)
    _, consultation_id = _setup_completed_consultation(client)
    assert client.post(f"/consultations/{consultation_id}/report/generate").status_code == 200

    assert client.get(f"/consultations/{consultation_id}/report/pdf").status_code == 409


def test_pdf_requires_auth(client):
    assert client.get("/consultations/1/report/pdf").status_code == 401


def test_pdf_renders_devanagari(client, monkeypatch):
    # Synthetic transcript containing Hindi text (Devanagari).
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    _bootstrap(client)
    _login(client)
    mobile = f"+1888{random.randint(100000, 999999)}"
    patient_id = client.post("/patients", json={"full_name": "हिन्दी रोगी", "mobile": mobile}).json()["id"]
    consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]
    up = client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": str(uuid.uuid4()), "duration_seconds": 3},
        files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
    )
    assert up.status_code == 201
    with SessionLocal() as db:
        db.add(Transcription(
            consultation_id=consultation_id, clinic_id=1, provider="mock",
            provider_model="mock", status="completed",
            transcript_text="मरीज को बुखार है। निदान: ऊपरी श्वसन संक्रमण।",
        ))
        db.commit()
    assert client.post(f"/consultations/{consultation_id}/report/generate").status_code == 200
    assert client.post(f"/consultations/{consultation_id}/report/approve").status_code == 200

    resp = client.get(f"/consultations/{consultation_id}/report/pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
    # A Unicode-font PDF is significantly larger than the old Latin-1 PDF.
    assert len(resp.content) > 3000
