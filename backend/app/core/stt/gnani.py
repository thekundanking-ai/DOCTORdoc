import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import httpx

from app.core.config import settings
from app.core.stt.base import ProviderError, SpeechToTextProvider, TranscriptResult

logger = logging.getLogger(__name__)

SUCCESS_CREATE = {"CREATED"}
SUCCESS_START = {"STARTING"}

# Gnani validates the multipart audio part by its FILENAME extension.
AUDIO_EXTENSIONS = {
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/flac": ".flac",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/webm": ".webm",
    "audio/aac": ".aac",
    "audio/amr": ".amr",
}


class GnaniPrismaV3Provider(SpeechToTextProvider):
    """Gnani Prisma v3.0 Batch STT API.

    Verified against https://docs.gnani.ai/api/STTBatch/Introduction:
      1. POST /stt/v3/batch/jobs (multipart, config + files) -> 201, CREATED, job_id
      2. POST /stt/v3/batch/jobs/{job_id}/start -> 202, STARTING
      3. GET  /stt/v3/batch/jobs/{job_id} until terminal status
      4. GET  /stt/v3/batch/jobs/{job_id}/files?status=COMPLETED -> transcript_url
      5. GET  transcript_url -> transcript JSON with full_transcript
    full_transcript is only present in the downloaded transcript document, not in
    status/file responses.
    """

    def __init__(self):
        if not settings.gnani_api_key:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED", "Transcription provider is not configured.", retryable=False
            )
        self._base = settings.gnani_api_base_url.rstrip("/")
        self._headers = {"X-API-Key-ID": settings.gnani_api_key}
        self._model = settings.gnani_stt_model
        self._language_code = settings.gnani_language_code
        self._format = settings.gnani_stt_format

    def _config(self) -> str:
        import json

        return json.dumps(
            {
                "model": self._model,
                "language_code": self._language_code,
                "format": self._format,
                "mode": "transcribe",
            }
        )

    def _post(self, path: str, **kwargs) -> httpx.Response:
        try:
            resp = httpx.post(urljoin(self._base, path), headers=self._headers, timeout=60.0, **kwargs)
        except httpx.TimeoutException:
            raise ProviderError("PROVIDER_TIMEOUT", "The transcription provider timed out.", retryable=True)
        except httpx.HTTPError as exc:
            raise ProviderError("PROVIDER_UNAVAILABLE", "The transcription provider is unavailable.", retryable=True)
        return self._check(resp)

    def _get(self, path: str, **kwargs) -> httpx.Response:
        try:
            resp = httpx.get(urljoin(self._base, path), headers=self._headers, timeout=60.0, **kwargs)
        except httpx.TimeoutException:
            raise ProviderError("PROVIDER_TIMEOUT", "The transcription provider timed out.", retryable=True)
        except httpx.HTTPError:
            raise ProviderError("PROVIDER_UNAVAILABLE", "The transcription provider is unavailable.", retryable=True)
        return self._check(resp)

    TRANSIENT_STATUSES = {429, 502, 503, 504}

    def _check(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code < 400:
            return resp

        code, message = self._error_info(resp)

        if resp.status_code in self.TRANSIENT_STATUSES:
            retry_after = self._parse_retry_after(resp.headers.get("retry-after"))
            raise ProviderError(
                code, message or "The transcription provider is temporarily unavailable.",
                retryable=True, retry_after=retry_after,
            )

        # Any other 4xx is permanent (auth, scope, invalid config, not found, …).
        raise ProviderError(code, message or "The transcription provider rejected the request.", retryable=False)

    @staticmethod
    def _parse_retry_after(raw: str | None) -> int | None:
        """Parse `Retry-After` as numeric seconds or RFC 7231 HTTP-date.

        Returns seconds (>= 0) or None to fall back to exponential backoff.
        """
        if not raw or not raw.strip():
            return None
        value = raw.strip()
        if value.isdigit():
            return int(value)
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0, int((when - datetime.now(timezone.utc)).total_seconds()))

    def _error_info(self, resp: httpx.Response) -> tuple[str, str | None]:
        """Return (sanitized error code, sanitized message). Never includes the API key."""
        try:
            body = resp.json()
        except Exception:
            return str(resp.status_code), None

        code = body.get("error")
        if isinstance(code, dict):
            code = code.get("type")
        if code is None:
            code = body.get("error_code") or body.get("code") or resp.status_code

        message = body.get("message")
        if not message and isinstance(body.get("detail"), dict):
            message = body["detail"].get("message")

        return str(code), str(message) if message else None

    def create_job(self, audio_bytes: bytes, mime_type: str) -> str:
        if len(audio_bytes) > settings.gnani_direct_upload_max_bytes:
            raise ProviderError(
                "AUDIO_TOO_LARGE",
                "This recording exceeds the provider's 10 MB direct-upload limit.",
                retryable=False,
            )

        extension = AUDIO_EXTENSIONS.get(mime_type)
        if extension is None:
            raise ProviderError(
                "UNSUPPORTED_AUDIO_FORMAT",
                "This audio format is not supported by the transcription provider.",
                retryable=False,
            )

        resp = self._post(
            "/stt/v3/batch/jobs",
            files={
                "config": (None, self._config(), "application/json"),
                "files": (f"recording{extension}", audio_bytes, mime_type),
            },
        )
        body = resp.json()
        if body.get("status") not in SUCCESS_CREATE or not body.get("job_id"):
            raise ProviderError("CREATE_FAILED", "The provider did not create a transcription job.", retryable=True)
        return body["job_id"]

    def start_job(self, job_id: str) -> None:
        resp = self._post(f"/stt/v3/batch/jobs/{job_id}/start")
        body = resp.json()
        if body.get("status") not in SUCCESS_START:
            raise ProviderError("START_FAILED", "The provider could not start the job.", retryable=True)

    def get_status(self, job_id: str) -> str:
        resp = self._get(f"/stt/v3/batch/jobs/{job_id}")
        try:
            body = resp.json()
        except Exception:
            raise ProviderError("INVALID_RESPONSE", "The provider returned an unreadable status.", retryable=True)
        status = body.get("status") if isinstance(body, dict) else None
        if not isinstance(status, str) or not status.strip():
            raise ProviderError("UNKNOWN_STATUS", "Unknown provider job status.", retryable=True)
        return status

    def retrieve_transcript(self, job_id: str) -> TranscriptResult:
        files_resp = self._get(f"/stt/v3/batch/jobs/{job_id}/files", params={"status": "COMPLETED"})
        records = self._extract_file_records(files_resp)
        if not records:
            raise ProviderError("NO_TRANSCRIPT", "The provider returned no completed transcript files.", retryable=True)

        transcript_url = records[0].get("transcript_url")
        if not transcript_url:
            raise ProviderError("NO_TRANSCRIPT_URL", "The provider transcript file has no URL.", retryable=True)

        # H2: The transcript URL is downloaded WITHOUT auth headers. Whether
        # Gnani requires the API key for this download is unresolved (insufficient
        # documentation). Left unchanged to avoid breaking a signed-URL flow.
        try:
            doc_resp = httpx.get(transcript_url, timeout=60.0)
        except httpx.HTTPError:
            raise ProviderError("TRANSCRIPT_DOWNLOAD_FAILED", "Downloading the transcript failed.", retryable=True)
        if doc_resp.status_code >= 400:
            raise ProviderError("TRANSCRIPT_DOWNLOAD_FAILED", "Could not download the transcript.", retryable=True)

        try:
            doc = doc_resp.json()
        except Exception:
            raise ProviderError("EMPTY_TRANSCRIPT", "The provider returned a malformed transcript document.", retryable=True)
        if not isinstance(doc, dict):
            raise ProviderError("EMPTY_TRANSCRIPT", "The provider returned an unreadable transcript document.", retryable=True)

        text = doc.get("full_transcript")
        if text is None:
            raise ProviderError("EMPTY_TRANSCRIPT", "The provider returned an empty transcript.", retryable=True)

        return TranscriptResult(
            transcript_text=str(text),
            detected_language=doc.get("language_code"),
            model=doc.get("model"),
            processing_time_ms=None,
            raw=doc,
        )

    @staticmethod
    def _extract_file_records(resp: httpx.Response) -> list:
        """Return the completed-file records from the provider /files response.

        Only documented structures are parsed: a bare JSON array, or an object
        whose "files" key holds the array. Anything else is treated as empty/
        malformed (=> an empty record list). Response contents are never logged.
        """
        try:
            body = resp.json()
        except Exception:
            return []
        if isinstance(body, list):
            records = body
        elif isinstance(body, dict):
            records = body.get("files")
            if not isinstance(records, list):
                return []
        else:
            return []
        return [record for record in records if isinstance(record, dict)]
