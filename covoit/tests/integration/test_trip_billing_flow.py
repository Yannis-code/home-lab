from datetime import date
from decimal import Decimal

import conftest


def _setup_trip(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    carol = conftest.create_and_login_user(client, admin_tok, "Carol", "carol@covoit.home")

    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.invite_and_join(client, group["id"], alice["token"], bob)
    conftest.invite_and_join(client, group["id"], alice["token"], carol)

    vehicle = conftest.create_vehicle(
        client,
        alice["token"],
        brand="Peugeot",
        model="308",
        seats=2,  # conducteur + 1 passager
        energies=[{"energy_type": "petrol", "consumption_per_100km": 6.0}],
    )

    today = date.today()
    response = client.post(
        f"/groups/{group['id']}/trips",
        json={
            "date": today.isoformat(),
            "time_of_day": "08:00",
            "origin": "Maison",
            "destination": "Travail",
            "driver_id": alice["id"],
            "vehicle_id": vehicle["id"],
            "passenger_ids": [bob["id"]],
            "segments": [
                {"distance_km": 100, "occupant_ids": [alice["id"], bob["id"]]},
            ],
        },
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 201, response.text
    trip = response.json()
    return {
        "alice": alice,
        "bob": bob,
        "carol": carol,
        "group": group,
        "vehicle": vehicle,
        "trip": trip,
        "today": today,
    }


def test_duplicate_occupant_ids_are_deduplicated_in_a_segment(client):
    ctx = _setup_trip(client)
    alice, bob, trip = ctx["alice"], ctx["bob"], ctx["trip"]

    response = client.put(
        f"/trips/{trip['id']}/segments",
        json={"segments": [{"distance_km": 100, "occupant_ids": [alice["id"], alice["id"], bob["id"]]}]},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200
    segments = response.json()
    assert len(segments) == 1
    assert sorted(segments[0]["occupant_ids"]) == sorted([alice["id"], bob["id"]])


def test_trip_creation_respects_vehicle_capacity(client):
    ctx = _setup_trip(client)
    alice, carol, trip = ctx["alice"], ctx["carol"], ctx["trip"]

    # La capacité (2, conducteur inclus) est déjà atteinte par alice + bob.
    response = client.post(
        f"/trips/{trip['id']}/participation-requests",
        json={"boarding_point": "Arrêt Carol"},
        headers=conftest.auth_headers(carol["token"]),
    )
    assert response.status_code == 201
    participation = response.json()
    assert participation["status"] == "waitlisted"

    # Le conducteur ne peut pas accepter au-delà de la capacité déclarée.
    response = client.post(
        f"/trips/{trip['id']}/participation-requests/{participation['id']}/decision",
        json={"approve": True},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 409


def test_trip_creation_over_capacity_is_rejected(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    carol = conftest.create_and_login_user(client, admin_tok, "Carol", "carol@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.invite_and_join(client, group["id"], alice["token"], bob)
    conftest.invite_and_join(client, group["id"], alice["token"], carol)
    vehicle = conftest.create_vehicle(
        client,
        alice["token"],
        brand="Peugeot",
        model="308",
        seats=2,
        energies=[{"energy_type": "petrol", "consumption_per_100km": 6.0}],
    )
    response = client.post(
        f"/groups/{group['id']}/trips",
        json={
            "date": date.today().isoformat(),
            "time_of_day": "08:00",
            "origin": "Maison",
            "destination": "Travail",
            "driver_id": alice["id"],
            "vehicle_id": vehicle["id"],
            "passenger_ids": [bob["id"], carol["id"]],
            "segments": [{"distance_km": 100, "occupant_ids": [alice["id"], bob["id"], carol["id"]]}],
        },
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 409


def test_full_billing_and_ledger_lifecycle(client):
    ctx = _setup_trip(client)
    alice, bob, carol, group, vehicle, trip, today = (
        ctx["alice"],
        ctx["bob"],
        ctx["carol"],
        ctx["group"],
        ctx["vehicle"],
        ctx["trip"],
        ctx["today"],
    )
    year, month = today.year, today.month

    # Le trajet doit être marqué effectué pour compter dans le bilan.
    response = client.post(
        f"/trips/{trip['id']}/status",
        json={"status": "completed"},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200

    # Sans prix mensuel, le bilan est bloqué (aucun solde calculable).
    response = client.get(
        f"/groups/{group['id']}/ledger",
        params={"year": year, "month": month},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["balances"] == {}
    assert any(issue["code"] == "missing_price" for issue in body["issues"])

    # Le propriétaire du véhicule renseigne le prix du mois.
    conftest.set_price(client, alice["token"], vehicle["id"], "petrol", year, month, 1.80)

    response = client.get(
        f"/groups/{group['id']}/ledger",
        params={"year": year, "month": month},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["issues"] == []
    # 100km / 100 * 6.0 L * 1.80 EUR = 10.80 EUR, partagés également entre alice et bob.
    assert Decimal(body["balances"][str(alice["id"])]) == Decimal("5.40")
    assert Decimal(body["balances"][str(bob["id"])]) == Decimal("-5.40")
    assert body["transfers"] == [
        {"debtor_id": bob["id"], "creditor_id": alice["id"], "amount": "5.40"}
    ]
    assert body["status"] == "open"

    # Carol n'a pas participé au trajet: elle ne peut pas valider le bilan.
    response = client.post(
        f"/groups/{group['id']}/ledger/validate",
        json={"year": year, "month": month},
        headers=conftest.auth_headers(carol["token"]),
    )
    assert response.status_code == 403

    # Alice valide seule: le bilan reste ouvert tant que bob n'a pas validé.
    response = client.post(
        f"/groups/{group['id']}/ledger/validate",
        json={"year": year, "month": month},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "open"

    # Bob valide à son tour: le bilan se clôture automatiquement.
    response = client.post(
        f"/groups/{group['id']}/ledger/validate",
        json={"year": year, "month": month},
        headers=conftest.auth_headers(bob["token"]),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "closed"

    # Bob rembourse Alice; le solde n'est réduit qu'après confirmation d'Alice.
    response = client.post(
        f"/groups/{group['id']}/reimbursements",
        json={"payee_id": alice["id"], "amount": 5.40, "year": year, "month": month},
        headers=conftest.auth_headers(bob["token"]),
    )
    assert response.status_code == 201
    reimbursement = response.json()
    assert reimbursement["status"] == "declared"

    response = client.get(
        f"/groups/{group['id']}/ledger",
        params={"year": year, "month": month},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert Decimal(response.json()["balances"][str(bob["id"])]) == Decimal("-5.40")

    response = client.post(
        f"/reimbursements/{reimbursement['id']}/confirm",
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"

    response = client.get(
        f"/groups/{group['id']}/ledger",
        params={"year": year, "month": month},
        headers=conftest.auth_headers(alice["token"]),
    )
    body = response.json()
    assert Decimal(body["balances"][str(alice["id"])]) == Decimal("0.00")
    assert Decimal(body["balances"][str(bob["id"])]) == Decimal("0.00")
    assert body["transfers"] == []


def test_csv_export_contains_balances(client):
    ctx = _setup_trip(client)
    alice, bob, group, vehicle, trip, today = (
        ctx["alice"],
        ctx["bob"],
        ctx["group"],
        ctx["vehicle"],
        ctx["trip"],
        ctx["today"],
    )
    client.post(
        f"/trips/{trip['id']}/status",
        json={"status": "completed"},
        headers=conftest.auth_headers(alice["token"]),
    )
    conftest.set_price(client, alice["token"], vehicle["id"], "petrol", today.year, today.month, 1.80)

    response = client.get(
        f"/groups/{group['id']}/ledger/export",
        params={"year": today.year, "month": today.month},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    text = response.text
    assert "balance" in text
    assert str(alice["id"]) in text
    assert str(bob["id"]) in text
