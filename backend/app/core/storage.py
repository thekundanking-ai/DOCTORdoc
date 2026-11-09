from abc import ABC, abstractmethod

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioAttachment


class AudioStorage(ABC):
    @abstractmethod
    def open(self, storage_key: str) -> bytes | None:
        ...

    @abstractmethod
    def delete(self, storage_key: str) -> bool:
        ...


class DatabaseAudioStorage(AudioStorage):
    """Audio blobs are stored in PostgreSQL (bytea) via AudioAttachment.data."""

    def __init__(self, db: Session):
        self.db = db

    def open(self, storage_key: str) -> bytes | None:
        row = self.db.scalar(select(AudioAttachment).where(AudioAttachment.storage_key == storage_key))
        return row.data if row is not None else None

    def delete(self, storage_key: str) -> bool:
        row = self.db.scalar(select(AudioAttachment).where(AudioAttachment.storage_key == storage_key))
        if row is None:
            return False
        self.db.delete(row)
        return True


def get_audio_storage(db: Session = Depends(get_db)) -> DatabaseAudioStorage:
    return DatabaseAudioStorage(db)
