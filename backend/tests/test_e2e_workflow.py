import random
import uuid
from datetime import datetime, timedelta, timezone

from app.core.ai.mock import MockReportProvider
from app.core.stt.mock import MockSpeechToTextProvider
from app.core.transcription_worker import process_pending
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


def _pump(consultation_id, max_iter=8):
    for _ in range(max_iter):
        process_pending()
        with SessionLocal() as db:
            transcription = db.query(Transcription).filter(Transcription.consultation_id == consultation_id).one_or_none()
            if transcription is None or transcription.status in ("completed", "failed"):
                return
            transcription.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()


def test_full_mock_workflow(client, monkeypatch):
    _bootstrap(client)
    _login(client)

    # 2. create patient
    patient_id = client.post(
        "/patients", json={"full_name": "E2E Patient", "mobile": f"+1888{random.randint(100000,999999)}"}
    ).json()["id"]

    # 3. consultation + audio
    consultation_id = client.post("/consultations", json={"patient_id": patient_id}).json()["id"]
    up = client.post(
        f"/consultations/{consultation_id}/audio",
        data={"upload_id": str(uuid.uuid4()), "duration_seconds": 3},
        files={"file": ("recording.bin", WAV_BYTES, "application/octet-stream")},
    )
    assert up.status_code == 201

    # 4. complete mock transcription
    monkeypatch.setattr(
        "app.core.transcription_worker.get_provider", lambda: MockSpeechToTextProvider("completed")
    )
    assert client.post(f"/consultations/{consultation_id}/transcription").status_code == 201
    _pump(consultation_id)
    transcription = client.get(f"/consultations/{consultation_id}/transcription").json()
    assert transcription["status"] == "completed"
    assert transcription["transcript_text"]

    # 5. generate mock report
    monkeypatch.setattr("app.services.report_service.get_report_provider", lambda: MockReportProvider("ok"))
    report = client.post(f"/consultations/{consultation_id}/report/generate").json()
    assert report["status"] == "generated"

    # 6. edit + approve
    patched = client.patch(
        f"/consultations/{consultation_id}/report",
        json={"diagnosis": "Doctor-confirmed URTI"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "draft"
    approved = client.post(f"/consultations/{consultation_id}/report/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    # 7. PDF
    pdf = client.get(f"/consultations/{consultation_id}/report/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    # 8. deliver (mock)
    delivery = client.post(f"/consultations/{consultation_id}/report/deliver")
    assert delivery.status_code == 200
    assert delivery.json()["status"] == "sent"

    # 9. consultation history shows the completed consultation
    history = client.get("/consultations", params={"patient_id": patient_id}).json()
    assert history["total"] == 1
    item = history["items"][0]
    assert item["id"] == consultation_id
    assert item["status"] == "completed"
    assert item["audio"] is None  # audio deleted after successful transcription

    report = client.get(f"/consultations/{consultation_id}/report").json()
    assert report["status"] == "approved"
    assert report["structured_report"]
