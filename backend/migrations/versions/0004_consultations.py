"""add consultation and audio_attachment tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "consultation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinic.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patient.id"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="open"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_consultation_clinic_id", "consultation", ["clinic_id"])
    op.create_index("ix_consultation_patient_id", "consultation", ["patient_id"])

    op.create_table(
        "audio_attachment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultation.id"), nullable=False, unique=True),
        sa.Column("upload_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("storage_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("sha256", sa.String(length=64)),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("audio_attachment")
    op.drop_index("ix_consultation_patient_id", table_name="consultation")
    op.drop_index("ix_consultation_clinic_id", table_name="consultation")
    op.drop_table("consultation")
