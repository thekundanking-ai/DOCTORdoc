from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ReportResult:
    structured: dict
    raw: dict = field(default_factory=dict)


class ReportProviderError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class ReportProvider(ABC):
    @abstractmethod
    def generate_report(self, transcript: str, patient_meta: dict) -> ReportResult:
        """Return a validated structured report dict."""
        raise NotImplementedError
