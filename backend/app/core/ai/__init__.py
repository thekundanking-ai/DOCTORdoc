from app.core.ai.base import ReportProvider
from app.core.ai.mercury_provider import MercuryReportProvider
from app.core.ai.mock import MockReportProvider
from app.core.config import settings


def get_report_provider() -> ReportProvider:
    if settings.mercury_api_key:
        return MercuryReportProvider()
    return MockReportProvider()
