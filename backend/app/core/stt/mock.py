import uuid

from app.core.stt.base import ProviderError, SpeechToTextProvider, TranscriptResult


class MockSpeechToTextProvider(SpeechToTextProvider):
    """Deterministic, stateless mock for tests/dev (mirrors the remote API
    which owns job state server-side). Non-billable."""

    def __init__(self, outcome: str = "completed"):
        self.outcome = outcome

    def create_job(self, audio_bytes: bytes, mime_type: str) -> str:
        return f"mock-job-{uuid.uuid4().hex}"

    def start_job(self, job_id: str) -> None:
        return None

    def get_status(self, job_id: str) -> str:
        return {
            "completed": "COMPLETED",
            "failed": "FAILED",
            "partial": "PARTIAL_FAILURE",
            "processing": "IN_PROGRESS",
        }.get(self.outcome, "COMPLETED")

    def retrieve_transcript(self, job_id: str) -> TranscriptResult:
        if self.outcome == "failed":
            raise ProviderError("TRANSCRIPTION_FAILED", "Transcription failed at the provider", retryable=True)
        if self.outcome == "partial":
            return TranscriptResult(
                transcript_text="partial transcript text",
                detected_language="hi-IN",
                model="prisma-v3.0",
                processing_time_ms=1200,
            )
        return TranscriptResult(
            transcript_text="this is a mock transcript for testing",
            detected_language="en-IN",
            model="prisma-v3.0",
            processing_time_ms=900,
        )
