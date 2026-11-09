import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audio_validation import sha256_hex, sniff_audio_type
from app.core.config import settings
from app.core.storage import AudioStorage, get_audio_storage
from app.db import get_db
from app.models import AudioAttachment, Consultation, ConsultationStatus, Patient, User

router = APIRouter()


class ConsultationCreate(BaseModel):
    patient_id: int


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    consultation_id: int
    mime_type: str
    file_size_bytes: int
    duration_seconds: float | None
    uploaded_at: object
    expires_at: object


class ConsultationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clinic_id: int
    patient_id: int
    created_by_user_id: int
    status: str
    started_at: object
    ended_at: object | None
    created_at: object
    updated_at: object
    audio: AttachmentOut | None = None


class ConsultationList(BaseModel):
    items: list[ConsultationOut]
    total: int
    page: int
    page_size: int


def _get_scoped_patient(db: Session, patient_id: int, clinic_id: int) -> Patient | None:
    return db.scalar(select(Patient).where(Patient.id == patient_id, Patient.clinic_id == clinic_id))


def _get_scoped_consultation(db: Session, consultation_id: int, clinic_id: int) -> Consultation | None:
    return db.scalar(
        select(Consultation).where(Consultation.id == consultation_id, Consultation.clinic_id == clinic_id)
    )


def _load_attachments(db: Session, consultation_ids: list[int]) -> dict[int, AudioAttachment]:
    if not consultation_ids:
        return {}
    rows = db.scalars(select(AudioAttachment).where(AudioAttachment.consultation_id.in_(consultation_ids))).all()
    return {row.consultation_id: row for row in rows}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConsultationOut)
def create_consultation(
    payload: ConsultationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Consultation:
    patient = _get_scoped_patient(db, payload.patient_id, user.clinic_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    consultation = Consultation(
        clinic_id=user.clinic_id,
        patient_id=patient.id,
        created_by_user_id=user.id,
    )
    db.add(consultation)
    db.commit()
    db.refresh(consultation)
    return consultation


@router.get("", response_model=ConsultationList)
def list_consultations(
    patient_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsultationList:
    patient = _get_scoped_patient(db, patient_id, user.clinic_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    base = select(Consultation).where(Consultation.clinic_id == user.clinic_id, Consultation.patient_id == patient_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = db.scalars(
        base.order_by(Consultation.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()

    attachments = _load_attachments(db, [item.id for item in items])
    results = []
    for item in items:
        out = ConsultationOut.model_validate(item)
        out.audio = AttachmentOut.model_validate(attachments[item.id]) if item.id in attachments else None
        results.append(out)

    return ConsultationList(items=results, total=total, page=page, page_size=page_size)


@router.get("/{consultation_id}", response_model=ConsultationOut)
def get_consultation(
    consultation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsultationOut:
    consultation = _get_scoped_consultation(db, consultation_id, user.clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")

    out = ConsultationOut.model_validate(consultation)
    attachment = db.scalar(select(AudioAttachment).where(AudioAttachment.consultation_id == consultation.id))
    if attachment is not None:
        out.audio = AttachmentOut.model_validate(attachment)
    return out


@router.post("/{consultation_id}/audio", status_code=status.HTTP_201_CREATED, response_model=AttachmentOut)
def upload_audio(
    consultation_id: int,
    upload_id: str = Form(...),
    file: UploadFile = File(...),
    duration_seconds: float | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AudioAttachment:
    consultation = _get_scoped_consultation(db, consultation_id, user.clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")

    existing = db.scalar(select(AudioAttachment).where(AudioAttachment.consultation_id == consultation.id))
    if existing is not None:
        if str(existing.upload_id) == upload_id:
            return existing
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Audio already uploaded")

    try:
        parsed_upload_id = uuid.UUID(upload_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid upload_id")

    data = file.file.read(settings.max_audio_bytes + 1)
    if not data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty file")
    if len(data) > settings.max_audio_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    detected = sniff_audio_type(data)
    if detected is None:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported audio type")

    if duration_seconds is not None and (
        duration_seconds <= 0 or duration_seconds > settings.audio_max_duration_seconds
    ):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid duration")

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.audio_retention_days)
    attachment = AudioAttachment(
        consultation_id=consultation.id,
        upload_id=parsed_upload_id,
        storage_key=secrets.token_hex(16),
        mime_type=detected[0],
        file_size_bytes=len(data),
        duration_seconds=duration_seconds,
        sha256=sha256_hex(data),
        data=data,
        expires_at=expires_at,
    )
    consultation.status = ConsultationStatus.awaiting_transcription.value

    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


@router.get("/{consultation_id}/audio")
def stream_audio(
    consultation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: AudioStorage = Depends(get_audio_storage),
) -> Response:
    consultation = _get_scoped_consultation(db, consultation_id, user.clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")

    attachment = db.scalar(select(AudioAttachment).where(AudioAttachment.consultation_id == consultation.id))
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No audio uploaded")

    blob = storage.open(attachment.storage_key)
    if blob is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio unavailable")
    return Response(content=blob, media_type=attachment.mime_type)


@router.post("/{consultation_id}/cancel", response_model=ConsultationOut)
def cancel_consultation(
    consultation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsultationOut:
    consultation = _get_scoped_consultation(db, consultation_id, user.clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
    if consultation.status != ConsultationStatus.open_.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Consultation cannot be cancelled")

    consultation.status = ConsultationStatus.cancelled.value
    consultation.ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(consultation)
    return ConsultationOut.model_validate(consultation)
