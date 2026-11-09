from app.core.config import settings
from app.core.stt.base import SpeechToTextProvider
from app.core.stt.gnani import GnaniPrismaV3Provider
from app.core.stt.mock import MockSpeechToTextProvider


def get_provider() -> SpeechToTextProvider:
    if settings.gnani_api_key:
        return GnaniPrismaV3Provider()
    return MockSpeechToTextProvider()
