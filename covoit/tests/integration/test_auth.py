import conftest


def test_admin_can_login_and_must_change_password(client):
    response = client.post(
        "/auth/login", json={"email": conftest.ADMIN_EMAIL, "password": conftest.ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["must_change_password"] is True
    assert body["token"]


def test_login_with_wrong_password_is_rejected(client):
    response = client.post(
        "/auth/login", json={"email": conftest.ADMIN_EMAIL, "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_admin_creates_user_and_user_logs_in(client):
    admin_tok = conftest.admin_token(client)
    user = conftest.create_user(client, admin_tok, "Alice", "alice@covoit.home")
    token = conftest.login(client, user["email"], user["temporary_password"])
    response = client.get("/users/me", headers=conftest.auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Alice"
    assert body["must_change_password"] is True


def test_non_admin_cannot_create_users(client):
    admin_tok = conftest.admin_token(client)
    user = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    response = client.post(
        "/admin/users",
        json={"name": "Bob", "email": "bob@covoit.home"},
        headers=conftest.auth_headers(user["token"]),
    )
    assert response.status_code == 403


def test_admin_user_list_includes_deactivated_accounts(client):
    admin_tok = conftest.admin_token(client)
    user = conftest.create_user(client, admin_tok, "Alice", "alice@covoit.home")

    response = client.get("/admin/users", headers=conftest.auth_headers(admin_tok))
    assert response.status_code == 200
    names = {u["name"] for u in response.json()}
    assert "Alice" in names

    client.patch(f"/admin/users/{user['id']}/deactivate", headers=conftest.auth_headers(admin_tok))

    # L'utilisateur désactivé disparaît de la recherche générale (réservée aux comptes actifs)...
    response = client.get("/users", params={"query": "Alice"}, headers=conftest.auth_headers(admin_tok))
    assert response.status_code == 200
    assert "Alice" not in {u["name"] for u in response.json()}

    # ...mais reste visible dans la liste d'administration pour être géré.
    response = client.get("/admin/users", headers=conftest.auth_headers(admin_tok))
    assert response.status_code == 200
    alice = next(u for u in response.json() if u["name"] == "Alice")
    assert alice["is_active"] is False


def test_non_admin_cannot_list_all_users(client):
    admin_tok = conftest.admin_token(client)
    user = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    response = client.get("/admin/users", headers=conftest.auth_headers(user["token"]))
    assert response.status_code == 403


def test_change_password_requires_current_password(client):
    admin_tok = conftest.admin_token(client)
    user = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    response = client.post(
        "/auth/change-password",
        json={"current_password": "not-the-password", "new_password": "NewPassword123"},
        headers=conftest.auth_headers(user["token"]),
    )
    assert response.status_code == 401

    response = client.post(
        "/auth/change-password",
        json={"current_password": user["temporary_password"], "new_password": "NewPassword123"},
        headers=conftest.auth_headers(user["token"]),
    )
    assert response.status_code == 204

    # L'ancien mot de passe temporaire ne fonctionne plus, le nouveau si.
    response = client.post(
        "/auth/login", json={"email": user["email"], "password": user["temporary_password"]}
    )
    assert response.status_code == 401
    response = client.post(
        "/auth/login", json={"email": user["email"], "password": "NewPassword123"}
    )
    assert response.status_code == 200
    assert response.json()["must_change_password"] is False


def test_missing_authorization_header_is_rejected(client):
    response = client.get("/users/me")
    assert response.status_code == 401


def test_admin_can_reset_forgotten_password(client):
    admin_tok = conftest.admin_token(client)
    user = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    response = client.post(
        f"/admin/users/{user['id']}/reset-password", headers=conftest.auth_headers(admin_tok)
    )
    assert response.status_code == 200
    new_temp_password = response.json()["temporary_password"]
    # L'ancien mot de passe est invalidé, le nouveau mot de passe temporaire fonctionne.
    response = client.post(
        "/auth/login", json={"email": user["email"], "password": user["temporary_password"]}
    )
    assert response.status_code == 401
    response = client.post("/auth/login", json={"email": user["email"], "password": new_temp_password})
    assert response.status_code == 200
    assert response.json()["must_change_password"] is True
