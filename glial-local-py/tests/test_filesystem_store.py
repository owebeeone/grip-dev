from tempfile import TemporaryDirectory

from glial_local import (
    bind_launcher_session_to_existing_session,
    ContextState,
    create_launcher_session_id,
    ensure_launcher_session_record,
    FilesystemGripSessionStore,
    NewSessionRequest,
    PersistedChange,
    SessionSnapshot,
)


def test_filesystem_store_persists_across_instances_and_collapses() -> None:
    with TemporaryDirectory() as tmp:
        store = FilesystemGripSessionStore(tmp)
        store.new_session(
            NewSessionRequest(
                session_id="session-a",
                initial_snapshot=SessionSnapshot(
                    session_id="session-a",
                    contexts={
                        "/root": ContextState(path="/root", name="root", children=[], drips={})
                    },
                ),
            )
        )
        store.write_incremental_change(
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
                    "value": 101,
                    "taps": [],
                },
            ),
        )

        reloaded = FilesystemGripSessionStore(tmp)
        hydrated = reloaded.hydrate("session-a")
        assert hydrated.snapshot.contexts["/root"].drips["app:value"].value == 101
        assert len(hydrated.applied_changes) == 1

        reloaded.collapse("session-a")
        hydrated = reloaded.hydrate("session-a")
        assert hydrated.applied_changes == []


def test_filesystem_store_persists_launcher_session_records() -> None:
    with TemporaryDirectory() as tmp:
        store = FilesystemGripSessionStore(tmp)
        launcher_session_id = create_launcher_session_id("fs")

        initial = ensure_launcher_session_record(
            store,
            launcher_session_id,
            title="Filesystem session",
            storage_mode="local",
        )
        replacement = store.new_session(NewSessionRequest(title="Replacement session"))
        bind_launcher_session_to_existing_session(
            store,
            launcher_session_id,
            replacement,
            "local",
        )

        reloaded = FilesystemGripSessionStore(tmp)
        listed = reloaded.list_launcher_sessions()
        assert len(listed) == 1
        assert listed[0].launcher_session_id == launcher_session_id
        assert listed[0].glial_session_id == replacement.session_id
        assert listed[0].glial_session_id != initial.glial_session_id
