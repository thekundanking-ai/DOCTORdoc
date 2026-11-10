"""add email column to patient

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-09

"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("patient", sa.Column("email", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("patient", "email")
