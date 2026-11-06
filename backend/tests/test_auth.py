from datetime import timedelta

from app.core.security import create_access_token, hash_password
from app.db import SessionLocal
from app.models import Clinic, Role, User

BOOTSTRAP = {
    "email": "owner@example.com",
    "password": "super-secret-1",
    "full_name": "Owner User",
    "clinic_name": "Test Clinic",
}


def _bootstrap(client) -> str:
    resp = client.post("/auth/bootstrap", json=BOOTSTRAP)
    assert resp.status_code == 201
    return resp.json()["email"]


def _create_user(email: str, password: str, role: str, clinic_id: int) -> User:
    with SessionLocal() as db:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name="Clinician",
            role=role,
            clinic_id=clinic_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def test_bootstrap_creates_owner_and_blocks_second(client):
    _bootstrap(client)
    resp = client.post("/auth/bootstrap", json=BOOTSTRAP)
    assert resp.status_code == 409


def test_login_success_sets_cookie(client):
    _bootstrap(client)
    resp = client.post("/auth/login", json={"email": BOOTSTRAP["email"], "password": BOOTSTRAP["password"]})
    assert resp.status_code == 200
    assert resp.json()["role"] == Role.clinic_owner.value
    assert "access_token" in resp.cookies


def test_login_invalid_password(client):
    _bootstrap(client)
    resp = client.post("/auth/login", json={"email": BOOTSTRAP["email"], "password": "wrong-password"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


def test_login_unknown_account_same_error(client):
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever-123"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_invalid_token(client):
    assert client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_me_expired_token(client):
    _bootstrap(client)
    token = create_access_token(1, Role.clinic_owner.value, expires_delta=timedelta(minutes=-5))
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_me_with_valid_cookie(client):
    _bootstrap(client)
    client.post("/auth/login", json={"email": BOOTSTRAP["email"], "password": BOOTSTRAP["password"]})
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == BOOTSTRAP["email"]


def test_logout_clears_cookie(client):
    _bootstrap(client)
    client.post("/auth/login", json={"email": BOOTSTRAP["email"], "password": BOOTSTRAP["password"]})
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_role_gating(client):
    email = _bootstrap(client)
    client.post("/auth/login", json={"email": email, "password": BOOTSTRAP["password"]})
    assert client.get("/auth/owner-only").status_code == 200

    with SessionLocal() as db:
        clinic_id = db.query(Clinic).first().id
    _create_user("clinician@example.com", "clinician-pass-1", Role.clinician.value, clinic_id)

    client.post("/auth/login", json={"email": "clinician@example.com", "password": "clinician-pass-1"})
    assert client.get("/auth/owner-only").status_code == 403
