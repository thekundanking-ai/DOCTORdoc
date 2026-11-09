from app.core.ai.base import ReportProvider, ReportProviderError, ReportResult


class MockReportProvider(ReportProvider):
    """Deterministic, non-billable mock for development and tests."""

    def __init__(self, outcome: str = "ok"):
        self.outcome = outcome

    def _base_report(self, transcript: str) -> dict:
        return {
            "patient_information": {"name": None, "mobile": None, "consultation_date": None},
            "chief_complaint": "Patient reports mild fever and sore throat since yesterday.",
            "symptoms": ["fever", "sore throat"],
            "medical_history": None,
            "clinical_observations": None,
            "diagnosis": "Upper respiratory tract infection (stated by doctor).",
            "medications": [
                {"name": "Paracetamol", "dosage": "500 mg", "frequency": "as needed", "duration": "3 days"}
            ],
            "investigations": None,
            "treatment_and_advice": "Hydration, rest, and gargles.",
            "follow_up": "Review in 3 days if symptoms persist.",
            "unclear_or_missing": [],
        }

    def generate_report(self, transcript: str, patient_meta: dict) -> ReportResult:
        if self.outcome == "empty":
            return ReportResult(structured={})
        if self.outcome == "invalid":
            raise ReportProviderError("INVALID_RESPONSE", "Provider returned invalid JSON.", retryable=True)
        if self.outcome == "timeout":
            raise ReportProviderError("PROVIDER_TIMEOUT", "Report provider timed out.", retryable=True)
        if self.outcome == "failure":
            raise ReportProviderError("PROVIDER_FAILURE", "Report provider failed.", retryable=True)
        if self.outcome == "hallucination":
            report = self._base_report(transcript)
            report["diagnosis"] = "Invented diagnosis not stated by doctor."
            return ReportResult(structured=report)
        return ReportResult(structured=self._base_report(transcript))
