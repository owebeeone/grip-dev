from tempfile import TemporaryDirectory

from glial_local import (
    ContextState,
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
