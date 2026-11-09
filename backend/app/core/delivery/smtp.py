import smtplib
from email.message import EmailMessage

from app.core.delivery.base import DeliveryProvider, DeliveryResult


class SmtpDeliveryProvider(DeliveryProvider):
    """Simple SMTP email delivery (TLS). External credentials come from env only.

    NOTE: sends real email. Must never be called without explicit authorization.
    """

    def __init__(self, host: str, port: int, user: str, password: str, sender: str, starttls: bool = True):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender
        self.starttls = starttls

    def send(self, recipient, subject, payload_bytes, payload_type, meta) -> DeliveryResult:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = self.sender
            msg["To"] = recipient
            msg.set_content("Your DoctorDoc consultation report is attached.")
            msg.add_attachment(payload_bytes, maintype="application", subtype="pdf", filename=f"report-{meta.get('consultation_id')}.pdf")

            with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
                if self.starttls:
                    smtp.starttls()
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)
            return DeliveryResult("sent", None)
        except Exception as exc:
            return DeliveryResult("failed", f"SMTP error: {type(exc).__name__}")
