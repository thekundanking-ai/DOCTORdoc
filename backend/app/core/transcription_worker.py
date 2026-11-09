import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import DatabaseAudioStorage
from app.core.stt.base import ProviderError
from app.core.stt.base import TERMINAL_STATUSES as PROVIDER_TERMINAL
from app.core.stt import get_provider
from app.db import SessionLocal
from app.models import AudioAttachment, Consultation, ConsultationStatus, Transcription, TranscriptionStatus

logger = logging.getLogger(__name__)

# Concurrency: this worker is designed for a SINGLE worker process (the current
# single-backend deployment). The claim mechanism (`_claim_next`) is a
# check-then-set using the `processing_started_at` heartbeat and is NOT atomic;
# running multiple worker processes could claim the same transcription
# concurrently. Do not scale to multiple workers without adding DB-level
# claiming (e.g. `SELECT ... FOR UPDATE SKIP LOCKED` or an atomic guarded UPDATE).

PROVIDER_ACTIVE = {"CREATED", "STARTING", "QUEUED", "IN_PROGRESS"}
LOCAL_ACTIVE = {TranscriptionStatus.submitting.value, TranscriptionStatus.processing.value}

# The minimum interval between provider polls is sourced from
# settings.gnani_poll_interval_seconds (single authoritative value).
MAX_BACKOFF_SECONDS = 300
_POLL_RETRY_JITTER = (0.8, 1.2)


def _now():
    return datetime.now(timezone.utc)


def _backoff(retry_after: int | None, attempt: int) -> int:
    """Bounded exponential backoff with jitter and optional Retry-After override."""
    if retry_after is not None:
        base = retry_after
    else:
        base = settings.gnani_poll_interval_seconds * (2 ** max(attempt - 1, 0))
    jitter = random.uniform(*_POLL_RETRY_JITTER)
    seconds = int(base * jitter)
    return max(settings.gnani_poll_interval_seconds, min(seconds, MAX_BACKOFF_SECONDS))


def _deadline(transcription: Transcription) -> datetime:
    """Persistent overall deadline for a job.

    Uses the stored `deadline_at` when present (set once on first successful
    submission and never reset). For legacy/never-submitted rows it falls back
    to the submit or creation anchor so old rows are still bounded.
    """
    if transcription.deadline_at is not None:
        return transcription.deadline_at
    anchor = transcription.submitted_at or transcription.created_at or _now()
    return anchor + timedelta(seconds=settings.gnani_job_deadline_seconds)


def _timed_out(transcription: Transcription) -> bool:
    return _now() >= _deadline(transcription)


def _claim_next(db: Session) -> Transcription | None:
    """Claim the next due transcription (safe across restarts).

    - Failed rows are only re-processed up to the retry cap.
    - In-progress (submitting/processing) rows are always resumable once their
      scheduled `next_retry_at` has passed.
    - `processing_started_at` guards against concurrent workers claiming the same row.
    """
    now = _now()
    candidates = db.scalars(
        select(Transcription).where(
            Transcription.status.in_(LOCAL_ACTIVE | {TranscriptionStatus.failed.value}),
            ((Transcription.next_retry_at.is_(None)) | (Transcription.next_retry_at <= now)),
            or_(
                Transcription.status != TranscriptionStatus.failed.value,
                Transcription.retry_count < settings.gnani_max_retries,
            ),
        )
    ).all()
    for transcription in candidates:
        if transcription.processing_started_at and (
            _now() - transcription.processing_started_at < timedelta(seconds=120)
        ):
            continue
        transcription.processing_started_at = now
        return transcription
    return None


def _schedule_transient(db: Session, transcription: Transcription, retry_after: int | None) -> None:
    """Persist a bounded, transient poll/retry wait (does NOT mark failed)."""
    transcription.retry_count += 1
    transcription.next_retry_at = _now() + timedelta(seconds=_backoff(retry_after, transcription.retry_count))
    transcription.processing_started_at = None
    db.commit()


def _mark_failed(db: Session, transcription: Transcription, code: str, message: str) -> None:
    """Permanent failure: stop reprocessing permanently."""
    db.rollback()
    transcription.status = TranscriptionStatus.failed.value
    transcription.error_code = code
    transcription.error_message = message
    transcription.processing_started_at = None
    transcription.retry_count = settings.gnani_max_retries
    transcription.next_retry_at = None
    db.commit()
    logger.warning("transcription %s failed permanently: %s", transcription.id, code)


