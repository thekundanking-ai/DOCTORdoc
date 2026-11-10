import json
import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.stt.base import ProviderError, SpeechToTextProvider, TranscriptResult

logger = logging.getLogger(__name__)

_AUDIO_EXTENSIONS = {
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

_WORK_DIR = Path(tempfile.gettempdir()) / "kilo" / "whisper_jobs"

_model_instances = {}


def _load_model(size, device, compute_type, download_root=None):
    key = (size, device, compute_type)
    if key not in _model_instances:
        from faster_whisper import WhisperModel

        kwargs = {"device": device, "compute_type": compute_type}
        if download_root:
            kwargs["download_root"] = download_root
        _model_instances[key] = WhisperModel(size, **kwargs)
    return _model_instances[key]


def _map_language(code):
    """Map a user-facing language code to a faster-whisper language param.

    None/''/'auto'/'indic-auto' -> None (whisper auto-detects). Region
    suffixes are stripped (hi-IN -> hi).
    """
    if not code:
        return None
    code = str(code).strip().lower()
    if code in ("auto", "indic-auto"):
        return None
    return code.split("-")[0].split("_")[0]


class WhisperProvider(SpeechToTextProvider):
    """Local, free STT via faster-whisper (CPU/GPU). Not billable.

    Runs synchronously; the worker drives the usual create -> start -> poll ->
    retrieve phases. Inference happens once at create time; the result is cached
    on disk (and deleted after the transcript is persisted).
    """

    def __init__(self, model_size=None, device=None, compute_type=None, language_code=None):
        self._model_size = model_size or settings.whisper_model
        self._device = device or settings.whisper_device
        self._compute_type = compute_type or settings.whisper_compute_type
        self._download_root = settings.whisper_download_root or None
        self._language = _map_language(
            language_code if language_code is not None else settings.gnani_language_code
        )
        self.provider_model = f"faster-whisper-{self._model_size}"
        self.language_code = settings.gnani_language_code or "indic-auto"
        self.format = "transcribe"

    def create_job(self, audio_bytes, mime_type):
        ext = _AUDIO_EXTENSIONS.get(mime_type) or ".wav"
        job_id = f"whisper-{uuid.uuid4().hex}"
        work_dir = _WORK_DIR / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        audio_path = work_dir / f"audio{ext}"
        audio_path.write_bytes(audio_bytes)
        try:
            text, detected_lang = self._transcribe(audio_path)
        except Exception:
            logger.exception("whisper inference failed for %s", job_id)
            raise ProviderError(
                "PROVIDER_INFERENCE_FAILED", "Local transcription inference failed.", retryable=True
            )
        result = {"text": text, "language": detected_lang, "model": self.provider_model}
        (work_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return job_id

    def start_job(self, job_id):
        return None

    def get_status(self, job_id):
        return "COMPLETED" if (_WORK_DIR / job_id / "result.json").exists() else "IN_PROGRESS"

    def retrieve_transcript(self, job_id):
        result_path = _WORK_DIR / job_id / "result.json"
        if not result_path.exists():
            raise ProviderError("NO_TRANSCRIPT", "Local transcript result is missing.", retryable=True)
        data = json.loads(result_path.read_text(encoding="utf-8"))
        text = (data.get("text") or "").strip()
        if not text:
            raise ProviderError("EMPTY_TRANSCRIPT", "Local transcription produced no text.", retryable=False)
        shutil.rmtree(_WORK_DIR / job_id, ignore_errors=True)
        return TranscriptResult(
            transcript_text=text,
            detected_language=data.get("language"),
            model=self.provider_model,
            processing_time_ms=None,
            raw=data,
        )

    def _transcribe(self, path):
        model = _load_model(
            self._model_size, self._device, self._compute_type, self._download_root
        )
        segments, info = model.transcribe(str(path), language=self._language)
        text = "".join(segment.text for segment in segments).strip()
        return text, (info.language if info.language else None)
