from app.core.config import settings
from app.core.stt.base import ProviderError, SpeechToTextProvider
from app.core.stt.gnani import GnaniPrismaV3Provider
from app.core.stt.mock import MockSpeechToTextProvider
from app.core.stt.whisper import WhisperProvider


def get_provider() -> SpeechToTextProvider:
    mode = settings.stt_provider.strip().lower()
    if mode == "whisper":
        return WhisperProvider()
    if mode == "gnani":
        if not settings.gnani_api_key:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED", "GNANI_API_KEY is not configured.", retryable=False
            )
        return GnaniPrismaV3Provider()
    if mode == "mock":
        return MockSpeechToTextProvider()
    # auto: first configured provider wins
    if settings.gnani_api_key:
        return GnaniPrismaV3Provider()
    if settings.mock_providers_allowed():
        return MockSpeechToTextProvider()
    return WhisperProvider()
