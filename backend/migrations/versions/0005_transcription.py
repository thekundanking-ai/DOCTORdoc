"""add transcription table

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "transcription",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultation.id"), nullable=False, unique=True),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinic.id"), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_model", sa.String(length=50), nullable=False),
        sa.Column("provider_job_id", sa.String(length=64), unique=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="not_started"),
        sa.Column("language_code", sa.String(length=50), nullable=False, server_default="indic-auto"),
        sa.Column("format", sa.String(length=50), nullable=False, server_default="transcribe"),
        sa.Column("transcript_text", sa.Text()),
        sa.Column("detected_language", sa.String(length=50)),
        sa.Column("processing_time_ms", sa.BigInteger()),
        sa.Column("error_code", sa.String(length=100)),
        sa.Column("error_message", sa.String(length=500)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_transcription_clinic_id", "transcription", ["clinic_id"])


def downgrade():
    op.drop_index("ix_transcription_clinic_id", table_name="transcription")
    op.drop_table("transcription")
