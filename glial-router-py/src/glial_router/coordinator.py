"""In-memory Glial coordination logic for local tests and development."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any

from .models import (
    AttachSessionRequest,
    AttachSessionResponse,
    LeaseResponse,
    PersistedChangeModel,
    ReplayResponse,
    RemoteSessionLoadResponse,
    RemoteSessionSummaryModel,
    SharedSessionLoadResponse,
    SubmitChangeResponse,
    UpsertRemoteSessionRequest,
    VirtualClockModel,
)
from .remote_store import InMemoryRemoteSessionStore, RemoteSessionRecord, RemoteSessionStore


def _now_ms() -> int:
    return int(time() * 1000)


def _clone(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_clone(item) for item in value]
    if isinstance(value, dict):
        return {key: _clone(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return value.__class__.model_validate(value.model_dump())
    return value


def _apply_change(snapshot: dict[str, Any], change: PersistedChangeModel) -> None:
    contexts = snapshot.setdefault("contexts", {})
    path = change.path

    if change.target_kind == "context":
        if change.payload is not None:
            payload = _clone(change.payload)
            payload["path"] = path
            contexts[path] = payload
        return

    if change.target_kind == "child-order":
        context = contexts.get(path)
        if context is None:
            return
        context["children"] = list((change.payload or {}).get("children", []))
        return

    if change.target_kind == "drip":
        context = contexts.get(path)
        if context is None or change.grip_id is None:
            return
        drips = context.setdefault("drips", {})
        payload = _clone(change.payload or {})
        payload["grip_id"] = change.grip_id
        payload.setdefault("name", change.grip_id)
        payload.setdefault("taps", [])
        drips[change.grip_id] = payload
        return

    if change.target_kind == "tap-meta":
        context = contexts.get(path)
        if context is None or change.grip_id is None:
            return
        drip = context.get("drips", {}).get(change.grip_id)
        if drip is None:
            return
        drip["taps"] = _clone((change.payload or {}).get("taps", []))
        return

    if change.target_kind == "remove":
        if change.grip_id is None:
            contexts.pop(path, None)
            return
        context = contexts.get(path)
        if context is not None:
            context.get("drips", {}).pop(change.grip_id, None)


def _ensure_context(snapshot: dict[str, Any], path: str) -> dict[str, Any]:
    contexts = snapshot.setdefault("contexts", {})
    context = contexts.get(path)
    if context is None:
        name = path.rsplit("/", 1)[-1]
        context = {"path": path, "name": name, "children": [], "drips": {}}
        contexts[path] = context
    context.setdefault("path", path)
    context.setdefault("name", path.rsplit("/", 1)[-1])
    context.setdefault("children", [])
    context.setdefault("drips", {})
    return context


def _set_shared_value(snapshot: dict[str, Any], *, path: str, grip_id: str, value: Any) -> None:
    context = _ensure_context(snapshot, path)
    drips = context.setdefault("drips", {})
    drip = drips.get(grip_id)
    if drip is None:
        name = grip_id.split(":", 1)[-1]
        drip = {"grip_id": grip_id, "name": name, "taps": []}
        drips[grip_id] = drip
    drip["grip_id"] = grip_id
    drip.setdefault("name", grip_id.split(":", 1)[-1])
    drip.setdefault("taps", [])
    drip["value"] = _clone(value)


@dataclass(slots=True)
class _SessionState:
    session_id: str
    snapshot: dict[str, Any]
    logical_counter: int = 0
    changes: list[PersistedChangeModel] = field(default_factory=list)

    def next_clock(self) -> VirtualClockModel:
        self.logical_counter += 1
        return VirtualClockModel(
            wall_time_ms=_now_ms(),
            logical_counter=self.logical_counter,
            replica_id="glial",
        )

    def last_clock(self) -> VirtualClockModel:
        return VirtualClockModel(
            wall_time_ms=_now_ms(),
            logical_counter=self.logical_counter,
            replica_id="glial",
        )


class InMemoryGlialCoordinator:
    """Minimal authoritative session coordinator with attach, change, and replay flows."""

    def __init__(self, remote_session_store: RemoteSessionStore | None = None) -> None:
        self._sessions: dict[str, _SessionState] = {}
        self._remote_session_store = remote_session_store or InMemoryRemoteSessionStore()

    def attach(self, session_id: str, request: AttachSessionRequest) -> AttachSessionResponse:
        session = self._sessions.get(session_id)
        if session is None:
            session = _SessionState(
                session_id=session_id,
                snapshot=(
                    _clone(request.snapshot)
                    if request.snapshot is not None
                    else {"session_id": session_id, "contexts": {}}
                ),
            )
            self._sessions[session_id] = session
        elif request.snapshot is not None and not session.snapshot.get("contexts"):
            session.snapshot = _clone(request.snapshot)
        return AttachSessionResponse(
            session_id=session_id,
            snapshot=_clone(session.snapshot),
            last_clock=session.last_clock(),
        )

    def get_snapshot(self, session_id: str) -> AttachSessionResponse:
        session = self._require_session(session_id)
        return AttachSessionResponse(
            session_id=session_id,
            snapshot=_clone(session.snapshot),
            last_clock=session.last_clock(),
        )

    def submit_change(self, session_id: str, change: PersistedChangeModel) -> SubmitChangeResponse:
        session = self._require_session(session_id)
        accepted = change.model_copy(deep=True)
        accepted.session_clock = session.next_clock()
        _apply_change(session.snapshot, accepted)
        session.changes.append(accepted)
        return SubmitChangeResponse(accepted_change=accepted)

    def replay(self, session_id: str, since_counter: int = 0) -> ReplayResponse:
        session = self._require_session(session_id)
        changes = [
            change.model_copy(deep=True)
            for change in session.changes
            if (change.session_clock.logical_counter if change.session_clock is not None else 0)
            > since_counter
        ]
        return ReplayResponse(
            session_id=session_id,
            changes=changes,
            last_clock=session.last_clock(),
        )

    def list_remote_sessions(self, user_id: str) -> list[RemoteSessionSummaryModel]:
        return [
            RemoteSessionSummaryModel(
                session_id=session.session_id,
                title=session.title,
                last_modified_ms=session.last_modified_ms,
            )
            for session in sorted(
                self._remote_session_store.list_sessions(user_id),
                key=lambda session: session.last_modified_ms,
                reverse=True,
            )
        ]

    def get_remote_session(self, user_id: str, session_id: str) -> RemoteSessionLoadResponse:
        session = self._require_remote_session(user_id, session_id)
        return RemoteSessionLoadResponse(
            session_id=session.session_id,
            title=session.title,
            snapshot=_clone(session.snapshot),
            last_modified_ms=session.last_modified_ms,
        )

    def save_remote_session(
        self,
        user_id: str,
        session_id: str,
        request: UpsertRemoteSessionRequest,
    ) -> RemoteSessionLoadResponse:
        session = self._remote_session_store.upsert_session(
            user_id,
            session_id,
            snapshot=request.snapshot,
            title=request.title,
        )
        return RemoteSessionLoadResponse(
            session_id=session.session_id,
            title=session.title,
            snapshot=_clone(session.snapshot),
            last_modified_ms=session.last_modified_ms,
        )

    def get_shared_session(self, user_id: str, session_id: str) -> SharedSessionLoadResponse:
        session = self._require_remote_session(user_id, session_id)
        return SharedSessionLoadResponse(
            session_id=session.session_id,
            title=session.title,
            snapshot=_clone(session.shared_snapshot or {"session_id": session_id, "contexts": {}, "taps": {}}),
            leases=_clone(session.leases),
            last_modified_ms=session.last_modified_ms,
        )

    def save_shared_session(
        self,
        user_id: str,
        session_id: str,
        *,
        snapshot: dict[str, Any],
        title: str | None = None,
    ) -> SharedSessionLoadResponse:
        session = self._remote_session_store.upsert_shared_snapshot(
            user_id,
            session_id,
            shared_snapshot=snapshot,
            title=title,
        )
        return SharedSessionLoadResponse(
            session_id=session.session_id,
            title=session.title,
            snapshot=_clone(session.shared_snapshot or {}),
            leases=_clone(session.leases),
            last_modified_ms=session.last_modified_ms,
        )

    def request_tap_lease(
        self,
        user_id: str,
        session_id: str,
        tap_id: str,
        *,
        replica_id: str,
        priority: int,
    ) -> LeaseResponse:
        session = self._remote_session_store.get_session(user_id, session_id)
        current_leases = _clone(session.leases) if session is not None else {}
        existing = current_leases.get(tap_id)
        granted = False
        if existing is None:
            granted = True
        else:
            current_priority = int(existing.get("priority", 0))
            current_replica_id = str(existing.get("primary_replica_id", ""))
            if priority > current_priority:
                granted = True
            elif priority == current_priority and current_replica_id == replica_id:
                granted = True
        if granted:
            current_leases[tap_id] = {
                "tap_id": tap_id,
                "primary_replica_id": replica_id,
                "priority": priority,
                "granted_ms": _now_ms(),
            }
            stored = self._remote_session_store.update_leases(user_id, session_id, current_leases)
            lease = stored.leases[tap_id]
            return LeaseResponse(**lease, granted=True)
        assert existing is not None
        return LeaseResponse(
            tap_id=tap_id,
            primary_replica_id=str(existing["primary_replica_id"]),
            priority=int(existing["priority"]),
            granted_ms=int(existing["granted_ms"]),
            granted=False,
        )

    def release_tap_lease(
        self,
        user_id: str,
        session_id: str,
        tap_id: str,
        *,
        replica_id: str | None = None,
    ) -> bool:
        session = self._remote_session_store.get_session(user_id, session_id)
        if session is None:
            return False
        current_leases = _clone(session.leases)
        existing = current_leases.get(tap_id)
        if existing is None:
            return False
        if replica_id is not None and existing.get("primary_replica_id") != replica_id:
            return False
        current_leases.pop(tap_id, None)
        self._remote_session_store.update_leases(user_id, session_id, current_leases)
        return True

    def update_shared_value(
        self,
        user_id: str,
        session_id: str,
        *,
        path: str,
        grip_id: str,
        value: Any,
    ) -> SharedSessionLoadResponse:
        session = self._require_remote_session(user_id, session_id)
        shared_snapshot = _clone(
            session.shared_snapshot or {"session_id": session_id, "contexts": {}, "taps": {}}
        )
        _set_shared_value(shared_snapshot, path=path, grip_id=grip_id, value=value)
        self._remote_session_store.upsert_shared_snapshot(
            user_id,
            session_id,
            shared_snapshot=shared_snapshot,
            title=session.title,
        )

        source_snapshot = _clone(session.snapshot)
        if source_snapshot:
            _set_shared_value(source_snapshot, path=path, grip_id=grip_id, value=value)
            self._remote_session_store.upsert_session(
                user_id,
                session_id,
                snapshot=source_snapshot,
                title=session.title,
            )

        refreshed = self._require_remote_session(user_id, session_id)
        return SharedSessionLoadResponse(
            session_id=refreshed.session_id,
            title=refreshed.title,
            snapshot=_clone(
                refreshed.shared_snapshot
                or {"session_id": session_id, "contexts": {}, "taps": {}}
            ),
            leases=_clone(refreshed.leases),
            last_modified_ms=refreshed.last_modified_ms,
        )

    def delete_remote_session(self, user_id: str, session_id: str) -> bool:
        return self._remote_session_store.delete_session(user_id, session_id)

    def _require_session(self, session_id: str) -> _SessionState:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    def _require_remote_session(self, user_id: str, session_id: str) -> RemoteSessionRecord:
        session = self._remote_session_store.get_session(user_id, session_id)
        if session is None:
            raise KeyError(f"{user_id}:{session_id}")
        return session
