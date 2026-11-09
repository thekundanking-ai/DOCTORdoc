import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DoctorDoc"
    debug: bool = False
    database_url: str = "postgresql+psycopg2://doctordoc:doctordoc@localhost:5432/doctordoc"
    frontend_origin: str = "http://localhost:5173"

    secret_key: str | None = None
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cookie_secure: bool = False
    cookie_name: str = "access_token"

    max_audio_bytes: int = 50 * 1024 * 1024
    audio_max_duration_seconds: int = 3600
    audio_retention_days: int = 7
    audio_cleanup_interval_seconds: int = 3600

    gnani_api_key: str | None = None
    gnani_api_base_url: str = "https://api.vachana.ai"
    gnani_stt_model: str = "prisma-v3.0"
    gnani_language_code: str = "indic-auto"
    gnani_stt_format: str = "transcribe"
    # Authoritative minimum interval between provider status polls (seconds).
    # Used by the transcription worker; the old hardcoded constant was removed.
    gnani_poll_interval_seconds: int = 10
    gnani_direct_upload_max_bytes: int = 10 * 1024 * 1024
    gnani_worker_interval_seconds: int = 10
    gnani_max_retries: int = 3
    # Overall deadline for a single transcription job (seconds since first
    # successful submission). After this the job is terminated as timed out.
    gnani_job_deadline_seconds: int = 3600
    # Ceiling on distinct provider poll attempts before a job is timed out.
    # This bounds the `processing` loop independently of failed-job retries.
    gnani_max_polls: int = 500

    mercury_api_key: str | None = None
    mercury_base_url: str = "https://api.inceptionlabs.ai"
    mercury_model: str = "mercury-3"
    mercury_timeout_seconds: float = 60.0

    delivery_provider: str = "mock"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True

    _secret = None

    def resolve_secret_key(self) -> str:
        if self._secret:
            return self._secret
        if self.secret_key:
            self._secret = self.secret_key
        elif self.debug:
            self._secret = secrets.token_urlsafe(32)
        else:
            raise RuntimeError("SECRET_KEY environment variable is required when DEBUG=false")
        return self._secret


settings = Settings()
