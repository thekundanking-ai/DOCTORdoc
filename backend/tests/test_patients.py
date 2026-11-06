from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Clinic, User

BOOT = {
    "email": "owner@example.com",
    "password": "super-secret-1",
    "full_name": "Owner User",
    "clinic_name": "Test Clinic",
}

MOBILE = "+15551234567"


def _bootstrap(client) -> None:
    resp = client.post("/auth/bootstrap", json=BOOT)
    assert resp.status_code == 201


def _login(client, email: str = BOOT["email"], password: str = BOOT["password"]) -> None:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200


def _create_other_clinic_user() -> dict:
    with SessionLocal() as db:
        clinic = Clinic(name="Other Clinic", slug="other-clinic")
        db.add(clinic)
        db.flush()
        user = User(
            email="other@example.com",
            hashed_password=hash_password("other-pass-1"),
            full_name="Other Staff",
            role="staff",
            clinic_id=clinic.id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"email": user.email, "password": "other-pass-1", "clinic_id": clinic.id}


def _create_patient(client, full_name: str, mobile: str = MOBILE) -> int:
    resp = client.post("/patients", json={"full_name": full_name, "mobile": mobile})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_create_patient(client):
    _bootstrap(client)
    _login(client)
    resp = client.post("/patients", json={"full_name": "Alice Smith", "mobile": MOBILE})
    assert resp.status_code == 201
    data = resp.json()
    assert data["full_name"] == "Alice Smith"
    assert data["mobile"] == MOBILE
    assert data["is_active"] is True
    assert data["clinic_id"] == 1


def test_create_patient_invalid_input(client):
    _bootstrap(client)
    _login(client)
    assert client.post("/patients", json={"full_name": "A", "mobile": "123"}).status_code == 422
    assert client.post("/patients", json={"full_name": "A", "mobile": "abc123"}).status_code == 422
    assert client.post("/patients", json={"full_name": "   ", "mobile": MOBILE}).status_code == 422


def test_duplicate_patient_rejected(client):
    _bootstrap(client)
    _login(client)
    _create_patient(client, "Alice Smith")
    dup = client.post("/patients", json={"full_name": "Alice Smith", "mobile": MOBILE})
    assert dup.status_code == 409
    different_name = client.post("/patients", json={"full_name": "Bob Jones", "mobile": MOBILE})
    assert different_name.status_code == 201


def test_cross_clinic_isolation(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client, "Alice Smith")

    other = _create_other_clinic_user()
    _login(client, other["email"], other["password"])

    assert client.get("/patients").json()["total"] == 0
    assert client.get(f"/patients/{patient_id}").status_code == 404
    assert client.patch(f"/patients/{patient_id}", json={"full_name": "Hacked"}).status_code == 404
    assert client.post(f"/patients/{patient_id}/archive").status_code == 404


def test_search_by_name_and_mobile(client):
    _bootstrap(client)
    _login(client)
    _create_patient(client, "Alice Smith", "+15551234567")
    _create_patient(client, "Alice Johnson", "+14700000123")
    _create_patient(client, "Bob Brown", "+15551234567")

    by_name = client.get("/patients", params={"q": "ali"}).json()
    assert by_name["total"] == 2
    by_mobile = client.get("/patients", params={"q": "555"}).json()
    assert by_mobile["total"] == 2


def test_pagination_and_sort(client):
    _bootstrap(client)
    _login(client)
    for i in range(25):
        _create_patient(client, f"Patient {i:02d}")

    page1 = client.get("/patients", params={"page": 1, "page_size": 10}).json()
    assert page1["total"] == 25
    assert len(page1["items"]) == 10

    sorted_asc = client.get("/patients", params={"sort": "full_name", "order": "asc", "page_size": 25}).json()
    names = [item["full_name"] for item in sorted_asc["items"]]
    assert names == sorted(names)


def test_update_patient(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client, "Alice Smith")

    resp = client.patch(f"/patients/{patient_id}", json={"full_name": "Alice Smith Jr", "mobile": "+19990000000"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["full_name"] == "Alice Smith Jr"
    assert data["mobile"] == "+19990000000"

    _create_patient(client, "Bob Jones")
    conflict = client.patch("/patients/2", json={"full_name": "Alice Smith Jr", "mobile": "+19990000000"})
    assert conflict.status_code == 409


def test_archive_workflow(client):
    _bootstrap(client)
    _login(client)
    patient_id = _create_patient(client, "Alice Smith")

    archived = client.post(f"/patients/{patient_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False

    assert client.get("/patients").json()["total"] == 0
    assert client.get("/patients", params={"include_archived": True}).json()["total"] == 1
    assert client.get(f"/patients/{patient_id}").status_code == 200


def test_unauthenticated_access(client):
    assert client.get("/patients").status_code == 401
    assert client.post("/patients", json={"full_name": "X", "mobile": MOBILE}).status_code == 401
