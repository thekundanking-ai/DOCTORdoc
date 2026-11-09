from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError

from app.db import SessionLocal
from app.models import AudioAttachment


def purge_expired_audio(db) -> int:
    now = datetime.now(timezone.utc)
    try:
        rows = db.scalars(select(AudioAttachment).where(AudioAttachment.expires_at < now)).all()
    except ProgrammingError as exc:
        db.rollback()
        if "does not exist" in str(exc):
            return 0
        raise
    for row in rows:
        db.delete(row)
    db.commit()
    return len(rows)


def run_purge() -> int:
    with SessionLocal() as db:
        return purge_expired_audio(db)
