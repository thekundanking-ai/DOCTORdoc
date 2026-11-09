from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.stt import get_provider
from app.db import get_db
from app.models import AudioAttachment, Consultation, Transcription, TranscriptionStatus, User

router = APIRouter()

RETRYABLE_TRANSIENT = {
    "PROVIDER_TIMEOUT",
    "PROVIDER_UNAVAILABLE",
    "CREATE_FAILED",
    "START_FAILED",
    "NO_TRANSCRIPT",
    "NO_TRANSCRIPT_URL",
    "TRANSCRIPT_DOWNLOAD_FAILED",
    "TRANSCRIPTION_FAILED",
    "EMPTY_TRANSCRIPT",
    "UNKNOWN_STATUS",
}


class TranscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    consultation_id: int
    clinic_id: int
    provider: str
    provider_model: str
    provider_job_id: str | None
    status: str
    language_code: str
    format: str
    transcript_text: str | None
    detected_language: str | None
    processing_time_ms: int | None
    error_code: str | None
    error_message: str | None
    retry_count: int
    provider_status: str | None
    poll_count: int
    deadline_at: object | None
    submitted_at: object | None
    completed_at: object | None
    created_at: object
    updated_at: object


def _get_scoped_consultation(db: Session, consultation_id: int, clinic_id: int) -> Consultation | None:
    return db.scalar(
        select(Consultation).where(Consultation.id == consultation_id, Consultation.clinic_id == clinic_id)
    )


def _get_transcription(db: Session, consultation_id: int, clinic_id: int | None = None) -> Transcription | None:
    stmt = select(Transcription).where(Transcription.consultation_id == consultation_id)
    if clinic_id is not None:
        stmt = stmt.where(Transcription.clinic_id == clinic_id)
    return db.scalar(stmt)


@router.post("/{consultation_id}/transcription", response_model=TranscriptionOut, status_code=status.HTTP_201_CREATED)
def start_transcription(
    consultation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Transcription:
    consultation = _get_scoped_consultation(db, consultation_id, user.clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")

    if _get_transcription(db, consultation_id, user.clinic_id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transcription already started")

    audio = db.scalar(select(AudioAttachment).where(AudioAttachment.consultation_id == consultation_id))
    if audio is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No audio uploaded")

    if audio.file_size_bytes > settings.gnani_direct_upload_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="This recording exceeds the provider's 10 MB direct-upload limit",
        )

    try:
        provider_name = type(get_provider()).__name__
    except Exception:
        provider_name = "unknown"

    transcription = Transcription(
        consultation_id=consultation_id,
        clinic_id=user.clinic_id,
        provider=provider_name,
        provider_model=settings.gnani_stt_model,
        status=TranscriptionStatus.submitting.value,
        language_code=settings.gnani_language_code,
        format=settings.gnani_stt_format,
    )
    db.add(transcription)
    db.commit()
    db.refresh(transcription)
    return transcription


@router.get("/{consultation_id}/transcription", response_model=TranscriptionOut)
def get_transcription(
    consultation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Transcription:
    consultation = _get_scoped_consultation(db, consultation_id, user.clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")

    transcription = _get_transcription(db, consultation_id, user.clinic_id)
    if transcription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No transcription found")

    return transcription


@router.post("/{consultation_id}/transcription/retry", response_model=TranscriptionOut)
def retry_transcription(
    consultation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Transcription:
    consultation = _get_scoped_consultation(db, consultation_id, user.clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")

    transcription = _get_transcription(db, consultation_id, user.clinic_id)
    if transcription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No transcription found")

    if transcription.status != TranscriptionStatus.failed.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transcription is not in a retryable state")

    if transcription.error_code not in RETRYABLE_TRANSIENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This failure is not retryable"
        )
    if transcription.retry_count >= settings.gnani_max_retries:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Maximum retries reached")

    if transcription.deadline_at is not None and datetime.now(timezone.utc) >= transcription.deadline_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This transcription is past its overall deadline and cannot be retried",
        )

    # Retry semantics: a manual retry restarts a fresh, bounded polling attempt.
    # poll_count resets (per-attempt poll budget) while the persistent overall
    # deadline (deadline_at) and the provider job id are preserved. Attempts
    # remain bounded by retry_count and the absolute deadline.
    transcription.status = TranscriptionStatus.submitting.value
    transcription.next_retry_at = None
    transcription.retry_count += 1
    transcription.poll_count = 0
    transcription.error_code = None
    transcription.error_message = None
    db.commit()
    db.refresh(transcription)
    return transcription
