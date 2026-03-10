from fastapi.testclient import TestClient

from glial_local import EnableSharingRequest, PersistedChange
from glial_net import HttpGlialClient, HttpGripSessionLink
from glial_router import create_app


def test_http_glial_client_round_trip_against_fastapi_router() -> None:
    test_client = TestClient(create_app())
    client = HttpGlialClient(client=test_client)

    attached = client.attach_session(
        "session-a",
        {
            "session_id": "session-a",
            "contexts": {
                "/root": {
                    "path": "/root",
                    "name": "root",
                    "children": [],
                    "drips": {},
                }
            },
        },
    )
    assert attached["session_id"] == "session-a"

    accepted = client.submit_change(
        "session-a",
        PersistedChange(
            change_id="change-1",
            session_id="session-a",
            source="local",
            status="pending_sync",
            target_kind="drip",
            path="/root",
            grip_id="app:value",
            payload={
                "grip_id": "app:value",
                "name": "value",
                "value": 7,
                "taps": [],
            },
        ),
    )
    assert accepted.session_clock is not None
    assert accepted.session_clock.logical_counter == 1

    snapshot = client.get_snapshot("session-a")
    assert snapshot["snapshot"]["contexts"]["/root"]["drips"]["app:value"]["value"] == 7

    replayed = client.replay("session-a", since_counter=0)
    assert len(replayed) == 1
    assert replayed[0].change_id == "change-1"


def test_http_grip_session_link_uses_snapshot_supplier_and_tracks_last_accept() -> None:
    test_client = TestClient(create_app())
    client = HttpGlialClient(client=test_client)
    supplied = {
        "session_id": "session-b",
        "contexts": {
            "/root": {
                "path": "/root",
                "name": "root",
                "children": [],
                "drips": {},
            }
        },
    }
    link = HttpGripSessionLink(client, snapshot_supplier=lambda session_id: supplied)

    link.attach(EnableSharingRequest(session_id="session-b"))
    link.publish_local_change(
        "session-b",
        PersistedChange(
            change_id="change-2",
            session_id="session-b",
            source="local",
            status="pending_sync",
            target_kind="context",
            path="/child",
            payload={
                "path": "/child",
                "name": "child",
                "children": [],
                "drips": {},
            },
        ),
    )

    assert link.last_accepted_change is not None
    assert link.last_accepted_change.session_clock is not None


def test_http_glial_client_manages_remote_sessions_against_fastapi_router() -> None:
    test_client = TestClient(create_app())
    client = HttpGlialClient(client=test_client)

    saved = client.save_remote_session(
        "user-a",
        "session-remote-a",
        {
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
        title="Remote A",
    )
    assert saved["session_id"] == "session-remote-a"

    listed = client.list_remote_sessions("user-a")
    assert len(listed) == 1
    assert listed[0]["session_id"] == "session-remote-a"

    loaded = client.load_remote_session("user-a", "session-remote-a")
    assert loaded["snapshot"]["session_id"] == "session-remote-a"

    deleted = client.delete_remote_session("user-a", "session-remote-a")
    assert deleted is True

    assert client.list_remote_sessions("user-a") == []


def test_http_glial_client_manages_shared_sessions_against_fastapi_router() -> None:
    test_client = TestClient(create_app())
    client = HttpGlialClient(client=test_client)

    saved = client.save_shared_session(
        "user-a",
        "shared-a",
        {
            "session_id": "shared-a",
            "contexts": {
                "main-home": {
                    "path": "main-home",
                    "name": "main-home",
                    "children": [],
                    "drips": {},
                }
            },
            "taps": {},
        },
        title="Shared A",
    )
    assert saved["session_id"] == "shared-a"

    loaded = client.load_shared_session("user-a", "shared-a")
    assert loaded["snapshot"]["session_id"] == "shared-a"

    lease = client.request_tap_lease(
        "user-a",
        "shared-a",
        "tap-a",
        replica_id="headless-a",
        priority=10,
    )
    assert lease["primary_replica_id"] == "headless-a"

    updated = client.update_shared_value(
        "user-a",
        "shared-a",
        path="main-home",
        grip_id="app:Count",
        value=5,
    )
    assert updated["snapshot"]["contexts"]["main-home"]["drips"]["app:Count"]["value"] == 5

    assert client.release_tap_lease("user-a", "shared-a", "tap-a", replica_id="headless-a") is True
