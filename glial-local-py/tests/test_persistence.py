from glial_local import (
    ContextState,
    EnableSharingRequest,
    InMemoryGripSessionPersistence,
    NewSessionRequest,
    PersistedChange,
    RemoveSessionRequest,
    SessionSnapshot,
)


def _make_snapshot(session_id: str) -> SessionSnapshot:
    return SessionSnapshot(
        session_id=session_id,
        contexts={
            "/root": ContextState(path="/root", name="root", children=[], drips={})
        },
    )


def test_in_memory_persistence_create_hydrate_collapse_and_remove() -> None:
    persistence = InMemoryGripSessionPersistence()
    summary = persistence.new_session(
        NewSessionRequest(
            session_id="session-a",
            title="A",
            initial_snapshot=_make_snapshot("session-a"),
        )
    )
    assert summary.session_id == "session-a"

    listed = persistence.list_sessions()
    assert [entry.session_id for entry in listed] == ["session-a"]

    persistence.write_incremental_change(
        "session-a",
        PersistedChange(
            change_id="change-1",
            session_id="session-a",
            source="local",
            status="applied",
            origin_mutation_seq=1,
            target_kind="drip",
            path="/root",
            grip_id="app:value",
            payload={
                "grip_id": "app:value",
                "name": "value",
                "value": 42,
                "taps": [],
            },
        ),
    )

    hydrated = persistence.hydrate("session-a")
    assert hydrated.applied_changes[0].change_id == "change-1"
    assert hydrated.snapshot.contexts["/root"].drips["app:value"].value == 42

    persistence.collapse("session-a")
    hydrated = persistence.hydrate("session-a")
    assert hydrated.applied_changes == []
    assert hydrated.snapshot.contexts["/root"].drips["app:value"].value == 42

    persistence.remove_session(RemoveSessionRequest(session_id="session-a"))
    assert persistence.get_session("session-a") is None


def test_in_memory_persistence_emits_delta_and_sharing_events() -> None:
    persistence = InMemoryGripSessionPersistence()
    persistence.new_session(NewSessionRequest(session_id="session-b"))
    events: list[str] = []

    unsubscribe = persistence.subscribe("session-b", lambda event: events.append(event[0]))
    persistence.write_incremental_change(
        "session-b",
        PersistedChange(
            change_id="change-2",
            session_id="session-b",
            source="local",
            status="pending_sync",
            origin_mutation_seq=2,
            target_kind="context",
            path="/root",
            payload={
                "path": "/root",
                "name": "root",
                "children": [],
                "drips": {},
            },
        ),
    )
    persistence.enable_sharing(EnableSharingRequest(session_id="session-b"))
    unsubscribe()

    assert "delta" in events
    assert "sharing_state" in events
