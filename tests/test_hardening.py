"""Regression tests for production hardening and safe exported data."""
import csv
import io
from urllib.parse import quote

import pytest

from app import create_app
from app.config import ProductionConfig
from tests.conftest import login


@pytest.mark.parametrize("secret", ["", "short-secret", "dev-key-not-secure-change-me"])
def test_production_rejects_missing_or_weak_session_secret(monkeypatch, secret):
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", secret)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")


def test_production_accepts_configured_session_secret(monkeypatch):
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "unique-for-this-deployment-" + "x" * 40)
    app = create_app("production")
    assert app.config["SECRET_KEY"] == "unique-for-this-deployment-" + "x" * 40


@pytest.mark.parametrize("target", [
    "//attacker.example/landing",
    "/\\attacker.example/landing",
    "/%2F%2Fattacker.example/landing",
    "/%5Cattacker.example/landing",
    "https://attacker.example/landing",
    "/%0d%0aLocation:attacker.example",
])
def test_login_rejects_external_next_url(client, member_user, target):
    path = "/auth/login?next=" + quote(target, safe="")
    response = client.post(path, data={
        "email": "member@example.com", "password": "Password123",
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "/profile/dashboard"


def test_login_accepts_valid_local_next_url(client, member_user):
    response = client.post("/auth/login?next=%2Fservices", data={
        "email": "member@example.com", "password": "Password123",
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "/services"


def test_admin_csv_export_escapes_spreadsheet_formulas(client, db, admin_user, member_user):
    member_user.full_name = "=2+2"
    member_user.profile.phone_number = "+2348012345678"
    member_user.profile.profession = " @SUM(1,1)"
    db.session.commit()

    login(client, "admin@example.com")
    response = client.get("/admin/export/members.csv")
    assert response.status_code == 200

    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
    assert rows[0][0] == "Full Name"
    member = next(row for row in rows[1:] if row[1] == "member@example.com")
    assert member[0] == "'=2+2"
    assert member[5] == "' @SUM(1,1)"
    assert member[6] == "'+2348012345678"
