from app.core.delivery.base import DeliveryProvider, DeliveryProviderError
from app.core.delivery.mock import MockDeliveryProvider
from app.core.delivery.smtp import SmtpDeliveryProvider
from app.core.config import settings


def get_delivery_provider(sender: str | None = None) -> DeliveryProvider:
    # Real SMTP is used ONLY when explicitly configured. Otherwise mock is used
    # only for dev/tests (DEBUG) or when explicitly opted in.
    if settings.smtp_host and settings.smtp_username and settings.smtp_password:
        return SmtpDeliveryProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_username,
            password=settings.smtp_password,
            sender=sender or settings.smtp_from_email or settings.smtp_username,
            sender_name=settings.smtp_from_name,
            starttls=settings.smtp_use_tls,
        )
    if settings.mock_providers_allowed():
        return MockDeliveryProvider()
    raise DeliveryProviderError(
        "PROVIDER_NOT_CONFIGURED",
        "No delivery provider is configured (SMTP env vars missing) and mock delivery is disabled.",
    )
