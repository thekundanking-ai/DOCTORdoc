from app.core.delivery.base import DeliveryProvider
from app.core.delivery.mock import MockDeliveryProvider
from app.core.delivery.smtp import SmtpDeliveryProvider
from app.core.config import settings


def get_delivery_provider() -> DeliveryProvider:
    # Real SMTP is used ONLY when explicitly configured. Otherwise mock (dev/tests).
    if settings.smtp_host and settings.smtp_user and settings.smtp_password:
        return SmtpDeliveryProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            sender=settings.smtp_from or settings.smtp_user,
            starttls=settings.smtp_starttls,
        )
    return MockDeliveryProvider()
