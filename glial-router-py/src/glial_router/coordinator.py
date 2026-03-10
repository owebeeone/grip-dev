"""In-memory Glial coordination logic for local tests and development."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any

from .models import (
    AttachSessionRequest,
    AttachSessionResponse,
    PersistedChangeModel,
    ReplayResponse,
    RemoteSessionLoadResponse,
    RemoteSessionSummaryModel,
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
