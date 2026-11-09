"""add consultation_report table

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "consultation_report",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultation_id", sa.Integer(), sa.ForeignKey("consultation.id"), nullable=False, unique=True),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinic.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patient.id"), nullable=False),
        sa.Column("transcript_snapshot", sa.Text(), nullable=False),
        sa.Column("structured_report", JSONB()),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="generating"),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=50), nullable=False),
        sa.Column("error_code", sa.String(length=100)),
        sa.Column("error_message", sa.String(length=500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
    )
    op.create_index("ix_consultation_report_clinic_id", "consultation_report", ["clinic_id"])


def downgrade():
    op.drop_index("ix_consultation_report_clinic_id", table_name="consultation_report")
    op.drop_table("consultation_report")
