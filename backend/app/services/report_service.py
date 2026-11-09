import re
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai import get_report_provider
from app.core.ai.base import ReportProviderError
from app.core.delivery import get_delivery_provider
from app.models import (
    Consultation,
    ConsultationReport,
    DeliveryStatus,
    Patient,
    ReportDelivery,
    ReportStatus,
    Transcription,
    TranscriptionStatus,
    User,
)
from app.schemas.report import StructuredReport
from app.services.report_pdf import build_report_pdf


def _get_scoped_consultation(db: Session, consultation_id: int, clinic_id: int) -> Consultation | None:
    return db.scalar(
        select(Consultation).where(Consultation.id == consultation_id, Consultation.clinic_id == clinic_id)
    )


def _get_report(db: Session, consultation_id: int) -> ConsultationReport | None:
    return db.scalar(select(ConsultationReport).where(ConsultationReport.consultation_id == consultation_id))


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z]{4,}", text.lower())}


def _mentions(transcript: str, phrase: str) -> bool:
    if not phrase:
        return True
    return bool(_terms(transcript) & _terms(phrase))


def _apply_guardrails(structured: dict, transcript: str) -> dict:
    """Flag content not verifiably present in the transcript; never invent clinical facts."""
    uncertain = list(structured.get("unclear_or_missing") or [])

    diagnosis = structured.get("diagnosis")
    if diagnosis and not _mentions(transcript, diagnosis):
        structured["diagnosis"] = None
        uncertain.append("Diagnosis was not found in the transcript — confirm before using.")

    for med in structured.get("medications") or []:
        name = med.get("name")
        if name and not _mentions(transcript, name):
            uncertain.append(f"Medication '{name}' not found in the transcript — confirm the prescription.")

    structured["unclear_or_missing"] = uncertain
    return structured


def _validate_structured(data: dict, transcript: str) -> dict:
    try:
        model = StructuredReport.model_validate(data)
    except Exception:
        raise ReportProviderError("INVALID_RESPONSE", "Provider returned a report that failed validation.", retryable=True)
    structured = model.model_dump()
    return _apply_guardrails(structured, transcript)


def generate_report(db: Session, consultation_id: int, user: User, provider=None) -> ConsultationReport:
    consultation = _get_scoped_consultation(db, consultation_id, user.clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")

    transcription = db.scalar(
        select(Transcription).where(
            Transcription.consultation_id == consultation_id,
            Transcription.status == TranscriptionStatus.completed.value,
        )
    )
    if transcription is None or not transcription.transcript_text:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A completed transcript is required")

    patient = db.get(Patient, consultation.patient_id)
    patient_meta = {
        "name": patient.full_name if patient else None,
        "mobile": patient.mobile if patient else None,
        "consultation_date": consultation.started_at.isoformat() if consultation.started_at else None,
    }

    provider = provider or get_report_provider()
    existing = _get_report(db, consultation_id)

    if existing is not None:
        if existing.status == ReportStatus.approved.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved reports cannot be regenerated")
        if existing.status == ReportStatus.generating.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report generation already in progress")

    if existing is None:
        existing = ConsultationReport(
            consultation_id=consultation_id,
            clinic_id=user.clinic_id,
            patient_id=consultation.patient_id,
            transcript_snapshot=transcription.transcript_text,
            status=ReportStatus.generating.value,
            provider=type(provider).__name__,
            model=getattr(provider, "_model", "mock"),
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
        prev_draft = None
    else:
        prev_draft = existing.structured_report
        existing.status = ReportStatus.generating.value
        existing.error_code = None
        existing.error_message = None
        existing.transcript_snapshot = transcription.transcript_text
        db.commit()

    try:
        result = provider.generate_report(transcription.transcript_text, patient_meta)
        structured = _validate_structured(result.structured, transcription.transcript_text)
        existing.structured_report = structured
        existing.status = ReportStatus.generated.value
        existing.error_code = None
        existing.error_message = None
        db.commit()
        db.refresh(existing)
        return existing
    except ReportProviderError as exc:
        if prev_draft is not None:
            existing.structured_report = prev_draft
            existing.status = ReportStatus.generated.value
        else:
            existing.structured_report = None
            existing.status = ReportStatus.failed.value
        existing.error_code = exc.code
        existing.error_message = exc.message
        db.commit()
        db.refresh(existing)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Report generation failed. You can retry.")


def update_report(db: Session, consultation_id: int, user: User, structured: dict) -> ConsultationReport:
    consultation = _get_scoped_consultation(db, consultation_id, user.clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
    report = _get_report(db, consultation_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No report found")

    if report.status == ReportStatus.approved.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved reports are immutable")
    if report.status == ReportStatus.generating.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report is still generating")

    try:
        model = StructuredReport.model_validate(structured)
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid report data")

    report.structured_report = model.model_dump()
    report.status = ReportStatus.draft.value
    db.commit()
    db.refresh(report)
    return report


def approve_report(db: Session, consultation_id: int, user: User) -> ConsultationReport:
    from datetime import datetime, timezone

    consultation = _get_scoped_consultation(db, consultation_id, user.clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
    report = _get_report(db, consultation_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No report found")
    if report.status == ReportStatus.approved.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report already approved")
    if report.status not in (ReportStatus.generated.value, ReportStatus.draft.value):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report is not ready to approve")
    if not report.structured_report:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report has no content to approve")

    report.status = ReportStatus.approved.value
    report.approved_at = datetime.now(timezone.utc)
    report.approved_by = user.id
    db.commit()
    db.refresh(report)
    return report


def _get_approved_report(db: Session, consultation_id: int, clinic_id: int) -> ConsultationReport:
    consultation = _get_scoped_consultation(db, consultation_id, clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
    report = _get_report(db, consultation_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No report found")
    if report.status != ReportStatus.approved.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report is not approved")
    return report


def render_report_pdf(db: Session, consultation_id: int, clinic_id: int) -> bytes:
    report = _get_approved_report(db, consultation_id, clinic_id)
    consultation = db.get(Consultation, report.consultation_id)
    patient = db.get(Patient, report.patient_id)
    return build_report_pdf(report, patient, consultation)


def deliver_report(db: Session, consultation_id: int, user: User) -> ReportDelivery:
    report = _get_approved_report(db, consultation_id, user.clinic_id)
    consultation = db.get(Consultation, report.consultation_id)
    patient = db.get(Patient, report.patient_id)

    pdf_bytes = build_report_pdf(report, patient, consultation)
    recipient = patient.mobile if patient else None
    provider = get_delivery_provider()

    try:
        result = provider.send(
            recipient=recipient or "unknown",
            subject=f"Consultation report #{consultation_id}",
            payload_bytes=pdf_bytes,
            payload_type="application/pdf",
            meta={"consultation_id": consultation_id, "report_id": report.id},
        )
    except Exception:
        result = None

    delivery = ReportDelivery(
        report_id=report.id,
        clinic_id=user.clinic_id,
        channel="sms",
    )
    if result and result.status == "sent":
        delivery.status = DeliveryStatus.sent.value
        delivery.delivered_at = datetime.now(timezone.utc)
    else:
        delivery.status = DeliveryStatus.failed.value
        delivery.error_message = (result.message if result else "Delivery provider error")
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return delivery