def _run_turn(db: Session, transcription: Transcription) -> None:
    provider = get_provider()

    if _timed_out(transcription):
        _mark_failed(db, transcription, "PROCESSING_TIMEOUT", "Transcription exceeded the maximum allowed time.")
        return

    audio = db.scalar(select(AudioAttachment).where(AudioAttachment.consultation_id == transcription.consultation_id))
    if audio is None:
        _mark_failed(db, transcription, "AUDIO_MISSING", "No audio is available for transcription.")
        return

    # --- Phase 1: create the provider job (ONLY if we have no job id yet) ---
    if not transcription.provider_job_id:
        try:
            job_id = provider.create_job(audio.data, audio.mime_type)
        except ProviderError as exc:
            if exc.retryable:
                _schedule_transient(db, transcription, exc.retry_after)
            else:
                _mark_failed(db, transcription, exc.code, exc.message or "Provider rejected the audio.")
            return
        except Exception:
            logger.exception("transcription %s create crashed", transcription.id)
            _schedule_transient(db, transcription, None)
            return
        # M3: remote job creation happens BEFORE we persist provider_job_id.
        # If the process dies in this window, the restart has no job id and will
        # call create_job() again -> a duplicate remote job. Closing this window
        # requires provider-side idempotency (a contract change); documented, not
        # implemented here to avoid duplicate submissions.
        transcription.provider_job_id = job_id
        transcription.submitted_at = _now()
        if transcription.deadline_at is None:
            transcription.deadline_at = _now() + timedelta(seconds=settings.gnani_job_deadline_seconds)
        transcription.status = TranscriptionStatus.submitting.value
        transcription.error_code = None
        transcription.error_message = None
        transcription.retry_count = 0
        transcription.processing_started_at = None
        db.commit()
        return  # start on a later turn

    # --- Phase 2: start the job (once) ---
    if transcription.status == TranscriptionStatus.submitting.value:
        try:
            provider.start_job(transcription.provider_job_id)
        except ProviderError as exc:
            if exc.retryable:
                _schedule_transient(db, transcription, exc.retry_after)
            else:
                _mark_failed(db, transcription, exc.code, exc.message or "Provider could not start the job.")
            return
        except Exception:
            logger.exception("transcription %s start crashed", transcription.id)
            _schedule_transient(db, transcription, None)
            return
        transcription.status = TranscriptionStatus.processing.value
        # Enforce the 10 s minimum before the FIRST poll.
        transcription.next_retry_at = _now() + timedelta(seconds=settings.gnani_poll_interval_seconds)
        transcription.processing_started_at = None
        db.commit()
        return

    # --- Phase 3: poll (status == processing) ---
    transcription.poll_count += 1
    transcription.processing_started_at = None
    try:
        status = provider.get_status(transcription.provider_job_id)
    except ProviderError as exc:
        transcription.provider_status = None
        transcription.provider_status_at = _now()
        db.commit()
        if exc.retryable:
            _schedule_transient(db, transcription, exc.retry_after)
        else:
            _mark_failed(db, transcription, exc.code, exc.message or "Provider poll failed.")
        return
    except Exception:
        logger.exception("transcription %s poll crashed", transcription.id)
        transcription.provider_status = "POLL_ERROR"
        transcription.provider_status_at = _now()
        db.commit()
        _schedule_transient(db, transcription, None)
        return

    transcription.provider_status = status
    transcription.provider_status_at = _now()
    db.commit()
    logger.info("transcription %s provider status=%s poll=%s", transcription.id, status, transcription.poll_count)

    if transcription.poll_count >= settings.gnani_max_polls or _timed_out(transcription):
        _mark_failed(
            db, transcription, "PROCESSING_TIMEOUT", "Transcription timed out after the maximum number of polls."
        )
        return

    if status in PROVIDER_ACTIVE or status not in PROVIDER_TERMINAL:
        transcription.next_retry_at = _now() + timedelta(seconds=settings.gnani_poll_interval_seconds)
        db.commit()
        return

    if status == "COMPLETED":
        try:
            result = provider.retrieve_transcript(transcription.provider_job_id)
        except ProviderError as exc:
            if exc.retryable:
                if transcription.poll_count >= settings.gnani_max_polls or _timed_out(transcription):
                    _mark_failed(
                        db, transcription, "PROCESSING_TIMEOUT", "Transcription timed out while retrieving its transcript."
                    )
                else:
                    _schedule_transient(db, transcription, exc.retry_after)
            else:
                _mark_failed(db, transcription, exc.code, exc.message or "Provider returned no transcript.")
            return
        except Exception:
            logger.exception("transcription %s retrieve crashed", transcription.id)
            if transcription.poll_count >= settings.gnani_max_polls or _timed_out(transcription):
                _mark_failed(
                    db, transcription, "PROCESSING_TIMEOUT", "Transcription timed out while retrieving its transcript."
                )
            else:
                _schedule_transient(db, transcription, None)
            return
        transcription.transcript_text = result.transcript_text
        transcription.detected_language = result.detected_language
        transcription.processing_time_ms = result.processing_time_ms
        transcription.status = TranscriptionStatus.completed.value
        transcription.completed_at = _now()
        transcription.error_code = None
        transcription.error_message = None
        transcription.processing_started_at = None
        transcription.retry_count = 0
        transcription.next_retry_at = None
        db.commit()
        _delete_audio_after_success(db, audio)
        consultation = db.get(Consultation, transcription.consultation_id)
        if consultation is not None:
            consultation.status = ConsultationStatus.completed.value
            consultation.ended_at = _now()
            db.commit()
        return

    # Terminal non-completed (FAILED / PARTIAL_FAILURE / START_FAILED / CANCELLED)
    _mark_failed(
        db, transcription, "TRANSCRIPTION_FAILED", "The provider could not transcribe the audio."
    )


def _delete_audio_after_success(db: Session, audio: AudioAttachment) -> None:
    """Delete audio only after the transcript is committed; never lose the transcript."""
    try:
        storage = DatabaseAudioStorage(db)
        storage.delete(audio.storage_key)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("audio deletion failed for consultation %s; transcript already saved", audio.consultation_id)


def process_pending() -> int:
    processed = 0
    try:
        with SessionLocal() as db:
            while True:
                transcription = _claim_next(db)
                if transcription is None:
                    break
                _run_turn(db, transcription)
                processed += 1
    except ProgrammingError as exc:
        with SessionLocal() as db:
            db.rollback()
        if "does not exist" in str(exc):
            return 0
        raise
    return processed


async def transcription_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(process_pending)
        except Exception:
            logger.exception("transcription worker error")
        await asyncio.sleep(settings.gnani_worker_interval_seconds)
