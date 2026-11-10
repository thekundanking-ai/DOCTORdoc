"""add email verification columns and clinic sender_email

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-09

"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("verification_token_hash", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("verification_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("clinic", sa.Column("sender_email", sa.String(length=255), nullable=True))
    # Preserve pre-existing accounts (e.g. the bootstrap owner) as verified so
    # existing logins keep working after this migration.
    op.execute("UPDATE users SET email_verified = TRUE")


def downgrade():
    op.drop_column("clinic", "sender_email")
    op.drop_column("users", "verification_expires_at")
    op.drop_column("users", "verification_token_hash")
    op.drop_column("users", "email_verified")
