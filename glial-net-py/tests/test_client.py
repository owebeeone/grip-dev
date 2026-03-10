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
