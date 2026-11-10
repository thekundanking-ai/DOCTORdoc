import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.delivery import get_delivery_provider
from app.core.delivery.smtp import SmtpDeliveryProvider
from app.core.ratelimit import RateLimiter
from app.core.security import (
    create_access_token,
    generate_verification_token,
    hash_password,
    hash_verification_token,
    verify_password,
)
from app.db import get_db
from app.models import Clinic, Role, User

logger = logging.getLogger(__name__)

router = APIRouter()

_register_limiter = RateLimiter(limit=settings.rate_limit_register, window_seconds=settings.rate_limit_window_seconds)
_login_limiter = RateLimiter(limit=settings.rate_limit_login, window_seconds=settings.rate_limit_window_seconds)

VERIFICATION_TTL_HOURS = 24


class BootstrapIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    clinic_name: str = Field(min_length=1, max_length=255)


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    clinic_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: str
    clinic_id: int


class RegisterOut(UserOut):
    # Present only in development when SMTP is not configured (DEBUG=true) so
    # developers can complete verification without a real mail transport.
    dev_verification_token: str | None = None


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "clinic"


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug = base
    n = 2
    while db.query(Clinic).filter(Clinic.slug == slug).first():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password)


def _send_verification_email(recipient: str, token: str) -> None:
    provider = get_delivery_provider()
    if isinstance(provider, SmtpDeliveryProvider):
        provider.send_text(
            recipient,
            "Verify your DoctorDoc account",
            "Welcome to DoctorDoc!\n\n"
            "Your email verification token is:\n\n"
            f"{token}\n\n"
            f"It expires in {VERIFICATION_TTL_HOURS} hours. Visit /auth/verify-email to activate your account.",
        )
    else:
        logger.warning("No real SMTP provider available; verification email not sent for %s", recipient)


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def bootstrap(payload: BootstrapIn, db: Session = Depends(get_db)) -> User:
    existing = db.query(User).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bootstrap already completed")

    clinic = Clinic(name=payload.clinic_name, slug=_unique_slug(db, payload.clinic_name))
    db.add(clinic)
    db.flush()

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=Role.clinic_owner.value,
        clinic_id=clinic.id,
        email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterOut)
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)) -> RegisterOut:
    if not _register_limiter.allow(_client_ip(request)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many registration attempts")
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Passwords do not match")

    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    if not _smtp_configured() and not settings.debug:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        )

    clinic = Clinic(name=payload.clinic_name, slug=_unique_slug(db, payload.clinic_name))
    db.add(clinic)
    db.flush()

    token = generate_verification_token()
    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=Role.clinic_owner.value,
        clinic_id=clinic.id,
        email_verified=False,
        verification_token_hash=hash_verification_token(token),
        verification_expires_at=datetime.now(timezone.utc) + timedelta(hours=VERIFICATION_TTL_HOURS),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    db.refresh(user)

    dev_token = None
    if _smtp_configured():
        try:
            _send_verification_email(email, token)
        except Exception as exc:
            logger.error("Failed to send verification email to %s: %s", email, exc)
    else:
        dev_token = token

    out = RegisterOut.model_validate(user)
    out.dev_verification_token = dev_token
    return out


@router.post("/verify-email", status_code=status.HTTP_200_OK)
def verify_email(payload: VerifyEmailIn, db: Session = Depends(get_db)) -> dict:
    digest = hash_verification_token(payload.token)
    user = db.query(User).filter(User.verification_token_hash == digest).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token")
    if user.verification_expires_at is None or user.verification_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification token has expired")

    user.email_verified = True
    user.verification_token_hash = None
    user.verification_expires_at = None

    clinic = db.get(Clinic, user.clinic_id)
    if clinic is not None and not clinic.sender_email:
        clinic.sender_email = user.email

    db.commit()
    return {"ok": True}


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, request: Request, db: Session = Depends(get_db)) -> User:
    if not _login_limiter.allow(_client_ip(request)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")

    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.hashed_password) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")

    token = create_access_token(user.id, user.role)
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
        max_age=settings.access_token_expire_minutes * 60,
    )
    return user


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(key=settings.cookie_name, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/owner-only")
def owner_only(user: User = Depends(require_roles(Role.clinic_owner, Role.admin))) -> dict:
    return {"message": "owner/admin access granted"}
