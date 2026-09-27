from datetime import date

import conftest


def test_list_recurring_models(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")

    response = client.get(
        f"/groups/{group['id']}/recurring-models", headers=conftest.auth_headers(alice["token"])
    )
    assert response.status_code == 200
    assert response.json() == []

    client.post(
        f"/groups/{group['id']}/recurring-models",
        json={
            "name": "Matin",
            "origin": "Maison",
            "destination": "Travail",
            "weekdays": [0, 1, 2, 3, 4],
            "time_of_day": "08:00",
        },
        headers=conftest.auth_headers(alice["token"]),
    )
    response = client.get(
        f"/groups/{group['id']}/recurring-models", headers=conftest.auth_headers(alice["token"])
    )
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Matin"


def test_list_my_recurring_participations(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.invite_and_join(client, group["id"], alice["token"], bob)
    model = client.post(
        f"/groups/{group['id']}/recurring-models",
        json={
            "name": "Matin",
            "origin": "Maison",
            "destination": "Travail",
            "weekdays": [0, 1, 2, 3, 4],
            "time_of_day": "08:00",
        },
        headers=conftest.auth_headers(alice["token"]),
    ).json()

    response = client.get(
        "/users/me/recurring-participations", headers=conftest.auth_headers(bob["token"])
    )
    assert response.json() == []

    client.post(
        f"/recurring-models/{model['id']}/participants",
        json={"user_id": bob["id"]},
        headers=conftest.auth_headers(alice["token"]),
    )
    response = client.get(
        "/users/me/recurring-participations", headers=conftest.auth_headers(bob["token"])
    )
    assert response.status_code == 200
    participations = response.json()
    assert len(participations) == 1
    assert participations[0]["model_name"] == "Matin"
    assert participations[0]["group_id"] == group["id"]

    client.post(
        f"/recurring-models/{model['id']}/participants/{participations[0]['id']}/accept",
        headers=conftest.auth_headers(bob["token"]),
    )
    response = client.get(
        "/users/me/recurring-participations", headers=conftest.auth_headers(bob["token"])
    )
    assert response.json() == []


def test_list_reimbursements_for_group_and_month(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.invite_and_join(client, group["id"], alice["token"], bob)
    today = date.today()

    response = client.get(
        f"/groups/{group['id']}/reimbursements",
        params={"year": today.year, "month": today.month},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.json() == []

    client.post(
        f"/groups/{group['id']}/reimbursements",
        json={"payee_id": alice["id"], "amount": 12.5, "year": today.year, "month": today.month},
        headers=conftest.auth_headers(bob["token"]),
    )
    response = client.get(
        f"/groups/{group['id']}/reimbursements",
        params={"year": today.year, "month": today.month},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200
    reimbursements = response.json()
    assert len(reimbursements) == 1
    assert reimbursements[0]["payer_id"] == bob["id"]
    assert reimbursements[0]["status"] == "declared"
