"""Fixtures et utilitaires partagés pour les tests d'intégration.

Chaque test obtient une base SQLite en mémoire fraîche (le moteur global de
l'application est monkeypatché) afin que les tests restent indépendants et
puissent s'exécuter dans n'importe quel ordre.
"""

import covoit.db as db_module
import covoit.main as main_module
import pytest
from covoit.config import settings
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

ADMIN_EMAIL = "admin@covoit.home"
ADMIN_PASSWORD = "AdminPass123!"


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(main_module, "engine", engine)
    monkeypatch.setattr(settings, "admin_email", ADMIN_EMAIL)
    monkeypatch.setattr(settings, "admin_password", ADMIN_PASSWORD)
    monkeypatch.setattr(settings, "admin_name", "Administrateur")

    with TestClient(main_module.app) as test_client:
        yield test_client


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, email: str, password: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def admin_token(client) -> str:
    return login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


def create_user(client, admin_tok: str, name: str, email: str) -> dict:
    """Crée un utilisateur via l'administrateur et retourne id/email/mot de passe temporaire."""
    response = client.post(
        "/admin/users", json={"name": name, "email": email}, headers=auth_headers(admin_tok)
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "id": body["user"]["id"],
        "email": email,
        "temporary_password": body["temporary_password"],
    }


def create_and_login_user(client, admin_tok: str, name: str, email: str) -> dict:
    user = create_user(client, admin_tok, name, email)
    user["token"] = login(client, email, user["temporary_password"])
    return user


def create_group(client, token: str, name: str) -> dict:
    response = client.post("/groups", json={"name": name}, headers=auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


def invite_and_join(client, group_id: int, manager_token: str, invitee: dict) -> None:
    response = client.post(
        f"/groups/{group_id}/invitations",
        json={"user_id": invitee["id"]},
        headers=auth_headers(manager_token),
    )
    assert response.status_code == 201, response.text
    membership_id = response.json()["id"]
    response = client.post(
        f"/groups/{group_id}/invitations/{membership_id}/accept",
        headers=auth_headers(invitee["token"]),
    )
    assert response.status_code == 200, response.text


def create_vehicle(client, token: str, brand: str, model: str, seats: int, energies: list[dict]) -> dict:
    response = client.post(
        "/vehicles",
        json={"brand": brand, "model": model, "seats": seats, "energies": energies},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def set_price(client, token: str, vehicle_id: int, energy_type: str, year: int, month: int, price: float) -> dict:
    response = client.post(
        f"/vehicles/{vehicle_id}/monthly-prices",
        json={"energy_type": energy_type, "year": year, "month": month, "price_per_unit": price},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()
