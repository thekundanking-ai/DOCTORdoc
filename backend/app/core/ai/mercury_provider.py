import json
import logging
from urllib.parse import urljoin

import httpx

from app.core.ai.base import ReportProvider, ReportProviderError, ReportResult
from app.core.config import settings

logger = logging.getLogger(__name__)

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "patient_information": {
            "type": ["object", "null"],
            "properties": {
                "name": {"type": ["string", "null"]},
                "mobile": {"type": ["string", "null"]},
                "consultation_date": {"type": ["string", "null"]},
            },
            "additionalProperties": False,
        },
        "chief_complaint": {"type": ["string", "null"]},
        "symptoms": {"type": ["array", "null"], "items": {"type": "string"}},
        "medical_history": {"type": ["string", "null"]},
        "clinical_observations": {"type": ["array", "null"], "items": {"type": "string"}},
        "diagnosis": {"type": ["string", "null"]},
        "medications": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": ["string", "null"]},
                    "dosage": {"type": ["string", "null"]},
                    "frequency": {"type": ["string", "null"]},
                    "duration": {"type": ["string", "null"]},
                },
                "additionalProperties": False,
            },
        },
        "investigations": {"type": ["array", "null"], "items": {"type": "string"}},
        "treatment_and_advice": {"type": ["string", "null"]},
        "follow_up": {"type": ["string", "null"]},
        "unclear_or_missing": {"type": ["array", "null"], "items": {"type": "string"}},
    },
    "additionalProperties": False,
    "required": [],
}

SYSTEM_PROMPT = """You are a medical documentation assistant. You transform an audio transcription of a doctor's consultation into a structured report draft. You do not practice medicine.

Safety rules (mandatory):
1. Only include information that is explicitly present in the transcript.
2. Never invent symptoms, diagnosis, medications, dosages, frequency, duration, laboratory results, or examination findings.
3. Never infer allergies. Only note allergies if explicitly stated.
4. Do not convert uncertainty into a confirmed medical fact.
5. Diagnoses are only included if explicitly stated by the doctor. Otherwise set "diagnosis" to null.
6. Medications are only included if explicitly stated. Each medication field (name, dosage, frequency, duration) may be independently null when not stated. Never invent values.
7. If a section is missing, set it to null (or an empty list for list sections).
8. Flag incomplete, contradictory, or ambiguous details in "unclear_or_missing".
9. Preserve the doctor's wording; do not summarize, translate, or editorialize.
10. Output only the JSON object matching the provided schema."""


class MercuryReportProvider(ReportProvider):
    def __init__(self):
        if not settings.mercury_api_key:
            raise ReportProviderError("PROVIDER_NOT_CONFIGURED", "Report provider is not configured.")
        self._base = settings.mercury_base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {settings.mercury_api_key}"}
        self._model = settings.mercury_model
        self._timeout = settings.mercury_timeout_seconds

    def generate_report(self, transcript: str, patient_meta: dict) -> ReportResult:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Patient context: "
                        + json.dumps(patient_meta)
                        + "\n\nConsultation transcript:\n"
                        + transcript
                    ),
                },
            ],
            "reasoning_effort": "low",
            "max_completion_tokens": 4000,
            "temperature": 0.5,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "consultation_report", "schema": REPORT_SCHEMA, "strict": True},
            },
        }

        try:
            resp = httpx.post(
                urljoin(self._base, "/v1/chat/completions"),
                headers=self._headers,
                json=payload,
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            raise ReportProviderError("PROVIDER_TIMEOUT", "Report provider timed out.", retryable=True)
        except httpx.HTTPError:
            raise ReportProviderError("PROVIDER_UNAVAILABLE", "Report provider is unavailable.", retryable=True)

        if resp.status_code in (401, 402, 404):
            raise ReportProviderError("PROVIDER_PERMANENT", "Report provider rejected the request.")
        if resp.status_code in (429, 500, 502, 503, 504):
            raise ReportProviderError("PROVIDER_TRANSIENT", "Report provider is temporarily unavailable.", retryable=True)
        if resp.status_code >= 400:
            raise ReportProviderError("PROVIDER_ERROR", "Report provider returned an error.", retryable=True)

        try:
            body = resp.json()
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError):
            raise ReportProviderError("INVALID_RESPONSE", "Provider returned an invalid response.", retryable=True)

        try:
            structured = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            raise ReportProviderError("INVALID_RESPONSE", "Provider returned invalid JSON.", retryable=True)

        return ReportResult(structured=structured, raw=body)
