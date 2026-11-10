import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import Patient, User

router = APIRouter()

MOBILE_PATTERN = re.compile(r"^\+?[0-9]{7,15}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PatientCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    mobile: str
    email: str | None = None

    @field_validator("full_name")
    @classmethod
    def _strip_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("full name is required")
        return value

    @field_validator("mobile")
    @classmethod
    def _validate_mobile(cls, value: str) -> str:
        value = value.strip()
        if not MOBILE_PATTERN.match(value):
            raise ValueError("invalid mobile number")
        return value

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            return None
        if not EMAIL_PATTERN.match(value):
            raise ValueError("invalid email address")
        return value.lower()


class PatientUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    mobile: str | None = None
    email: str | None = None
    is_active: bool | None = None

    @field_validator("full_name")
    @classmethod
    def _strip_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("full name cannot be empty")
        return value

    @field_validator("mobile")
    @classmethod
    def _validate_mobile(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not MOBILE_PATTERN.match(value):
            raise ValueError("invalid mobile number")
        return value

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            return None
        if not EMAIL_PATTERN.match(value):
            raise ValueError("invalid email address")
        return value.lower()


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clinic_id: int
    full_name: str
    mobile: str
    email: str | None = None
    is_active: bool
    created_by: int
    created_at: object
    updated_at: object


class PatientList(BaseModel):
    items: list[PatientOut]
    total: int
    page: int
    page_size: int


def _normalize_mobile(mobile: str) -> str:
    return re.sub(r"\D", "", mobile)


def _get_scoped_patient(db: Session, patient_id: int, clinic_id: int) -> Patient | None:
    return db.scalar(select(Patient).where(Patient.id == patient_id, Patient.clinic_id == clinic_id))


def _active_duplicate(
    db: Session, clinic_id: int, name_normalized: str, mobile_normalized: str, exclude_id: int | None = None
) -> Patient | None:
    stmt = select(Patient).where(
        Patient.clinic_id == clinic_id,
        Patient.is_active.is_(True),
        func.lower(Patient.full_name) == name_normalized,
        Patient.mobile_normalized == mobile_normalized,
    )
    if exclude_id is not None:
        stmt = stmt.where(Patient.id != exclude_id)
    return db.scalar(stmt)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PatientOut)
def create_patient(
    payload: PatientCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Patient:
    mobile_normalized = _normalize_mobile(payload.mobile)
    if _active_duplicate(db, user.clinic_id, payload.full_name.lower(), mobile_normalized):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A patient with this name and mobile already exists"
        )

    patient = Patient(
        clinic_id=user.clinic_id,
        full_name=payload.full_name,
        mobile=payload.mobile,
        mobile_normalized=mobile_normalized,
        email=payload.email,
        created_by=user.id,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("", response_model=PatientList)
def list_patients(
    q: str | None = None,
    include_archived: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort: Literal["created_at", "updated_at", "full_name"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientList:
    filters = [Patient.clinic_id == user.clinic_id]
    if not include_archived:
        filters.append(Patient.is_active.is_(True))
    if q:
        q = q.strip()
        if q:
            like = f"%{q}%"
            conditions = [Patient.full_name.ilike(like)]
            mobile_query = _normalize_mobile(q)
            if mobile_query:
                conditions.append(Patient.mobile_normalized.like(f"%{mobile_query}%"))
            filters.append(or_(*conditions))

    base = select(Patient).where(*filters)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    column = getattr(Patient, sort)
    column = column.desc() if order == "desc" else column.asc()
    items = db.scalars(base.order_by(column).offset((page - 1) * page_size).limit(page_size)).all()
    return PatientList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Patient:
    patient = _get_scoped_patient(db, patient_id, user.clinic_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: int,
    payload: PatientUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Patient:
    patient = _get_scoped_patient(db, patient_id, user.clinic_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    if payload.full_name is not None:
        patient.full_name = payload.full_name
    if payload.mobile is not None:
        patient.mobile = payload.mobile
        patient.mobile_normalized = _normalize_mobile(payload.mobile)
    if payload.email is not None:
        patient.email = payload.email
    if payload.is_active is not None:
        patient.is_active = payload.is_active

    if _active_duplicate(db, user.clinic_id, patient.full_name.lower(), patient.mobile_normalized, exclude_id=patient.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A patient with this name and mobile already exists"
        )

    db.commit()
    db.refresh(patient)
    return patient


@router.post("/{patient_id}/archive", response_model=PatientOut)
def archive_patient(
    patient_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Patient:
    patient = _get_scoped_patient(db, patient_id, user.clinic_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    patient.is_active = False
    db.commit()
    db.refresh(patient)
    return patient






