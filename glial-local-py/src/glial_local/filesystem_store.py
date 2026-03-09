"""Filesystem-backed local session store."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from .in_memory import _apply_change_to_snapshot, _create_empty_snapshot, _now_ms
from .types import (
    ContextState,
    DripState,
    GripSessionStore,
    HydratedSession,
    NewSessionRequest,
    PersistedChange,
    RemoveSessionRequest,
    SessionSnapshot,
    SessionSummary,
    SyncCheckpoint,
    TapExport,
    VirtualClock,
)


def _clock_from_dict(data: dict | None) -> VirtualClock | None:
    if data is None:
        return None
    return VirtualClock(**data)


def _tap_from_dict(data: dict) -> TapExport:
    return TapExport(**data)


def _drip_from_dict(data: dict) -> DripState:
    return DripState(
        grip_id=data["grip_id"],
        name=data["name"],
        value=data.get("value"),
        value_clock=_clock_from_dict(data.get("value_clock")),
        purpose=data.get("purpose"),
        description=data.get("description"),
        taps=[_tap_from_dict(entry) for entry in data.get("taps", [])],
    )


def _context_from_dict(data: dict) -> ContextState:
    return ContextState(
        path=data["path"],
        name=data["name"],
        purpose=data.get("purpose"),
        description=data.get("description"),
        entry_clock=_clock_from_dict(data.get("entry_clock")),
        children=list(data.get("children", [])),
        drips={key: _drip_from_dict(value) for key, value in data.get("drips", {}).items()},
    )


def _snapshot_from_dict(data: dict) -> SessionSnapshot:
    return SessionSnapshot(
        session_id=data.get("session_id"),
        snapshot_clock=_clock_from_dict(data.get("snapshot_clock")),
        contexts={key: _context_from_dict(value) for key, value in data.get("contexts", {}).items()},
    )


def _summary_from_dict(data: dict) -> SessionSummary:
    return SessionSummary(
        session_id=data["session_id"],
        title=data.get("title"),
        mode=data["mode"],
        last_modified_ms=data["last_modified_ms"],
        last_glial_session_clock=_clock_from_dict(data.get("last_glial_session_clock")),
    )


def _change_from_dict(data: dict) -> PersistedChange:
    return PersistedChange(
        change_id=data["change_id"],
        session_id=data["session_id"],
        source=data["source"],
        status=data["status"],
        target_kind=data["target_kind"],
        path=data["path"],
        origin_replica_id=data.get("origin_replica_id"),
        origin_mutation_seq=data.get("origin_mutation_seq"),
        origin_generation=data.get("origin_generation"),
        session_clock=_clock_from_dict(data.get("session_clock")),
        grip_id=data.get("grip_id"),
        tap_id=data.get("tap_id"),
        payload=deepcopy(data.get("payload")),
    )


def _checkpoint_from_dict(data: dict) -> SyncCheckpoint:
    return SyncCheckpoint(
        attached=data["attached"],
        last_applied_clock=_clock_from_dict(data.get("last_applied_clock")),
        last_snapshot_clock=_clock_from_dict(data.get("last_snapshot_clock")),
        last_snapshot_id=data.get("last_snapshot_id"),
    )


class FilesystemGripSessionStore(GripSessionStore):
    """Simple JSON-file-backed session store."""

    def __init__(self, base_path: str | Path) -> None:
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

    def new_session(self, request: NewSessionRequest) -> SessionSummary:
        session_id = request.session_id or f"session_{_now_ms()}"
        summary = SessionSummary(
            session_id=session_id,
            title=request.title,
            mode="local",
            last_modified_ms=_now_ms(),
        )
        record = {
            "summary": asdict(summary),
            "snapshot": asdict(request.initial_snapshot or _create_empty_snapshot(session_id)),
            "applied_changes": [],
            "pending_changes": [],
            "sync_checkpoint": asdict(SyncCheckpoint(attached=False)),
        }
        self._write_record(session_id, record)
        return deepcopy(summary)

    def list_sessions(self) -> list[SessionSummary]:
        summaries: list[SessionSummary] = []
        for session_dir in self._base_path.iterdir():
            if not session_dir.is_dir():
                continue
            record = self._read_record(session_dir.name)
            summaries.append(_summary_from_dict(record["summary"]))
        return sorted(summaries, key=lambda entry: entry.last_modified_ms, reverse=True)

    def get_session(self, session_id: str) -> SessionSummary | None:
        record = self._read_record(session_id, required=False)
        if record is None:
            return None
        return _summary_from_dict(record["summary"])

    def hydrate(self, session_id: str) -> HydratedSession:
        record = self._read_record(session_id)
        return HydratedSession(
            summary=_summary_from_dict(record["summary"]),
            snapshot=_snapshot_from_dict(record["snapshot"]),
            applied_changes=[_change_from_dict(entry) for entry in record["applied_changes"]],
            pending_changes=[_change_from_dict(entry) for entry in record["pending_changes"]],
            sync_checkpoint=_checkpoint_from_dict(record["sync_checkpoint"]),
        )

    def write_incremental_change(self, session_id: str, change: PersistedChange) -> None:
        record = self._read_record(session_id)
        next_change = asdict(change)
        if change.status == "pending_sync":
            record["pending_changes"] = [
                entry for entry in record["pending_changes"] if entry["change_id"] != change.change_id
            ]
            record["pending_changes"].append(next_change)
        else:
            record["pending_changes"] = [
                entry for entry in record["pending_changes"] if entry["change_id"] != change.change_id
            ]
            record["applied_changes"].append(next_change)
        snapshot = _snapshot_from_dict(record["snapshot"])
        _apply_change_to_snapshot(snapshot, change)
        record["snapshot"] = asdict(snapshot)
        record["summary"]["last_modified_ms"] = _now_ms()
        self._write_record(session_id, record)

    def replace_snapshot(self, session_id: str, snapshot: SessionSnapshot, reason: str) -> None:
        record = self._read_record(session_id)
        record["snapshot"] = asdict(snapshot)
        record["applied_changes"] = []
        record["summary"]["last_modified_ms"] = _now_ms()
        if snapshot.snapshot_clock is not None:
            checkpoint = _checkpoint_from_dict(record["sync_checkpoint"])
            checkpoint.last_snapshot_clock = snapshot.snapshot_clock
            record["sync_checkpoint"] = asdict(checkpoint)
        self._write_record(session_id, record)

    def collapse(self, session_id: str) -> None:
        record = self._read_record(session_id)
        record["applied_changes"] = []
        record["summary"]["last_modified_ms"] = _now_ms()
        self._write_record(session_id, record)

    def remove_session(self, request: RemoveSessionRequest) -> None:
        session_dir = self._session_dir(request.session_id)
        if not session_dir.exists():
            return
        for child in session_dir.iterdir():
            child.unlink()
        session_dir.rmdir()

    def _record_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "session.json"

    def _session_dir(self, session_id: str) -> Path:
        return self._base_path / session_id

    def _read_record(self, session_id: str, required: bool = True) -> dict | None:
        path = self._record_path(session_id)
        if not path.exists():
            if required:
                raise KeyError(f"unknown session: {session_id}")
            return None
        return json.loads(path.read_text())

    def _write_record(self, session_id: str, record: dict) -> None:
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        self._record_path(session_id).write_text(json.dumps(record, indent=2, sort_keys=True))
