from datetime import date
from decimal import Decimal

import conftest


def _closed_ledger_scenario(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.invite_and_join(client, group["id"], alice["token"], bob)

    vehicle = conftest.create_vehicle(
        client,
        alice["token"],
        brand="Peugeot",
        model="308",
        seats=2,
        energies=[{"energy_type": "petrol", "consumption_per_100km": 6.0}],
    )

    today = date.today()
    trip = client.post(
        f"/groups/{group['id']}/trips",
        json={
            "date": today.isoformat(),
            "time_of_day": "08:00",
            "origin": "Maison",
            "destination": "Travail",
            "driver_id": alice["id"],
            "vehicle_id": vehicle["id"],
            "passenger_ids": [bob["id"]],
            "segments": [{"distance_km": 100, "occupant_ids": [alice["id"], bob["id"]]}],
        },
        headers=conftest.auth_headers(alice["token"]),
    ).json()

    client.post(
        f"/trips/{trip['id']}/status",
        json={"status": "completed"},
        headers=conftest.auth_headers(alice["token"]),
    )
    conftest.set_price(client, alice["token"], vehicle["id"], "petrol", today.year, today.month, 1.80)

    segment_id = client.get(
        f"/trips/{trip['id']}/segments", headers=conftest.auth_headers(alice["token"])
    ).json()[0]["id"]

    return {
        "alice": alice,
        "bob": bob,
        "group": group,
        "trip": trip,
        "segment_id": segment_id,
        "year": today.year,
        "month": today.month,
    }


def _close_ledger(client, ctx):
    for user in (ctx["alice"], ctx["bob"]):
        response = client.post(
            f"/groups/{ctx['group']['id']}/ledger/validate",
            json={"year": ctx["year"], "month": ctx["month"]},
            headers=conftest.auth_headers(user["token"]),
        )
        assert response.status_code == 200
    return response.json()


def test_correction_is_rejected_before_closure(client):
    ctx = _closed_ledger_scenario(client)
    response = client.post(
        f"/groups/{ctx['group']['id']}/ledger/corrections",
        json={
            "year": ctx["year"],
            "month": ctx["month"],
            "segment_id": ctx["segment_id"],
            "new_distance_km": 120,
            "reason": "Correction odomètre",
        },
        headers=conftest.auth_headers(ctx["alice"]["token"]),
    )
    assert response.status_code == 409


def test_only_manager_can_correct_closed_ledger(client):
    ctx = _closed_ledger_scenario(client)
    _close_ledger(client, ctx)

    response = client.post(
        f"/groups/{ctx['group']['id']}/ledger/corrections",
        json={
            "year": ctx["year"],
            "month": ctx["month"],
            "segment_id": ctx["segment_id"],
            "new_distance_km": 120,
            "reason": "Correction odomètre",
        },
        headers=conftest.auth_headers(ctx["bob"]["token"]),
    )
    assert response.status_code == 403


def test_correction_carries_balance_delta_to_next_month(client):
    ctx = _closed_ledger_scenario(client)
    _close_ledger(client, ctx)

    response = client.post(
        f"/groups/{ctx['group']['id']}/ledger/corrections",
        json={
            "year": ctx["year"],
            "month": ctx["month"],
            "segment_id": ctx["segment_id"],
            "new_distance_km": 120,
            "reason": "Correction odomètre",
        },
        headers=conftest.auth_headers(ctx["alice"]["token"]),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    adjustments = {a["user_id"]: a["amount"] for a in body["adjustments"]}
    # Ancien coût 10.80 (5.40 chacun) -> nouveau coût 12.96 (6.48 chacun) : écart de 1.08.
    assert round(adjustments[ctx["alice"]["id"]], 2) == 1.08
    assert round(adjustments[ctx["bob"]["id"]], 2) == -1.08

    next_year, next_month = (
        (ctx["year"] + 1, 1) if ctx["month"] == 12 else (ctx["year"], ctx["month"] + 1)
    )
    response = client.get(
        f"/groups/{ctx['group']['id']}/ledger",
        params={"year": next_year, "month": next_month},
        headers=conftest.auth_headers(ctx["alice"]["token"]),
    )
    assert response.status_code == 200
    next_ledger = response.json()
    assert next_ledger["issues"] == []
    assert Decimal(next_ledger["balances"][str(ctx["alice"]["id"])]) == Decimal("1.08")
    assert Decimal(next_ledger["balances"][str(ctx["bob"]["id"])]) == Decimal("-1.08")
