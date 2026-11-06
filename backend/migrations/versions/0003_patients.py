"""add patient table

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "patient",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinic.id"), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("mobile", sa.String(length=50), nullable=False),
        sa.Column("mobile_normalized", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_patient_clinic_id", "patient", ["clinic_id"])
    op.create_index("ix_patient_clinic_mobile", "patient", ["clinic_id", "mobile_normalized"])


def downgrade():
    op.drop_index("ix_patient_clinic_mobile", table_name="patient")
    op.drop_index("ix_patient_clinic_id", table_name="patient")
    op.drop_table("patient")
