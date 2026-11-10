from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(str, Enum):
    clinic_owner = "clinic_owner"
    admin = "admin"
    clinician = "clinician"
    staff = "staff"


class Clinic(Base):
    __tablename__ = "clinic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Verified clinic-owner Gmail used as the per-clinic SMTP sender.
    sender_email: Mapped[str | None] = mapped_column(String(255))

    users: Mapped[list["User"]] = relationship(back_populates="clinic")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default=Role.staff.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    verification_token_hash: Mapped[str | None] = mapped_column(String(128))
    verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinic.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    clinic: Mapped["Clinic"] = relationship(back_populates="users")


class Patient(Base):
    __tablename__ = "patient"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinic.id"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mobile: Mapped[str] = mapped_column(String(50), nullable=False)
    mobile_normalized: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ConsultationStatus(str, Enum):
    open_ = "open"
    awaiting_transcription = "awaiting_transcription"
    completed = "completed"
    cancelled = "cancelled"


class Consultation(Base):
    __tablename__ = "consultation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinic.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"), nullable=False, index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ConsultationStatus.open_.value)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AudioAttachment(Base):
    __tablename__ = "audio_attachment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consultation_id: Mapped[int] = mapped_column(ForeignKey("consultation.id"), nullable=False, unique=True)
    upload_id: Mapped[object] = mapped_column(Uuid, nullable=False, unique=True)
    storage_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    sha256: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TranscriptionStatus(str, Enum):
    not_started = "not_started"
    submitting = "submitting"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Transcription(Base):
    __tablename__ = "transcription"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consultation_id: Mapped[int] = mapped_column(ForeignKey("consultation.id"), nullable=False, unique=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinic.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_model: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_job_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=TranscriptionStatus.not_started.value)
    language_code: Mapped[str] = mapped_column(String(50), nullable=False, default="indic-auto")
    format: Mapped[str] = mapped_column(String(50), nullable=False, default="transcribe")
    transcript_text: Mapped[str | None] = mapped_column(Text)
    detected_language: Mapped[str | None] = mapped_column(String(50))
    processing_time_ms: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(String(500))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Latest raw provider status (e.g. QUEUED/IN_PROGRESS/COMPLETED/FAILED).
    provider_status: Mapped[str | None] = mapped_column(String(50))
    provider_status_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Dedicated counter for provider poll attempts (separate from failed-job retries).
    poll_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Persistent overall deadline, set once on first successful submission, never reset.
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReportStatus(str, Enum):
    generating = "generating"
    draft = "draft"
    generated = "generated"
    failed = "failed"
    approved = "approved"


class ConsultationReport(Base):
    __tablename__ = "consultation_report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consultation_id: Mapped[int] = mapped_column(ForeignKey("consultation.id"), nullable=False, unique=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinic.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"), nullable=False)
    transcript_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    structured_report: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ReportStatus.generating.value)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class DeliveryStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class ReportDelivery(Base):
    __tablename__ = "report_delivery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("consultation_report.id"), nullable=False, index=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinic.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="sms")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DeliveryStatus.pending.value)
    error_message: Mapped[str | None] = mapped_column(String(500))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
