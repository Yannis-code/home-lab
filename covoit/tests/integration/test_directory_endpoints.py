import conftest


def test_list_my_groups_returns_only_active_memberships(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.create_group(client, alice["token"], "Trajet piscine")

    response = client.get("/groups", headers=conftest.auth_headers(alice["token"]))
    assert response.status_code == 200
    names = {g["name"] for g in response.json()}
    assert names == {"Trajet boulot", "Trajet piscine"}

    response = client.get("/groups", headers=conftest.auth_headers(bob["token"]))
    assert response.status_code == 200
    assert response.json() == []


def test_list_my_invitations(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")

    response = client.get("/users/me/invitations", headers=conftest.auth_headers(bob["token"]))
    assert response.json() == []

    client.post(
        f"/groups/{group['id']}/invitations",
        json={"user_id": bob["id"]},
        headers=conftest.auth_headers(alice["token"]),
    )
    response = client.get("/users/me/invitations", headers=conftest.auth_headers(bob["token"]))
    assert response.status_code == 200
    invitations = response.json()
    assert len(invitations) == 1
    assert invitations[0]["group_id"] == group["id"]
    assert invitations[0]["group_name"] == "Trajet boulot"

    # Une fois acceptée, l'invitation ne doit plus apparaître.
    client.post(
        f"/groups/{group['id']}/invitations/{invitations[0]['id']}/accept",
        headers=conftest.auth_headers(bob["token"]),
    )
    response = client.get("/users/me/invitations", headers=conftest.auth_headers(bob["token"]))
    assert response.json() == []


def test_search_users_by_name(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")

    response = client.get("/users", params={"query": "ali"}, headers=conftest.auth_headers(alice["token"]))
    assert response.status_code == 200
    names = {u["name"] for u in response.json()}
    assert names == {"Alice"}

    response = client.get("/users", headers=conftest.auth_headers(alice["token"]))
    names = {u["name"] for u in response.json()}
    assert {"Alice", "Bob", "Administrateur"}.issubset(names)


def test_list_group_vehicles_includes_owned_and_shared(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.invite_and_join(client, group["id"], alice["token"], bob)

    alice_vehicle = conftest.create_vehicle(
        client,
        alice["token"],
        brand="Peugeot",
        model="308",
        seats=5,
        energies=[{"energy_type": "petrol", "consumption_per_100km": 6.0}],
    )
    bob_vehicle = conftest.create_vehicle(
        client,
        bob["token"],
        brand="Renault",
        model="Clio",
        seats=4,
        energies=[{"energy_type": "diesel", "consumption_per_100km": 4.5}],
    )

    # Sans partage, Alice ne voit que son propre véhicule pour son propre trajet.
    response = client.get(
        f"/groups/{group['id']}/vehicles",
        params={"driver_id": alice["id"]},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200
    assert [v["id"] for v in response.json()] == [alice_vehicle["id"]]

    client.post(
        f"/vehicles/{bob_vehicle['id']}/share",
        json={"group_id": group["id"]},
        headers=conftest.auth_headers(bob["token"]),
    )
    response = client.get(
        f"/groups/{group['id']}/vehicles",
        params={"driver_id": alice["id"]},
        headers=conftest.auth_headers(alice["token"]),
    )
    ids = {v["id"] for v in response.json()}
    assert ids == {alice_vehicle["id"], bob_vehicle["id"]}
