"""In-memory reference implementations for Glial local-first persistence."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from time import time
from typing import Callable, TypeVar
from uuid import uuid4

from .types import (
    ContextState,
    EnableSharingRequest,
    GripSessionLink,
    GripSessionPersistence,
    GripSessionStore,
    HydratedSession,
    LauncherSessionRecord,
    LauncherSessionRecordStore,
    NewSessionRequest,
    PersistedChange,
    PersistenceEvent,
    RemoveSessionRequest,
    SessionMode,
    SessionSnapshot,
    SessionSummary,
    SharingState,
    SyncCheckpoint,
)


def _now_ms() -> int:
    return int(time() * 1000)


def _make_session_id() -> str:
    return f"session_{_now_ms()}_{uuid4().hex[:8]}"


T = TypeVar("T")


def _clone(value: T) -> T:
    return deepcopy(value)


@dataclass(slots=True)
class _SessionRecord:
    summary: SessionSummary
    snapshot: SessionSnapshot
    applied_changes: list[PersistedChange] = field(default_factory=list)
    pending_changes: list[PersistedChange] = field(default_factory=list)
    sync_checkpoint: SyncCheckpoint = field(default_factory=lambda: SyncCheckpoint(attached=False))
    sharing_state: SharingState = "detached"
    subscribers: set = field(default_factory=set)


def _create_empty_snapshot(session_id: str | None = None) -> SessionSnapshot:
    return SessionSnapshot(session_id=session_id, contexts={})


def _apply_change_to_snapshot(snapshot: SessionSnapshot, change: PersistedChange) -> None:
    path = change.path
    if change.target_kind == "context":
        payload = change.payload or {}
        snapshot.contexts[path] = ContextState(
            path=path,
            name=str(payload.get("name", path)),
            purpose=payload.get("purpose"),
            description=payload.get("description"),
            children=list(payload.get("children", [])),
            drips=deepcopy(payload.get("drips", {})),
        )
        return

    if change.target_kind == "child-order":
        context = snapshot.contexts.get(path)
        if context is None:
            return
        context.children = list((change.payload or {}).get("children", []))
        return

    if change.target_kind == "drip":
        context = snapshot.contexts.get(path)
        if context is None or change.grip_id is None:
            return
        payload = change.payload or {}
        existing = context.drips.get(change.grip_id)
        context.drips[change.grip_id] = deepcopy(existing) if existing is not None else None  # type: ignore[assignment]
        if context.drips[change.grip_id] is None:
            from .types import DripState

            context.drips[change.grip_id] = DripState(
                grip_id=change.grip_id,
                name=str(payload.get("name", change.grip_id)),
                taps=deepcopy(payload.get("taps", [])),
                value=payload.get("value"),
            )
        else:
            drip = context.drips[change.grip_id]
            drip.name = str(payload.get("name", drip.name))
            drip.value = payload.get("value", drip.value)
            drip.taps = deepcopy(payload.get("taps", drip.taps))
        return

    if change.target_kind == "tap-meta":
        context = snapshot.contexts.get(path)
        if context is None or change.grip_id is None:
            return
        drip = context.drips.get(change.grip_id)
        if drip is None:
            return
        drip.taps = deepcopy((change.payload or {}).get("taps", []))
        return

    if change.target_kind == "remove":
        if change.grip_id is None:
            snapshot.contexts.pop(path, None)
            return
        context = snapshot.contexts.get(path)
        if context is not None:
            context.drips.pop(change.grip_id, None)


class InMemoryGripSessionStore(GripSessionStore, LauncherSessionRecordStore):
    """Reference in-memory session store used by tests and early integration."""

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionRecord] = {}
        self._launcher_sessions: dict[str, LauncherSessionRecord] = {}

    def new_session(self, request: NewSessionRequest) -> SessionSummary:
        session_id = request.session_id or _make_session_id()
        summary = SessionSummary(
            session_id=session_id,
            title=request.title,
            mode="local",
            last_modified_ms=_now_ms(),
        )
        self._sessions[session_id] = _SessionRecord(
            summary=summary,
            snapshot=_clone(request.initial_snapshot or _create_empty_snapshot(session_id)),
        )
        return _clone(summary)

    def list_sessions(self) -> list[SessionSummary]:
        return sorted(
            (_clone(record.summary) for record in self._sessions.values()),
            key=lambda entry: entry.last_modified_ms,
            reverse=True,
        )

    def get_session(self, session_id: str) -> SessionSummary | None:
        record = self._sessions.get(session_id)
        return _clone(record.summary) if record is not None else None

    def list_launcher_sessions(self) -> list[LauncherSessionRecord]:
        return sorted(
            (_clone(record) for record in self._launcher_sessions.values()),
            key=lambda entry: entry.last_opened_ms,
            reverse=True,
        )

    def get_launcher_session(self, launcher_session_id: str) -> LauncherSessionRecord | None:
        record = self._launcher_sessions.get(launcher_session_id)
        return _clone(record) if record is not None else None

    def put_launcher_session(self, record: LauncherSessionRecord) -> None:
        self._launcher_sessions[record.launcher_session_id] = _clone(record)

    def remove_launcher_session(self, launcher_session_id: str) -> None:
        self._launcher_sessions.pop(launcher_session_id, None)

    def hydrate(self, session_id: str) -> HydratedSession:
        record = self._require_session(session_id)
        return HydratedSession(
            summary=_clone(record.summary),
            snapshot=_clone(record.snapshot),
            applied_changes=_clone(record.applied_changes),
            pending_changes=_clone(record.pending_changes),
            sync_checkpoint=_clone(record.sync_checkpoint),
        )

    def write_incremental_change(self, session_id: str, change: PersistedChange) -> None:
        record = self._require_session(session_id)
        next_change = _clone(change)
        if next_change.status == "pending_sync":
            record.pending_changes = [
                entry for entry in record.pending_changes if entry.change_id != next_change.change_id
            ]
            record.pending_changes.append(next_change)
        else:
            record.pending_changes = [
                entry for entry in record.pending_changes if entry.change_id != next_change.change_id
            ]
            record.applied_changes.append(next_change)
        _apply_change_to_snapshot(record.snapshot, next_change)
        record.summary.last_modified_ms = _now_ms()
        self._emit(record, ("delta", _clone(next_change)))

    def replace_snapshot(
        self,
        session_id: str,
        snapshot: SessionSnapshot,
        _reason: str,
    ) -> None:
        record = self._require_session(session_id)
        record.snapshot = _clone(snapshot)
        if record.snapshot.session_id is None:
            record.snapshot.session_id = session_id
        record.applied_changes.clear()
        record.summary.last_modified_ms = _now_ms()
        if snapshot.snapshot_clock is not None:
            record.sync_checkpoint.last_snapshot_clock = _clone(snapshot.snapshot_clock)
        self._emit(
            record,
            ("snapshot_reset", _clone(record.snapshot), _clone(record.sync_checkpoint)),
        )

    def collapse(self, session_id: str) -> None:
        record = self._require_session(session_id)
        record.applied_changes.clear()
        record.summary.last_modified_ms = _now_ms()

    def remove_session(self, request: RemoveSessionRequest) -> None:
        self._sessions.pop(request.session_id, None)

    def subscribe(self, session_id: str, sink: Callable[[PersistenceEvent], None]) -> Callable[[], None]:
        record = self._require_session(session_id)
        record.subscribers.add(sink)

        def unsubscribe() -> None:
            record.subscribers.discard(sink)

        return unsubscribe

    def set_sharing_state(self, session_id: str, state: SharingState) -> None:
        record = self._require_session(session_id)
        record.sharing_state = state
        self._emit(record, ("sharing_state", session_id, state))

    def set_session_mode(self, session_id: str, mode: SessionMode) -> None:
        record = self._require_session(session_id)
        record.summary.mode = mode
        record.summary.last_modified_ms = _now_ms()

    def _require_session(self, session_id: str) -> _SessionRecord:
        record = self._sessions.get(session_id)
        if record is None:
            raise KeyError(f"unknown session: {session_id}")
        return record

    @staticmethod
    def _emit(record: _SessionRecord, event: PersistenceEvent) -> None:
        for sink in tuple(record.subscribers):
            sink(_clone(event))


class NullGripSessionLink(GripSessionLink):
    def attach(self, request: EnableSharingRequest) -> None:
        return None

    def detach(self, session_id: str) -> None:
        return None

    def publish_local_change(self, session_id: str, change: PersistedChange) -> None:
        return None


class InMemoryGripSessionPersistence(GripSessionPersistence):
    """Coordinator implementation built from an in-memory store and optional link."""

    def __init__(
        self,
        store: InMemoryGripSessionStore | None = None,
        link: GripSessionLink | None = None,
    ) -> None:
        self._store = store or InMemoryGripSessionStore()
        self._link = link or NullGripSessionLink()

    def new_session(self, request: NewSessionRequest) -> SessionSummary:
        return self._store.new_session(request)

    def list_sessions(self) -> list[SessionSummary]:
        return self._store.list_sessions()

    def get_session(self, session_id: str) -> SessionSummary | None:
        return self._store.get_session(session_id)

    def hydrate(self, session_id: str) -> HydratedSession:
        return self._store.hydrate(session_id)

    def subscribe(
        self,
        session_id: str,
        sink: Callable[[PersistenceEvent], None],
    ) -> Callable[[], None]:
        return self._store.subscribe(session_id, sink)

    def write_incremental_change(self, session_id: str, change: PersistedChange) -> None:
        self._store.write_incremental_change(session_id, change)
        if change.source == "local" and change.status == "pending_sync":
            self._link.publish_local_change(session_id, change)

    def replace_snapshot(self, session_id: str, snapshot: SessionSnapshot, reason: str) -> None:
        self._store.replace_snapshot(session_id, snapshot, reason)

    def collapse(self, session_id: str) -> None:
        self._store.collapse(session_id)

    def enable_sharing(self, request: EnableSharingRequest) -> None:
        self._store.set_session_mode(request.session_id, "shared")
        self._store.set_sharing_state(request.session_id, "attaching")
        self._link.attach(request)
        self._store.set_sharing_state(request.session_id, "live")

    def disable_sharing(self, session_id: str) -> None:
        self._link.detach(session_id)
        self._store.set_sharing_state(session_id, "detached")
        self._store.set_session_mode(session_id, "local")

    def remove_session(self, request: RemoveSessionRequest) -> None:
        if request.scope == "local_and_shared":
            self._link.detach(request.session_id)
        self._store.remove_session(request)
