from fastapi.testclient import TestClient

from glial_router import create_app
from glial_router.coordinator import InMemoryGlialCoordinator
from glial_router.remote_store import FilesystemRemoteSessionStore


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


def test_shared_session_graph_lease_and_value_round_trip() -> None:
    client = TestClient(create_app())

    save_response = client.put(
        "/shared-sessions/session-shared-a",
        params={"user_id": "user-a"},
        json={
            "title": "Shared A",
            "snapshot": {
                "session_id": "session-shared-a",
                "contexts": {
                    "main-home": {
                        "path": "main-home",
                        "name": "main-home",
                        "children": [],
                        "drips": {
                            "app:Count": {
                                "grip_id": "app:Count",
                                "name": "Count",
                                "value": 3,
                                "taps": [],
                            }
                        },
                    }
                },
                "taps": {
                    "tap-count": {
                        "tap_id": "tap-count",
                        "tap_type": "AtomValueTap",
                        "home_path": "main-home",
                        "mode": "replicated",
                        "role": "primary",
                        "provides": ["app:Count"],
                    }
                },
            },
        },
    )
    assert save_response.status_code == 200

    load_response = client.get(
        "/shared-sessions/session-shared-a",
        params={"user_id": "user-a"},
    )
    assert load_response.status_code == 200
    assert load_response.json()["snapshot"]["taps"]["tap-count"]["tap_type"] == "AtomValueTap"

    contexts_response = client.get(
        "/shared-sessions/session-shared-a/contexts",
        params={"user_id": "user-a"},
    )
    assert contexts_response.status_code == 200
    assert "main-home" in contexts_response.json()

    taps_response = client.get(
        "/shared-sessions/session-shared-a/taps",
        params={"user_id": "user-a"},
    )
    assert taps_response.status_code == 200
    assert "tap-count" in taps_response.json()

    lease_response = client.post(
        "/shared-sessions/session-shared-a/leases/tap-count",
        params={"user_id": "user-a"},
        json={"replica_id": "headless-a", "priority": 50},
    )
    assert lease_response.status_code == 200
    assert lease_response.json()["primary_replica_id"] == "headless-a"

    value_response = client.post(
        "/shared-sessions/session-shared-a/values",
        params={"user_id": "user-a"},
        json={"path": "main-home", "grip_id": "app:Count", "value": 9},
    )
    assert value_response.status_code == 200
    assert value_response.json()["snapshot"]["contexts"]["main-home"]["drips"]["app:Count"]["value"] == 9

    release_response = client.delete(
        "/shared-sessions/session-shared-a/leases/tap-count",
        params={"user_id": "user-a", "replica_id": "headless-a"},
    )
    assert release_response.status_code == 204


def test_remote_session_delete_removes_session_from_catalog(tmp_path) -> None:
    client = TestClient(create_app())

    save_response = client.put(
        "/remote-sessions/session-remote-delete",
        params={"user_id": "user-a"},
        json={
            "title": "Remote Delete",
            "snapshot": {
                "session_id": "session-remote-delete",
                "contexts": {},
            },
        },
    )
    assert save_response.status_code == 200

    delete_response = client.delete(
        "/remote-sessions/session-remote-delete",
        params={"user_id": "user-a"},
    )
    assert delete_response.status_code == 204

    list_response = client.get("/remote-sessions", params={"user_id": "user-a"})
    assert list_response.status_code == 200
    assert list_response.json() == []

    load_response = client.get(
        "/remote-sessions/session-remote-delete",
        params={"user_id": "user-a"},
    )
    assert load_response.status_code == 404


