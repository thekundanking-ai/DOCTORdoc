from abc import ABC, abstractmethod
from dataclasses import dataclass, field

TERMINAL_STATUSES = {"COMPLETED", "PARTIAL_FAILURE", "FAILED", "START_FAILED", "CANCELLED"}


@dataclass
class TranscriptResult:
    transcript_text: str
    detected_language: str | None = None
    model: str | None = None
    processing_time_ms: int | None = None
    raw: dict = field(default_factory=dict)


class ProviderError(Exception):
    """Base for provider failures with a safe user-facing code."""

    def __init__(self, code: str, message: str, retryable: bool = False, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after = retry_after


class SpeechToTextProvider(ABC):
    def create_job(self, audio_bytes: bytes, mime_type: str) -> str:
        """Upload audio and return a provider job id (does NOT start)."""
        raise NotImplementedError

    def start_job(self, job_id: str) -> None:
        raise NotImplementedError

    def get_status(self, job_id: str) -> str:
        """Return provider job status: CREATED/STARTING/QUEUED/IN_PROGRESS/terminal."""
        raise NotImplementedError

    def retrieve_transcript(self, job_id: str) -> TranscriptResult:
        """Download the completed transcript document."""
        raise NotImplementedError
