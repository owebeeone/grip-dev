"""HTTP client helpers for the initial Glial router protocol."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Protocol

import httpx

from glial_local.types import EnableSharingRequest, GripSessionLink, PersistedChange, VirtualClock


class ResponseLike(Protocol):
    status_code: int

    def json(self) -> Any: ...
    def raise_for_status(self) -> None: ...


class RequestClientLike(Protocol):
    def get(self, url: str, **kwargs: Any) -> ResponseLike: ...
    def post(self, url: str, **kwargs: Any) -> ResponseLike: ...
    def put(self, url: str, **kwargs: Any) -> ResponseLike: ...
    def delete(self, url: str, **kwargs: Any) -> ResponseLike: ...


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def _clock_from_json(data: dict[str, Any] | None) -> VirtualClock | None:
    if data is None:
        return None
    return VirtualClock(
        wall_time_ms=int(data["wall_time_ms"]),
        logical_counter=int(data["logical_counter"]),
        replica_id=str(data["replica_id"]),
    )


def _change_from_json(data: dict[str, Any]) -> PersistedChange:
    return PersistedChange(
        change_id=str(data["change_id"]),
        session_id=str(data["session_id"]),
        source=data["source"],
        status=data["status"],
        target_kind=data["target_kind"],
        path=str(data["path"]),
        origin_replica_id=data.get("origin_replica_id"),
        origin_mutation_seq=data.get("origin_mutation_seq"),
        origin_generation=data.get("origin_generation"),
        session_clock=_clock_from_json(data.get("session_clock")),
        grip_id=data.get("grip_id"),
        tap_id=data.get("tap_id"),
        payload=data.get("payload"),
    )


class HttpGlialClient:
    """Small HTTP client for the initial FastAPI-backed Glial router."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client: RequestClientLike | None = None,
    ) -> None:
        if client is None and base_url is None:
            raise ValueError("Either base_url or client must be provided")
        self._owned_client = httpx.Client(base_url=base_url or "") if client is None else None
        self._client = client or self._owned_client
        assert self._client is not None

    def close(self) -> None:
        if self._owned_client is not None:
            self._owned_client.close()

    def attach_session(self, session_id: str, snapshot: Any | None = None) -> dict[str, Any]:
        response = self._client.post(
            f"/sessions/{session_id}/attach",
            json={"snapshot": _to_jsonable(snapshot)},
        )
        response.raise_for_status()
        return response.json()

    def get_snapshot(self, session_id: str) -> dict[str, Any]:
        response = self._client.get(f"/sessions/{session_id}/snapshot")
        response.raise_for_status()
        return response.json()

    def submit_change(self, session_id: str, change: PersistedChange | dict[str, Any]) -> PersistedChange:
        response = self._client.post(
            f"/sessions/{session_id}/changes",
            json={"change": _to_jsonable(change)},
        )
        response.raise_for_status()
        body = response.json()
        return _change_from_json(body["accepted_change"])

    def replay(self, session_id: str, since_counter: int = 0) -> list[PersistedChange]:
        response = self._client.get(
            f"/sessions/{session_id}/replay",
            params={"since_counter": since_counter},
        )
        response.raise_for_status()
        body = response.json()
        return [_change_from_json(item) for item in body["changes"]]

    def list_remote_sessions(self, user_id: str) -> list[dict[str, Any]]:
        response = self._client.get("/remote-sessions", params={"user_id": user_id})
        response.raise_for_status()
        body = response.json()
        return list(body)

    def load_remote_session(self, user_id: str, session_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"/remote-sessions/{session_id}",
            params={"user_id": user_id},
        )
        response.raise_for_status()
        return response.json()

    def save_remote_session(
        self,
        user_id: str,
        session_id: str,
        snapshot: dict[str, Any],
        *,
        title: str | None = None,
    ) -> dict[str, Any]:
        response = self._client.put(
            f"/remote-sessions/{session_id}",
            params={"user_id": user_id},
            json={"title": title, "snapshot": _to_jsonable(snapshot)},
        )
        response.raise_for_status()
        return response.json()

    def delete_remote_session(self, user_id: str, session_id: str) -> bool:
        response = self._client.delete(
            f"/remote-sessions/{session_id}",
            params={"user_id": user_id},
        )
        response.raise_for_status()
        return True

    def load_shared_session(self, user_id: str, session_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"/shared-sessions/{session_id}",
            params={"user_id": user_id},
        )
        response.raise_for_status()
        return response.json()

    def save_shared_session(
        self,
        user_id: str,
        session_id: str,
        snapshot: dict[str, Any],
        *,
        title: str | None = None,
    ) -> dict[str, Any]:
        response = self._client.put(
            f"/shared-sessions/{session_id}",
            params={"user_id": user_id},
            json={"title": title, "snapshot": _to_jsonable(snapshot)},
        )
        response.raise_for_status()
        return response.json()

    def list_shared_contexts(self, user_id: str, session_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"/shared-sessions/{session_id}/contexts",
            params={"user_id": user_id},
        )
        response.raise_for_status()
        return response.json()

    def list_shared_taps(self, user_id: str, session_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"/shared-sessions/{session_id}/taps",
            params={"user_id": user_id},
        )
        response.raise_for_status()
        return response.json()

    def list_shared_leases(self, user_id: str, session_id: str) -> dict[str, Any]:
        response = self._client.get(
            f"/shared-sessions/{session_id}/leases",
            params={"user_id": user_id},
        )
        response.raise_for_status()
        return response.json()

    def request_tap_lease(
        self,
        user_id: str,
        session_id: str,
        tap_id: str,
        *,
        replica_id: str,
        priority: int = 0,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/shared-sessions/{session_id}/leases/{tap_id}",
            params={"user_id": user_id},
            json={"replica_id": replica_id, "priority": priority},
        )
        response.raise_for_status()
        return response.json()

    def release_tap_lease(
        self,
        user_id: str,
        session_id: str,
        tap_id: str,
        *,
        replica_id: str | None = None,
    ) -> bool:
        params: dict[str, Any] = {"user_id": user_id}
        if replica_id is not None:
            params["replica_id"] = replica_id
        response = self._client.delete(
            f"/shared-sessions/{session_id}/leases/{tap_id}",
            params=params,
        )
        response.raise_for_status()
        return True

    def update_shared_value(
        self,
        user_id: str,
        session_id: str,
        *,
        path: str,
        grip_id: str,
        value: Any,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/shared-sessions/{session_id}/values",
            params={"user_id": user_id},
            json={"path": path, "grip_id": grip_id, "value": _to_jsonable(value)},
        )
        response.raise_for_status()
        return response.json()


class HttpGripSessionLink(GripSessionLink):
    """`GripSessionLink` implementation backed by the Glial HTTP client."""

    def __init__(
        self,
        client: HttpGlialClient,
        *,
        snapshot_supplier: Callable[[str], Any | None] | None = None,
    ) -> None:
        self._client = client
        self._snapshot_supplier = snapshot_supplier
        self._last_accepted_change: PersistedChange | None = None

    @property
    def last_accepted_change(self) -> PersistedChange | None:
        return self._last_accepted_change

    def attach(self, request: EnableSharingRequest) -> None:
        snapshot = self._snapshot_supplier(request.session_id) if self._snapshot_supplier else None
        self._client.attach_session(request.session_id, snapshot)

    def detach(self, session_id: str) -> None:
        return None

    def publish_local_change(self, session_id: str, change: PersistedChange) -> None:
        self._last_accepted_change = self._client.submit_change(session_id, change)
