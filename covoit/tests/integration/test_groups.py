import conftest


def test_creator_becomes_manager_member_and_default_driver(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")

    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    assert group["manager_id"] == alice["id"]
    assert group["default_driver_id"] == alice["id"]

    response = client.get(f"/groups/{group['id']}/members", headers=conftest.auth_headers(alice["token"]))
    assert response.status_code == 200
    members = response.json()
    assert len(members) == 1
    assert members[0]["user_id"] == alice["id"]
    assert members[0]["status"] == "active"


def test_invite_requires_acceptance_before_membership_is_active(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")

    response = client.post(
        f"/groups/{group['id']}/invitations",
        json={"user_id": bob["id"]},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 201
    membership = response.json()
    assert membership["status"] == "pending"

    # Bob n'est pas encore membre actif tant qu'il n'a pas accepté.
    response = client.post(
        f"/groups/{group['id']}/default-driver",
        json={"user_id": bob["id"]},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 403

    response = client.post(
        f"/groups/{group['id']}/invitations/{membership['id']}/accept",
        headers=conftest.auth_headers(bob["token"]),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"


def test_only_manager_can_invite(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    carol = conftest.create_and_login_user(client, admin_tok, "Carol", "carol@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.invite_and_join(client, group["id"], alice["token"], bob)

    response = client.post(
        f"/groups/{group['id']}/invitations",
        json={"user_id": carol["id"]},
        headers=conftest.auth_headers(bob["token"]),
    )
    assert response.status_code == 403


def test_sole_manager_cannot_leave_group(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")

    response = client.post(f"/groups/{group['id']}/leave", headers=conftest.auth_headers(alice["token"]))
    assert response.status_code == 409


def test_manager_can_transfer_then_leave(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.invite_and_join(client, group["id"], alice["token"], bob)

    response = client.post(
        f"/groups/{group['id']}/transfer-management",
        json={"new_manager_id": bob["id"]},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200
    assert response.json()["manager_id"] == bob["id"]

    response = client.post(f"/groups/{group['id']}/leave", headers=conftest.auth_headers(alice["token"]))
    assert response.status_code == 200
    assert response.json()["status"] == "left"


def test_any_active_member_can_change_default_driver(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.invite_and_join(client, group["id"], alice["token"], bob)

    response = client.post(
        f"/groups/{group['id']}/default-driver",
        json={"user_id": bob["id"]},
        headers=conftest.auth_headers(bob["token"]),
    )
    assert response.status_code == 200
    assert response.json()["default_driver_id"] == bob["id"]


def test_only_manager_can_archive_group(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.invite_and_join(client, group["id"], alice["token"], bob)

    response = client.post(f"/groups/{group['id']}/archive", headers=conftest.auth_headers(bob["token"]))
    assert response.status_code == 403

    response = client.post(f"/groups/{group['id']}/archive", headers=conftest.auth_headers(alice["token"]))
    assert response.status_code == 200
    assert response.json()["is_archived"] is True
