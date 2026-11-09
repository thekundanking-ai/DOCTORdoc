"""add report_delivery table

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "report_delivery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("consultation_report.id"), nullable=False),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinic.id"), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="sms"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.String(length=500)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_report_delivery_report_id", "report_delivery", ["report_id"])
    op.create_index("ix_report_delivery_clinic_id", "report_delivery", ["clinic_id"])


def downgrade():
    op.drop_index("ix_report_delivery_clinic_id", table_name="report_delivery")
    op.drop_index("ix_report_delivery_report_id", table_name="report_delivery")
    op.drop_table("report_delivery")
