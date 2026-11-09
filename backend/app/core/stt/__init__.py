from app.core.config import settings
from app.core.stt.base import ProviderError, SpeechToTextProvider
from app.core.stt.gnani import GnaniPrismaV3Provider
from app.core.stt.mock import MockSpeechToTextProvider


def get_provider() -> SpeechToTextProvider:
    if settings.gnani_api_key:
        return GnaniPrismaV3Provider()
    if settings.mock_providers_allowed():
        return MockSpeechToTextProvider()
    raise ProviderError(
        "PROVIDER_NOT_CONFIGURED",
        "GNANI_API_KEY is not configured and mock providers are disabled.",
    )