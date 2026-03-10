"""Launcher-session helpers for desktop and CLI clients."""

from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from .in_memory import _now_ms
from .types import (
    GripSessionStore,
    LauncherSessionKind,
    LauncherSessionRecord,
    LauncherSessionRecordStore,
    LauncherSessionStorageMode,
    NewSessionRequest,
    SessionSummary,
)


class GripSessionCatalog(GripSessionStore, LauncherSessionRecordStore, Protocol):
    """Combined session catalog used by local launcher helpers."""


def create_launcher_session_id(prefix: str = "launcher") -> str:
    return f"{prefix}_{_now_ms()}_{uuid4().hex[:8]}"


def ensure_launcher_session_record(
    store: GripSessionCatalog,
    launcher_session_id: str,
    *,
    title: str | None = None,
    storage_mode: LauncherSessionStorageMode = "local",
    session_kind: LauncherSessionKind = "local",
    glial_session_id: str | None = None,
) -> LauncherSessionRecord:
    existing = store.get_launcher_session(launcher_session_id)
    if existing is not None:
        return existing
    summary = (
        store.get_session(glial_session_id)
        if glial_session_id is not None
        else None
    ) or store.new_session(
        NewSessionRequest(session_id=glial_session_id, title=title)
    )
    record = LauncherSessionRecord(
        launcher_session_id=launcher_session_id,
        glial_session_id=summary.session_id,
        title=summary.title or title,
        storage_mode=storage_mode,
        session_kind=session_kind,
        last_opened_ms=_now_ms(),
    )
    store.put_launcher_session(record)
    return record


def bind_launcher_session_to_existing_session(
    store: GripSessionCatalog,
    launcher_session_id: str,
    session: SessionSummary,
    storage_mode: LauncherSessionStorageMode = "local",
    session_kind: LauncherSessionKind = "local",
) -> LauncherSessionRecord:
    record = LauncherSessionRecord(
        launcher_session_id=launcher_session_id,
        glial_session_id=session.session_id,
        title=session.title,
        storage_mode=storage_mode,
        session_kind=session_kind,
        last_opened_ms=_now_ms(),
    )
    store.put_launcher_session(record)
    return record
