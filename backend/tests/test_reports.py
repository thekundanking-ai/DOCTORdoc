import uuid

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.core.ai.mock import MockReportProvider
from app.db import SessionLocal
from app.models import Clinic, ConsultationReport, Transcription, User
from app.services import report_service

BOOT = {
    "email": "owner@example.com",
    "password": "super-secret-1",
    "full_name": "Owner User",
    "clinic_name": "Test Clinic",
}

WAV_BYTES = b"RIFF0000WAVE" + b"\x00" * 64


def _bootstrap(client) -> None:
    assert client.post("/auth/bootstrap", json=BOOT).status_code == 201


def _login(client, email=BOOT["email"], password=BOOT["password"]) -> None:
    assert client.post("/auth/login", json={"email": email, "password": password}).status_code == 200


def _setup_completed_consultation(client, transcript: str | None = None) -> int:
    patient_id = client.post("/patients", json={"full_name": "Report Patient", "mobile": "+18881234567"}).json()["id"]
    consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]

    up = client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": str(uuid.uuid4()), "duration_seconds": 3},
        files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
    )
    assert up.status_code == 201

    # complete a transcription directly so the transcript exists
    with SessionLocal() as db:
        transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one_or_none()
        if transcription is None:
            transcription = Transcription(
                consultation_id=consultation_id,
                clinic_id=1,
                provider="mock",
                provider_model="mock",
                status="completed",
                transcript_text=transcript
                or "Patient reports fever and sore throat. Diagnosis: upper respiratory tract infection. Paracetamol 500 mg advised.",
            )
            db.add(transcription)
        else:
            transcription.status = "completed"
            transcription.transcript_text = transcript or "Patient reports fever and sore throat. Diagnosis: upper respiratory tract infection. Paracetamol 500 mg advised."
            transcription.completed_at = None
        db.commit()
    return consultation_id


def _create_other_clinic_user() -> None:
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
        )
        db.add(user)
        db.commit()


def test_generate_report_success(client, monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_completed_consultation(client)

    resp = client.post(f"/consultations/{consultation_id}/report/generate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "generated"
    assert body["structured_report"]["chief_complaint"]
    assert body["structured_report"]["diagnosis"]
    assert body["structured_report"]["medications"][0]["name"] == "Paracetamol"

    saved = client.get(f"/consultations/{consultation_id}/report").json()
    assert saved["id"] == body["id"]


def test_generate_requires_completed_transcript(client):
    _bootstrap(client)
    _login(client)
    patient_id = client.post("/patients", json={"full_name": "No Transcription", "mobile": "+18880000000"}).json()["id"]
    consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]
    assert client.post(f"/consultations/{consultation_id}/report/generate").status_code == 409


def test_failed_regeneration_preserves_existing_draft(client, monkeypatch):
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_completed_consultation(client)

    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    first = client.post(f"/consultations/{consultation_id}/report/generate").json()
    assert first["status"] == "generated"

    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("timeout"))
    resp = client.post(f"/consultations/{consultation_id}/report/generate")
    assert resp.status_code == 502
    after = client.get(f"/consultations/{consultation_id}/report").json()
    assert after["status"] == "generated"
    assert after["structured_report"]["diagnosis"] == first["structured_report"]["diagnosis"]


def test_approved_report_immutable(client):
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_completed_consultation(client)
    client.post(f"/consultations/{consultation_id}/report/generate")

    approve = client.post(f"/consultations/{consultation_id}/report/approve")
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"
    assert approve.json()["approved_by"] == 1

    assert client.patch(f"/consultations/{consultation_id}/report", json={"diagnosis": "changed"}).status_code == 409
    assert client.post(f"/consultations/{consultation_id}/report/generate").status_code == 409


def test_approve_requires_content(client):
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_completed_consultation(client)
    assert client.post(f"/consultations/{consultation_id}/report/approve").status_code == 404


def test_draft_edit_flow(client):
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_completed_consultation(client)
    client.post(f"/consultations/{consultation_id}/report/generate")

    patch = client.patch(f"/consultations/{consultation_id}/report", json={"diagnosis": "Doctor-confirmed URTI"})
    assert patch.status_code == 200
    assert patch.json()["status"] == "draft"
    assert patch.json()["structured_report"]["diagnosis"] == "Doctor-confirmed URTI"


def test_guardrail_flags_hallucinated_diagnosis(client, monkeypatch):
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("hallucination"))
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_completed_consultation(client, transcript="Patient reports fever.")
    body = client.post(f"/consultations/{consultation_id}/report/generate").json()
    assert body["structured_report"]["diagnosis"] is None
    flag_text = "".join(body["structured_report"]["unclear_or_missing"])
    assert "Diagnosis" in flag_text


def test_cross_clinic_report_isolation(client):
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_completed_consultation(client)
    client.post(f"/consultations/{consultation_id}/report/generate")

    _create_other_clinic_user()
    _login(client, "other@example.com", "other-pass-1")
    assert client.get(f"/consultations/{consultation_id}/report").status_code == 404
    assert client.post(f"/consultations/{consultation_id}/report/generate").status_code == 404
    assert client.patch(f"/consultations/{consultation_id}/report", json={"diagnosis": "x"}).status_code == 404
    assert client.post(f"/consultations/{consultation_id}/report/approve").status_code == 404


def test_report_requires_auth(client):
    assert client.get("/consultations/1/report").status_code == 401
    assert client.post("/consultations/1/report/generate").status_code == 401


def test_duplicate_generation_guard(client):
    _bootstrap(client)
    _login(client)
    consultation_id = _setup_completed_consultation(client)

    # simulate an in-progress report: create directly and set generating
    with SessionLocal() as db:
        report = ConsultationReport(
            consultation_id=consultation_id,
            clinic_id=1,
            patient_id=1,
            transcript_snapshot="x",
            status="generating",
            provider="mock",
            model="mock",
        )
        db.add(report)
        db.commit()

    assert client.post(f"/consultations/{consultation_id}/report/generate").status_code == 409
