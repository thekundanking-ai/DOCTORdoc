import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DoctorDoc"
    debug: bool = False
    database_url: str = "postgresql+psycopg2://doctordoc:doctordoc@localhost:5432/doctordoc"
    frontend_origin: str = "http://localhost:5173"

    secret_key: str | None = None
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cookie_secure: bool = False
    cookie_name: str = "access_token"

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
