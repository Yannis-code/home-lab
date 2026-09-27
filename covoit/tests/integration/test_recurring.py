import conftest


def _setup_group_with_model(client):
    admin_tok = conftest.admin_token(client)
    alice = conftest.create_and_login_user(client, admin_tok, "Alice", "alice@covoit.home")
    bob = conftest.create_and_login_user(client, admin_tok, "Bob", "bob@covoit.home")
    group = conftest.create_group(client, alice["token"], "Trajet boulot")
    conftest.invite_and_join(client, group["id"], alice["token"], bob)

    response = client.post(
        f"/groups/{group['id']}/recurring-models",
        json={
            "name": "Matin",
            "origin": "Maison",
            "destination": "Travail",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "time_of_day": "08:00",
        },
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 201, response.text
    model = response.json()
    return {"alice": alice, "bob": bob, "group": group, "model": model}


def test_generate_occurrences_creates_trips_with_default_driver(client):
    ctx = _setup_group_with_model(client)
    alice, model = ctx["alice"], ctx["model"]

    response = client.post(
        f"/recurring-models/{model['id']}/generate-occurrences",
        json={"horizon_days": 1},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200, response.text
    trips = response.json()
    assert len(trips) == 2  # aujourd'hui et demain
    for trip in trips:
        assert trip["driver_id"] == alice["id"]
        assert trip["status"] == "planned"
        assert trip["recurring_model_id"] == model["id"]


def test_generate_occurrences_is_idempotent(client):
    ctx = _setup_group_with_model(client)
    alice, model = ctx["alice"], ctx["model"]

    payload = {"horizon_days": 1}
    first = client.post(
        f"/recurring-models/{model['id']}/generate-occurrences",
        json=payload,
        headers=conftest.auth_headers(alice["token"]),
    ).json()
    second = client.post(
        f"/recurring-models/{model['id']}/generate-occurrences",
        json=payload,
        headers=conftest.auth_headers(alice["token"]),
    ).json()
    assert len(first) == 2
    assert len(second) == 0  # les occurrences existent déjà


def test_paused_model_does_not_generate_occurrences(client):
    ctx = _setup_group_with_model(client)
    alice, model = ctx["alice"], ctx["model"]

    response = client.post(
        f"/recurring-models/{model['id']}/pause", headers=conftest.auth_headers(alice["token"])
    )
    assert response.status_code == 200
    assert response.json()["is_paused"] is True

    response = client.post(
        f"/recurring-models/{model['id']}/generate-occurrences",
        json={"horizon_days": 1},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 200
    assert response.json() == []

    client.post(f"/recurring-models/{model['id']}/resume", headers=conftest.auth_headers(alice["token"]))
    response = client.post(
        f"/recurring-models/{model['id']}/generate-occurrences",
        json={"horizon_days": 1},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert len(response.json()) == 2


def test_deleting_model_cancels_future_planned_trips_but_keeps_history(client):
    ctx = _setup_group_with_model(client)
    alice, model = ctx["alice"], ctx["model"]

    trips = client.post(
        f"/recurring-models/{model['id']}/generate-occurrences",
        json={"horizon_days": 1},
        headers=conftest.auth_headers(alice["token"]),
    ).json()
    trip_id = trips[0]["id"]

    response = client.delete(
        f"/recurring-models/{model['id']}", headers=conftest.auth_headers(alice["token"])
    )
    assert response.status_code == 204

    response = client.get(f"/trips/{trip_id}", headers=conftest.auth_headers(alice["token"]))
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_accepted_recurring_participant_is_added_to_generated_trips(client):
    ctx = _setup_group_with_model(client)
    alice, bob, model = ctx["alice"], ctx["bob"], ctx["model"]

    response = client.post(
        f"/recurring-models/{model['id']}/participants",
        json={"user_id": bob["id"]},
        headers=conftest.auth_headers(alice["token"]),
    )
    assert response.status_code == 201
    participant = response.json()
    assert participant["accepted"] is False

    response = client.post(
        f"/recurring-models/{model['id']}/participants/{participant['id']}/accept",
        headers=conftest.auth_headers(bob["token"]),
    )
    assert response.status_code == 200
    assert response.json()["accepted"] is True

    trips = client.post(
        f"/recurring-models/{model['id']}/generate-occurrences",
        json={"horizon_days": 0},
        headers=conftest.auth_headers(alice["token"]),
    ).json()
    assert len(trips) == 1
    trip_id = trips[0]["id"]

    response = client.get(
        f"/trips/{trip_id}/participations", headers=conftest.auth_headers(alice["token"])
    )
    assert response.status_code == 200
    participations = response.json()
    roles = {p["user_id"]: p["role"] for p in participations}
    assert roles[alice["id"]] == "driver"
    assert roles[bob["id"]] == "passenger"
    assert all(p["status"] == "accepted" for p in participations)
