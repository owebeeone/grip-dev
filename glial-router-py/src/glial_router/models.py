"""Pydantic models for the initial Glial HTTP coordination API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VirtualClockModel(BaseModel):
    wall_time_ms: int
    logical_counter: int
    replica_id: str


class PersistedChangeModel(BaseModel):
    change_id: str
    session_id: str
    source: str
    status: str
    target_kind: str
    path: str
    origin_replica_id: str | None = None
    origin_mutation_seq: int | None = None
    origin_generation: int | None = None
    session_clock: VirtualClockModel | None = None
    grip_id: str | None = None
    tap_id: str | None = None
    payload: dict[str, Any] | None = None


class AttachSessionRequest(BaseModel):
    snapshot: dict[str, Any] | None = None


class AttachSessionResponse(BaseModel):
    session_id: str
    snapshot: dict[str, Any]
    last_clock: VirtualClockModel


class SubmitChangeRequest(BaseModel):
    change: PersistedChangeModel


class SubmitChangeResponse(BaseModel):
    accepted_change: PersistedChangeModel


class ReplayResponse(BaseModel):
    session_id: str
    changes: list[PersistedChangeModel] = Field(default_factory=list)
    last_clock: VirtualClockModel


class RemoteSessionSummaryModel(BaseModel):
    session_id: str
    title: str | None = None
    last_modified_ms: int


class RemoteSessionLoadResponse(BaseModel):
    session_id: str
    title: str | None = None
    snapshot: dict[str, Any]
    last_modified_ms: int


class UpsertRemoteSessionRequest(BaseModel):
    title: str | None = None
    snapshot: dict[str, Any]
