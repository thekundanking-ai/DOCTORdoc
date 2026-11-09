from app.core.delivery.base import DeliveryProvider, DeliveryResult


class MockDeliveryProvider(DeliveryProvider):
    """Records nothing external; simulates a successful send for tests/dev."""

    out_fail = False

    def send(self, recipient, subject, payload_bytes, payload_type, meta) -> DeliveryResult:
        if self.out_fail:
            return DeliveryResult("failed", "Mock delivery failure")
        return DeliveryResult("sent", "Mock delivery recorded (no external message sent)")
