"""add gnani bounded polling fields to transcription

Adds provider-status persistence, a dedicated poll counter, and a persistent
overall deadline for the Gnani transcription job. Existing rows are preserved;
only additive columns are introduced.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-07

"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transcription", sa.Column("provider_status", sa.String(length=50), nullable=True))
    op.add_column("transcription", sa.Column("provider_status_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "transcription",
        sa.Column("poll_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("transcription", sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("transcription", "deadline_at")
    op.drop_column("transcription", "poll_count")
    op.drop_column("transcription", "provider_status_at")
    op.drop_column("transcription", "provider_status")
