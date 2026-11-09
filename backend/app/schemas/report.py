from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MedicationItem(BaseModel):
    name: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None


class PatientInformation(BaseModel):
    name: Optional[str] = None
    mobile: Optional[str] = None
    consultation_date: Optional[str] = None


class StructuredReport(BaseModel):
    patient_information: Optional[PatientInformation] = None
    chief_complaint: Optional[str] = None
    symptoms: Optional[list[str]] = None
    medical_history: Optional[str] = None
    clinical_observations: Optional[list[str]] = None
    diagnosis: Optional[str] = None
    medications: Optional[list[MedicationItem]] = None
    investigations: Optional[list[str]] = None
    treatment_and_advice: Optional[str] = None
    follow_up: Optional[str] = None
    unclear_or_missing: Optional[list[str]] = None


class ReportUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_information: Optional[PatientInformation] = None
    chief_complaint: Optional[str] = Field(default=None, max_length=4000)
    symptoms: Optional[list[str]] = None
    medical_history: Optional[str] = Field(default=None, max_length=4000)
    clinical_observations: Optional[list[str]] = None
    diagnosis: Optional[str] = Field(default=None, max_length=2000)
    medications: Optional[list[MedicationItem]] = None
    investigations: Optional[list[str]] = None
    treatment_and_advice: Optional[str] = Field(default=None, max_length=8000)
    follow_up: Optional[str] = Field(default=None, max_length=4000)
    unclear_or_missing: Optional[list[str]] = None
