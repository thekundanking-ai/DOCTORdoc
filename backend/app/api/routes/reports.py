from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import Consultation, ConsultationReport, ReportDelivery, User
from app.schemas.report import ReportUpdate
from app.services import report_service

router = APIRouter()


class ConsultationReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    consultation_id: int
    clinic_id: int
    patient_id: int
    status: str
    provider: str
    model: str
    structured_report: dict | None
    error_code: str | None
    error_message: str | None
    approved_at: object | None
    approved_by: int | None
    created_at: object
    updated_at: object


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    clinic_id: int
    channel: str
    status: str
    error_message: str | None
    delivered_at: object | None
    created_at: object


def _get_scoped_consultation(db: Session, consultation_id: int, clinic_id: int) -> Consultation | None:
    return db.scalar(
        select(Consultation).where(Consultation.id == consultation_id, Consultation.clinic_id == clinic_id)
    )


@router.post("/{consultation_id}/report/generate", response_model=ConsultationReportOut)
def generate(
    consultation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsultationReport:
    return report_service.generate_report(db, consultation_id, user)


@router.get("/{consultation_id}/report", response_model=ConsultationReportOut)
def get_report(
    consultation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsultationReport:
    consultation = _get_scoped_consultation(db, consultation_id, user.clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
    report = db.scalar(select(ConsultationReport).where(ConsultationReport.consultation_id == consultation_id))
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No report found")
    return report


@router.patch("/{consultation_id}/report", response_model=ConsultationReportOut)
def update_report(
    consultation_id: int,
    payload: ReportUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsultationReport:
    return report_service.update_report(db, consultation_id, user, payload.model_dump(exclude_none=True))


@router.post("/{consultation_id}/report/approve", response_model=ConsultationReportOut)
def approve(
    consultation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsultationReport:
    return report_service.approve_report(db, consultation_id, user)


@router.get("/{consultation_id}/report/pdf")
def download_report_pdf(
    consultation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    pdf = report_service.render_report_pdf(db, consultation_id, user.clinic_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report-{consultation_id}.pdf"'},
    )


@router.post("/{consultation_id}/report/deliver", response_model=DeliveryOut)
def deliver(
    consultation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportDelivery:
    return report_service.deliver_report(db, consultation_id, user)
