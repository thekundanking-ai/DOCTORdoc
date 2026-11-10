from datetime import datetime, timedelta, timezone

from app.core.security import verify_password
from app.db import SessionLocal
from app.models import Clinic, Role, User

REGISTER = {
    "full_name": "New Owner",
    "clinic_name": "Green Clinic",
    "email": "new.owner@example.com",
    "password": "strong-pass-1",
    "confirm_password": "strong-pass-1",
}

BOOTSTRAP = {
    "email": "owner@example.com",
    "password": "super-secret-1",
    "full_name": "Owner User",
    "clinic_name": "Test Clinic",
}


def _register(client, **over):
    data = {**REGISTER, **over}
    return client.post("/auth/register", json=data)


def test_register_creates_clinic_and_unverified_owner(client):
    resp = _register(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == Role.clinic_owner.value
    assert body["email"] == REGISTER["email"]
    assert body["full_name"] == "New Owner"
    assert body.get("dev_verification_token")

    raw = resp.text
    assert "hashed_password" not in raw
    assert "smtp_password" not in raw.lower()
    assert "SMTP_PASSWORD" not in raw

    with SessionLocal() as db:
        u = db.query(User).filter(User.email == REGISTER["email"]).first()
        assert u is not None
        assert u.email_verified is False
        assert u.role == Role.clinic_owner.value
        assert u.verification_token_hash
        assert u.verification_expires_at is not None
        assert u.clinic_id
        clinic = db.get(Clinic, u.clinic_id)
        assert clinic.slug.startswith("green-clinic")


def test_register_ignores_role_field(client):
    resp = _register(client, role="admin")
    assert resp.status_code == 201
    assert resp.json()["role"] == Role.clinic_owner.value


def test_register_duplicate_email_conflict(client):
    assert _register(client).status_code == 201
    resp = _register(client)
    assert resp.status_code == 409


def test_register_duplicate_with_bootstrap_account(client):
    client.post("/auth/bootstrap", json=BOOTSTRAP)
    resp = _register(client, email=BOOTSTRAP["email"])
    assert resp.status_code == 409


def test_register_invalid_email(client):
    assert _register(client, email="not-an-email").status_code == 422


def test_register_short_password(client):
    assert _register(client, password="short", confirm_password="short").status_code == 422


def test_register_mismatched_passwords(client):
    assert _register(client, confirm_password="different-pass-9").status_code == 422


def test_register_password_is_argon2_hashed(client):
    _register(client)
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == REGISTER["email"]).first()
        assert u.hashed_password != REGISTER["password"]
        assert verify_password(REGISTER["password"], u.hashed_password) is True


def test_register_unique_slug_for_duplicate_clinic_name(client):
    a = _register(client, email="a@dup.com", clinic_name="Same Name")
    b = _register(client, email="b@dup.com", clinic_name="Same Name")
    assert a.status_code == b.status_code == 201
    with SessionLocal() as db:
        slugs = [c.slug for c in db.query(Clinic).all()]
    assert len(slugs) == len(set(slugs))


def test_verify_email_success_sets_sender_and_allows_login(client):
    resp = _register(client)
    token = resp.json()["dev_verification_token"]

    blocked = client.post("/auth/login", json={"email": REGISTER["email"], "password": REGISTER["password"]})
    assert blocked.status_code == 403

    v = client.post("/auth/verify-email", json={"token": token})
    assert v.status_code == 200
    assert v.json()["ok"] is True

    with SessionLocal() as db:
        u = db.query(User).filter(User.email == REGISTER["email"]).first()
        assert u.email_verified is True
        assert u.verification_token_hash is None
        assert u.verification_expires_at is None
        clinic = db.get(Clinic, u.clinic_id)
        assert clinic.sender_email == u.email

    lr = client.post("/auth/login", json={"email": REGISTER["email"], "password": REGISTER["password"]})
    assert lr.status_code == 200


def test_verify_email_wrong_token(client):
    _register(client)
    resp = client.post("/auth/verify-email", json={"token": "wrong-token"})
    assert resp.status_code == 400


def test_verify_email_expired_token(client):
    resp = _register(client)
    token = resp.json()["dev_verification_token"]
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == REGISTER["email"]).first()
        u.verification_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    r = client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 400
    assert "expired" in r.json()["detail"].lower()


def test_verify_email_token_reuse_rejected(client):
    resp = _register(client)
    token = resp.json()["dev_verification_token"]
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 200
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 400


def test_existing_bootstrap_owner_login_still_works(client):
    client.post("/auth/bootstrap", json=BOOTSTRAP)
    r = client.post("/auth/login", json={"email": BOOTSTRAP["email"], "password": BOOTSTRAP["password"]})
    assert r.status_code == 200
    assert r.json()["role"] == Role.clinic_owner.value


def test_cross_clinic_isolation_after_registration(client):
    t1 = _register(client, email="a@cp.com", clinic_name="Alpha Clinic").json()["dev_verification_token"]
    client.post("/auth/verify-email", json={"token": t1})
    t2 = _register(client, email="b@cp.com", clinic_name="Beta Clinic").json()["dev_verification_token"]
    client.post("/auth/verify-email", json={"token": t2})

    client.post("/auth/login", json={"email": "a@cp.com", "password": REGISTER["password"]})
    pr = client.post("/patients", json={"full_name": "Alice", "mobile": "+15551234567"})
    assert pr.status_code == 201
    pid = pr.json()["id"]

    client.post("/auth/logout")
    client.post("/auth/login", json={"email": "b@cp.com", "password": REGISTER["password"]})
    assert client.get(f"/patients/{pid}").status_code == 404
