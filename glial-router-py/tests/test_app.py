from fastapi.testclient import TestClient

from glial_router import create_app


def test_attach_submit_change_and_replay_round_trip() -> None:
    client = TestClient(create_app())

    attach_response = client.post(
        "/sessions/session-a/attach",
        json={
            "snapshot": {
                "session_id": "session-a",
                "contexts": {
                    "/root": {
                        "path": "/root",
                        "name": "root",
                        "children": [],
                        "drips": {},
                    }
                },
            }
        },
    )
    assert attach_response.status_code == 200
    assert attach_response.json()["session_id"] == "session-a"

    change_response = client.post(
        "/sessions/session-a/changes",
        json={
            "change": {
                "change_id": "change-1",
                "session_id": "session-a",
                "source": "local",
                "status": "pending_sync",
                "target_kind": "drip",
                "path": "/root",
                "grip_id": "app:value",
                "payload": {
                    "grip_id": "app:value",
                    "name": "value",
                    "value": 42,
                    "taps": [],
                },
            }
        },
    )
    assert change_response.status_code == 200
    accepted = change_response.json()["accepted_change"]
    assert accepted["session_clock"]["logical_counter"] == 1

    snapshot_response = client.get("/sessions/session-a/snapshot")
    assert snapshot_response.status_code == 200
    assert (
        snapshot_response.json()["snapshot"]["contexts"]["/root"]["drips"]["app:value"]["value"]
        == 42
    )

    replay_response = client.get("/sessions/session-a/replay", params={"since_counter": 0})
    assert replay_response.status_code == 200
    assert len(replay_response.json()["changes"]) == 1


def test_remote_session_catalog_round_trip() -> None:
    client = TestClient(create_app())

    save_response = client.put(
        "/remote-sessions/session-remote-a",
        params={"user_id": "user-a"},
        json={
            "title": "Remote A",
            "snapshot": {
                "session_id": "session-remote-a",
                "contexts": {
                    "/root": {
                        "path": "/root",
                        "name": "root",
                        "children": [],
                        "drips": {},
                    }
                },
            },
        },
    )
    assert save_response.status_code == 200

    list_response = client.get("/remote-sessions", params={"user_id": "user-a"})
    assert list_response.status_code == 200
    assert list_response.json()[0]["session_id"] == "session-remote-a"

    load_response = client.get(
        "/remote-sessions/session-remote-a",
        params={"user_id": "user-a"},
    )
    assert load_response.status_code == 200
    assert load_response.json()["snapshot"]["session_id"] == "session-remote-a"
