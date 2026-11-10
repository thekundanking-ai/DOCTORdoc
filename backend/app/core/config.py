import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field

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
    # Upper bound (seconds) for the poll interval once a job has been stuck in
    # a non-terminal provider status across many consecutive polls. Bounded
    # escalation keeps multiple concurrent jobs from hammering Gnani (the docs
    # warn tight polling provokes 429 errors) while staying >= poll_interval and
    # within the provider's recommended cadence. This is NOT a deadline; the job
    # deadline/retry logic is unchanged.
    gnani_poll_max_interval_seconds: int = 30
    gnani_direct_upload_max_bytes: int = 10 * 1024 * 1024
    gnani_worker_interval_seconds: int = 10
    gnani_max_retries: int = 3
    # Overall deadline for a single transcription job (seconds since first
    # successful submission). After this the job is terminated as timed out.
    gnani_job_deadline_seconds: int = 3600
    # Ceiling on distinct provider poll attempts before a job is timed out.
    # This bounds the `processing` loop independently of failed-job retries.
    gnani_max_polls: int = 500

    # STT provider selection: "auto" | "gnani" | "whisper" | "mock".
    # In auto mode the first configured provider wins: Gnani (if key set), then
    # mock (if allowed), then local whisper. Setting STT_PROVIDER=whisper is the
    # explicit way to route to the local provider (e.g. when Gnani is unreliable).
    stt_provider: str = "auto"
    # Local faster-whisper settings (free, CPU inference by default).
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_download_root: str | None = None

    mercury_api_key: str | None = None
    mercury_base_url: str = "https://api.inceptionlabs.ai"
    mercury_model: str = "mercury-3"
    mercury_timeout_seconds: float = 60.0

    delivery_provider: str = "mock"
    # Explicitly permit mock providers in a non-debug environment (dev/tests).
    # When DEBUG=true, mocks are always allowed. In production, this flag is
    # the only way to opt into mocks without setting a real provider key.
    allow_mock_providers: bool = False

    smtp_host: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_HOST", "smtp_host"))
    smtp_port: int = Field(default=587, validation_alias=AliasChoices("SMTP_PORT", "smtp_port"))
    smtp_username: str | None = Field(
        default=None, validation_alias=AliasChoices("SMTP_USERNAME", "SMTP_USER", "smtp_username")
    )
    smtp_password: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_PASSWORD", "smtp_password"))
    smtp_from_email: str | None = Field(
        default=None, validation_alias=AliasChoices("SMTP_FROM_EMAIL", "SMTP_FROM", "smtp_from_email")
    )
    smtp_from_name: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_FROM_NAME", "smtp_from_name"))
    smtp_use_tls: bool = Field(
        default=True, validation_alias=AliasChoices("SMTP_USE_TLS", "SMTP_STARTTLS", "smtp_use_tls")
    )

    # In-process rate limiting (keyed by client IP) for auth endpoints.
    rate_limit_login: int = 30
    rate_limit_register: int = 10
    rate_limit_window_seconds: int = 60

    _secret = None

    def mock_providers_allowed(self) -> bool:
        return bool(self.debug or self.allow_mock_providers)

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


