"""Remote backup session storage adapters for the Glial router."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from time import time
from typing import Any, Protocol


def _now_ms() -> int:
    return int(time() * 1000)


def _clone(value: Any) -> Any:
    return deepcopy(value)


@dataclass(slots=True)
class RemoteSessionRecord:
    user_id: str
    session_id: str
    snapshot: dict[str, Any]
    title: str | None = None
    last_modified_ms: int = field(default_factory=_now_ms)


class RemoteSessionStore(Protocol):
    def list_sessions(self, user_id: str) -> list[RemoteSessionRecord]: ...
    def get_session(self, user_id: str, session_id: str) -> RemoteSessionRecord | None: ...
    def upsert_session(
        self,
        user_id: str,
        session_id: str,
        *,
        snapshot: dict[str, Any],
        title: str | None = None,
    ) -> RemoteSessionRecord: ...
    def delete_session(self, user_id: str, session_id: str) -> bool: ...


class InMemoryRemoteSessionStore:
    """In-memory remote backup store keyed by user id and logical session id."""

    def __init__(self) -> None:
        self._sessions_by_user: dict[str, dict[str, RemoteSessionRecord]] = {}

    def list_sessions(self, user_id: str) -> list[RemoteSessionRecord]:
        sessions = self._sessions_by_user.get(user_id, {})
        return sorted(
            (_clone(record) for record in sessions.values()),
            key=lambda record: record.last_modified_ms,
            reverse=True,
        )

    def get_session(self, user_id: str, session_id: str) -> RemoteSessionRecord | None:
        record = self._sessions_by_user.get(user_id, {}).get(session_id)
        return _clone(record) if record is not None else None

    def upsert_session(
        self,
        user_id: str,
        session_id: str,
        *,
        snapshot: dict[str, Any],
        title: str | None = None,
    ) -> RemoteSessionRecord:
        sessions = self._sessions_by_user.setdefault(user_id, {})
        record = sessions.get(session_id)
        if record is None:
            record = RemoteSessionRecord(user_id=user_id, session_id=session_id, snapshot={})
            sessions[session_id] = record
        record.snapshot = _clone(snapshot)
        record.title = title
        record.last_modified_ms = _now_ms()
        return _clone(record)

    def delete_session(self, user_id: str, session_id: str) -> bool:
        sessions = self._sessions_by_user.get(user_id)
        if sessions is None or session_id not in sessions:
            return False
        del sessions[session_id]
        if not sessions:
            self._sessions_by_user.pop(user_id, None)
        return True


class FilesystemRemoteSessionStore:
    """Filesystem-backed remote backup store for local development and tests."""

    def __init__(self, base_path: str | Path) -> None:
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def list_sessions(self, user_id: str) -> list[RemoteSessionRecord]:
        user_dir = self._user_dir(user_id)
        if not user_dir.exists():
            return []
        with self._lock:
            paths = tuple(user_dir.glob("*.json"))
        records = [self._read_record(path) for path in paths]
        return sorted(records, key=lambda record: record.last_modified_ms, reverse=True)

    def get_session(self, user_id: str, session_id: str) -> RemoteSessionRecord | None:
        path = self._record_path(user_id, session_id)
        if not path.exists():
            return None
        return self._read_record(path)

    def upsert_session(
        self,
        user_id: str,
        session_id: str,
        *,
        snapshot: dict[str, Any],
        title: str | None = None,
    ) -> RemoteSessionRecord:
        existing = self.get_session(user_id, session_id)
        record = RemoteSessionRecord(
            user_id=user_id,
            session_id=session_id,
            snapshot=_clone(snapshot),
            title=title,
            last_modified_ms=_now_ms() if existing is None else _now_ms(),
        )
        self._write_record(record)
        return record

    def delete_session(self, user_id: str, session_id: str) -> bool:
        path = self._record_path(user_id, session_id)
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
            user_dir = path.parent
            if user_dir.exists() and not any(user_dir.iterdir()):
                user_dir.rmdir()
        return True

    def _user_dir(self, user_id: str) -> Path:
        return self._base_path / user_id

    def _record_path(self, user_id: str, session_id: str) -> Path:
        return self._user_dir(user_id) / f"{session_id}.json"

    def _read_record(self, path: Path) -> RemoteSessionRecord:
        with self._lock:
            payload = json.loads(path.read_text())
        return RemoteSessionRecord(
            user_id=payload["user_id"],
            session_id=payload["session_id"],
            snapshot=payload["snapshot"],
            title=payload.get("title"),
            last_modified_ms=int(payload["last_modified_ms"]),
        )

    def _write_record(self, record: RemoteSessionRecord) -> None:
        payload = {
            "user_id": record.user_id,
            "session_id": record.session_id,
            "snapshot": _clone(record.snapshot),
            "title": record.title,
            "last_modified_ms": record.last_modified_ms,
        }
        path = self._record_path(record.user_id, record.session_id)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(
                dir=path.parent,
                prefix=f"{path.name}.",
                suffix=".tmp",
                text=True,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
                    json.dump(payload, temp_file, indent=2, sort_keys=True)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())
                os.replace(temp_name, path)
            finally:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