def test_filesystem_remote_session_store_persists_across_app_instances(tmp_path) -> None:
    store = FilesystemRemoteSessionStore(tmp_path / "router-remote-store")
    first_client = TestClient(create_app(InMemoryGlialCoordinator(remote_session_store=store)))

    save_response = first_client.put(
        "/remote-sessions/session-remote-fs",
        params={"user_id": "user-fs"},
        json={
            "title": "Filesystem Remote",
            "snapshot": {
                "session_id": "session-remote-fs",
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

    second_client = TestClient(create_app(InMemoryGlialCoordinator(remote_session_store=store)))
    list_response = second_client.get("/remote-sessions", params={"user_id": "user-fs"})
    assert list_response.status_code == 200
    assert list_response.json()[0]["session_id"] == "session-remote-fs"

    load_response = second_client.get(
        "/remote-sessions/session-remote-fs",
        params={"user_id": "user-fs"},
    )
    assert load_response.status_code == 200
    assert load_response.json()["snapshot"]["session_id"] == "session-remote-fs"


def test_react_demo_static_bundle_is_served_with_spa_fallback(tmp_path) -> None:
    dist = tmp_path / "demo-dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>demo index</body></html>")
    (assets / "app.js").write_text("console.log('demo')")

    client = TestClient(create_app(react_demo_dist=dist))

    root_response = client.get("/")
    assert root_response.status_code == 200
    assert "demo index" in root_response.text

    asset_response = client.get("/demo/assets/app.js")
    assert asset_response.status_code == 200
    assert "console.log('demo')" in asset_response.text

    spa_response = client.get("/demo/settings/session-1")
    assert spa_response.status_code == 200
    assert "demo index" in spa_response.text


def test_react_viewer_static_bundle_is_served_with_spa_fallback(tmp_path) -> None:
    dist = tmp_path / "viewer-dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>viewer index</body></html>")
    (assets / "app.js").write_text("console.log('viewer')")

    client = TestClient(create_app(viewer_dist=dist))

    asset_response = client.get("/viewer/assets/app.js")
    assert asset_response.status_code == 200
    assert "console.log('viewer')" in asset_response.text

    spa_response = client.get("/viewer/sessions/shared-a")
    assert spa_response.status_code == 200
    assert "viewer index" in spa_response.text


def test_websocket_attach_sends_snapshot_and_broadcasts_submitted_changes() -> None:
    client = TestClient(create_app())

    seeded = client.post(
        "/sessions/session-live/attach",
        json={
            "snapshot": {
                "session_id": "session-live",
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
    assert seeded.status_code == 200

    with (
        client.websocket_connect("/sessions/session-live/ws") as replica_a,
        client.websocket_connect("/sessions/session-live/ws") as replica_b,
    ):
        replica_a.send_json(
            {
                "type": "attach",
                "replica_id": "replica-a",
            }
        )
        attached_a = replica_a.receive_json()
        assert attached_a["type"] == "attached"
        assert attached_a["session_id"] == "session-live"
        assert attached_a["snapshot"]["session_id"] == "session-live"

        replica_b.send_json(
            {
                "type": "attach",
                "replica_id": "replica-b",
            }
        )
        attached_b = replica_b.receive_json()
        assert attached_b["type"] == "attached"
        assert attached_b["session_id"] == "session-live"

        replica_a.send_json(
            {
                "type": "submit_change",
                "change": {
                    "change_id": "change-live-1",
                    "session_id": "session-live",
                    "source": "local",
                    "status": "pending_sync",
                    "target_kind": "drip",
                    "path": "/root",
                    "grip_id": "app:value",
                    "payload": {
                        "grip_id": "app:value",
                        "name": "value",
                        "value": 77,
                        "taps": [],
                    },
                },
            }
        )

        accepted_a = replica_a.receive_json()
        accepted_b = replica_b.receive_json()
        assert accepted_a["type"] == "accepted_change"
        assert accepted_b["type"] == "accepted_change"
        assert accepted_a["change"]["session_clock"]["logical_counter"] == 1
        assert accepted_b["change"]["payload"]["value"] == 77


def test_http_submitted_change_is_fanned_out_to_connected_websocket_replicas() -> None:
    client = TestClient(create_app())

    with client.websocket_connect("/sessions/session-http-live/ws") as replica:
        replica.send_json(
            {
                "type": "attach",
                "replica_id": "replica-http",
                "snapshot": {
                    "session_id": "session-http-live",
                    "contexts": {
                        "/root": {
                            "path": "/root",
                            "name": "root",
                            "children": [],
                            "drips": {},
                        }
                    },
                },
            }
        )
        attached = replica.receive_json()
        assert attached["type"] == "attached"

        response = client.post(
            "/sessions/session-http-live/changes",
            json={
                "change": {
                    "change_id": "change-http-1",
                    "session_id": "session-http-live",
                    "source": "local",
                    "status": "pending_sync",
                    "target_kind": "drip",
                    "path": "/root",
                    "grip_id": "app:value",
                    "payload": {
                        "grip_id": "app:value",
                        "name": "value",
                        "value": 88,
                        "taps": [],
                    },
                }
            },
        )
        assert response.status_code == 200

        accepted = replica.receive_json()
        assert accepted["type"] == "accepted_change"
        assert accepted["change"]["payload"]["value"] == 88


def test_shared_session_websocket_receives_initial_snapshot_and_fanout_updates() -> None:
    client = TestClient(create_app())

    seeded = client.put(
        "/shared-sessions/shared-live-a",
        params={"user_id": "user-a"},
        json={
            "title": "Shared Live A",
            "snapshot": {
                "session_id": "shared-live-a",
                "contexts": {
                    "main-home": {
                        "path": "main-home",
                        "name": "main-home",
                        "children": [],
                        "drips": {
                            "app:Count": {
                                "grip_id": "app:Count",
                                "name": "Count",
                                "value": 3,
                                "taps": [],
                            }
                        },
                    }
                },
                "taps": {},
            },
        },
    )
    assert seeded.status_code == 200

    with client.websocket_connect(
        "/shared-sessions/shared-live-a/ws?user_id=user-a&replica_id=viewer-a"
    ) as viewer:
        initial = viewer.receive_json()
        assert initial["type"] == "shared_session_snapshot"
        assert (
            initial["session"]["snapshot"]["contexts"]["main-home"]["drips"]["app:Count"]["value"]
            == 3
        )

        updated = client.post(
            "/shared-sessions/shared-live-a/values",
            params={"user_id": "user-a"},
            json={"path": "main-home", "grip_id": "app:Count", "value": 9},
        )
        assert updated.status_code == 200

        pushed = viewer.receive_json()
        assert pushed["type"] == "shared_session_snapshot"
        assert (
            pushed["session"]["snapshot"]["contexts"]["main-home"]["drips"]["app:Count"]["value"]
            == 9
        )

        lease = client.post(
            "/shared-sessions/shared-live-a/leases/tap-count",
            params={"user_id": "user-a"},
            json={"replica_id": "headless-a", "priority": 50},
        )
        assert lease.status_code == 200

        lease_event = viewer.receive_json()
        assert lease_event["type"] == "shared_session_snapshot"
        assert (
            lease_event["session"]["leases"]["tap-count"]["primary_replica_id"] == "headless-a"
        )
