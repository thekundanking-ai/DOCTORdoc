from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class DeliveryResult:
    status: str  # "sent" | "failed"
    message: str | None = None


class DeliveryProviderError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class DeliveryProvider(ABC):
    @abstractmethod
    def send(
        self,
        recipient: str,
        subject: str,
        payload_bytes: bytes,
        payload_type: str,
        meta: dict,
    ) -> DeliveryResult:
        raise NotImplementedError