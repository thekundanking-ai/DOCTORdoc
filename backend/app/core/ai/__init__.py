from app.core.ai.base import ReportProvider, ReportProviderError
from app.core.ai.mercury_provider import MercuryReportProvider
from app.core.ai.mock import MockReportProvider
from app.core.config import settings


def get_report_provider() -> ReportProvider:
    if settings.mercury_api_key:
        return MercuryReportProvider()
    if settings.mock_providers_allowed():
        return MockReportProvider()
    raise ReportProviderError(
        "PROVIDER_NOT_CONFIGURED",
        "MERCURY_API_KEY is not configured and mock providers are disabled.",
    )