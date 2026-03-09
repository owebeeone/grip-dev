"""Canonical persisted session types for Glial local-first storage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeAlias

SessionMode: TypeAlias = Literal["local", "shared"]
ChangeSource: TypeAlias = Literal["local", "glial", "hydrate", "collapse"]
ChangeStatus: TypeAlias = Literal["applied", "pending_sync", "confirmed", "superseded"]
PersistenceTargetKind: TypeAlias = Literal["context", "child-order", "drip", "tap-meta", "remove"]
TapExecutionMode: TypeAlias = Literal["replicated", "origin-primary", "negotiated-primary"]
TapExecutionRole: TypeAlias = Literal["primary", "follower"]
SharingState: TypeAlias = Literal["detached", "attaching", "live", "resyncing", "error"]


@dataclass(slots=True)
class VirtualClock:
    wall_time_ms: int
    logical_counter: int
    replica_id: str


@dataclass(slots=True)
class TapExport:
    tap_id: str
    tap_type: str
    mode: str
    role: str | None = None
    provides: list[str] = field(default_factory=list)
    home_param_grips: list[str] = field(default_factory=list)
    destination_param_grips: list[str] = field(default_factory=list)
    purpose: str | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None
    cache_state: dict[str, Any] | None = None


@dataclass(slots=True)
class DripState:
    grip_id: str
    name: str
    value: Any | None = None
    value_clock: VirtualClock | None = None
    purpose: str | None = None
    description: str | None = None
    taps: list[TapExport] = field(default_factory=list)


@dataclass(slots=True)
class ContextState:
    path: str
    name: str
    purpose: str | None = None
    description: str | None = None
    entry_clock: VirtualClock | None = None
    children: list[str] = field(default_factory=list)
    drips: dict[str, DripState] = field(default_factory=dict)


@dataclass(slots=True)
class SessionSnapshot:
    contexts: dict[str, ContextState] = field(default_factory=dict)
    session_id: str | None = None
    snapshot_clock: VirtualClock | None = None


@dataclass(slots=True)
class SessionSummary:
    session_id: str
    title: str | None
    mode: SessionMode
    last_modified_ms: int
    last_glial_session_clock: VirtualClock | None = None


@dataclass(slots=True)
class SyncCheckpoint:
    attached: bool
    last_applied_clock: VirtualClock | None = None
    last_snapshot_clock: VirtualClock | None = None
    last_snapshot_id: str | None = None


@dataclass(slots=True)
class PersistedChange:
    change_id: str
    session_id: str
    source: ChangeSource
    status: ChangeStatus
    target_kind: PersistenceTargetKind
    path: str
    origin_replica_id: str | None = None
    origin_mutation_seq: int | None = None
    origin_generation: int | None = None
    session_clock: VirtualClock | None = None
    grip_id: str | None = None
    tap_id: str | None = None
    payload: dict[str, Any] | None = None


@dataclass(slots=True)
class HydratedSession:
    summary: SessionSummary
    snapshot: SessionSnapshot
    applied_changes: list[PersistedChange]
    pending_changes: list[PersistedChange]
    sync_checkpoint: SyncCheckpoint


@dataclass(slots=True)
class NewSessionRequest:
    session_id: str | None = None
    title: str | None = None
    initial_snapshot: SessionSnapshot | None = None


@dataclass(slots=True)
class EnableSharingRequest:
    session_id: str
    mode: Literal["share_local_session"] = "share_local_session"


@dataclass(slots=True)
class RemoveSessionRequest:
    session_id: str
    scope: Literal["local_only", "local_and_shared"] = "local_only"


PersistenceEvent: TypeAlias = (
    tuple[Literal["delta"], PersistedChange]
    | tuple[Literal["snapshot_reset"], SessionSnapshot, SyncCheckpoint]
    | tuple[Literal["sharing_state"], str, SharingState]
)


class GripSessionPersistence(Protocol):
    def new_session(self, request: NewSessionRequest) -> SessionSummary: ...
    def list_sessions(self) -> list[SessionSummary]: ...
    def get_session(self, session_id: str) -> SessionSummary | None: ...
    def hydrate(self, session_id: str) -> HydratedSession: ...
    def subscribe(
        self,
        session_id: str,
        sink: Callable[[PersistenceEvent], None],
    ) -> Callable[[], None]: ...
    def write_incremental_change(self, session_id: str, change: PersistedChange) -> None: ...
    def replace_snapshot(
        self,
        session_id: str,
        snapshot: SessionSnapshot,
        reason: Literal["collapse", "glial_resync", "share_seed"],
    ) -> None: ...
    def collapse(self, session_id: str) -> None: ...
    def enable_sharing(self, request: EnableSharingRequest) -> None: ...
    def disable_sharing(self, session_id: str) -> None: ...
    def remove_session(self, request: RemoveSessionRequest) -> None: ...


class GripSessionStore(Protocol):
    def new_session(self, request: NewSessionRequest) -> SessionSummary: ...
    def list_sessions(self) -> list[SessionSummary]: ...
    def get_session(self, session_id: str) -> SessionSummary | None: ...
    def hydrate(self, session_id: str) -> HydratedSession: ...
    def write_incremental_change(self, session_id: str, change: PersistedChange) -> None: ...
    def replace_snapshot(
        self,
        session_id: str,
        snapshot: SessionSnapshot,
        reason: Literal["collapse", "glial_resync", "share_seed"],
    ) -> None: ...
    def collapse(self, session_id: str) -> None: ...
    def remove_session(self, request: RemoveSessionRequest) -> None: ...


class GripSessionLink(Protocol):
    def attach(self, request: EnableSharingRequest) -> None: ...
    def detach(self, session_id: str) -> None: ...
    def publish_local_change(self, session_id: str, change: PersistedChange) -> None: ...
