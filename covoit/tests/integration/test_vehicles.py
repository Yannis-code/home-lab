import conftest


def test_create_vehicle_with_energies(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")

    vehicle = conftest.create_vehicle(
        client,
        alice["token"],
        brand="Peugeot",
        model="308",
        seats=5,
        energies=[{"energy_type": "petrol", "consumption_per_100km": 6.0}],
    )
    assert vehicle["owner_id"] == alice["id"]
    assert vehicle["seats"] == 5
    assert vehicle["energies"] == [{"energy_type": "petrol", "consumption_per_100km": 6.0}]


def test_hybrid_vehicle_can_have_multiple_energies(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")

    vehicle = conftest.create_vehicle(
        client,
        alice["token"],
        brand="Toyota",
        model="Prius",
        seats=5,
        energies=[
            {"energy_type": "petrol", "consumption_per_100km": 3.0},
            {"energy_type": "electric", "consumption_per_100km": 12.0},
        ],
    )
    assert len(vehicle["energies"]) == 2


def test_vehicle_without_energy_is_rejected(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    response = client.post(
        "/vehicles",
        json={"brand": "Peugeot", "model": "308", "seats": 5, "energies": []},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 409


def test_only_owner_can_share_vehicle(client):
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
        seats=5,
        energies=[{"energy_type": "petrol", "consumption_per_100km": 6.0}],
    )

    response = client.post(
        f"/vehicles/{vehicle['id']}/share",
        json={"group_id": group["id"]},
        headers=conftest.auth_headers(bob["token"]),
    )
    assert response.status_code == 403

    response = client.post(
        f"/vehicles/{vehicle['id']}/share",
        json={"group_id": group["id"]},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 204
