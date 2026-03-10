"""FastAPI application factory for the Glial router."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse

from .coordinator import InMemoryGlialCoordinator
from .live_hub import SessionLiveHub
from .models import (
    AttachSessionRequest,
    AttachSessionResponse,
    LeaseRequest,
    LeaseResponse,
    ReplayResponse,
    RemoteSessionLoadResponse,
    RemoteSessionSummaryModel,
    SharedSessionLoadResponse,
    SharedValueUpdateRequest,
    SubmitChangeRequest,
    SubmitChangeResponse,
    UpsertRemoteSessionRequest,
    UpsertSharedSessionRequest,
    WebSocketAcceptedChangeEvent,
    WebSocketAttachRequest,
    WebSocketAttachedEvent,
    WebSocketSubmitChangeRequest,
)


def _default_react_demo_dist() -> Path | None:
    candidate = Path(__file__).resolve().parents[3] / "grip-react-demo" / "dist"
    if candidate.exists():
        return candidate
    return None


def _default_viewer_dist() -> Path | None:
    candidate = Path(__file__).resolve().parents[3] / "glial-viewer-ts" / "dist"
    if candidate.exists():
        return candidate
    return None


def create_app(
    coordinator: InMemoryGlialCoordinator | None = None,
    react_demo_dist: str | Path | None = None,
    viewer_dist: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Glial Router")
    app.state.glial_coordinator = coordinator or InMemoryGlialCoordinator()
    app.state.glial_live_hub = SessionLiveHub()
    app.state.react_demo_dist = (
        Path(react_demo_dist) if react_demo_dist is not None else _default_react_demo_dist()
    )
    app.state.viewer_dist = Path(viewer_dist) if viewer_dist is not None else _default_viewer_dist()

    @app.get("/", include_in_schema=False)
    def root_redirect():
        if app.state.react_demo_dist is not None:
            return RedirectResponse(url="/demo/", status_code=307)
        return {"service": "glial-router", "demo": "not configured"}

    @app.get("/demo", include_in_schema=False)
    @app.get("/demo/{asset_path:path}", include_in_schema=False)
    def react_demo(asset_path: str = ""):
        dist_path: Path | None = app.state.react_demo_dist
        if dist_path is None or not dist_path.exists():
            raise HTTPException(status_code=404, detail="react demo bundle is not available")
        if asset_path:
            requested = (dist_path / asset_path).resolve()
            if requested.is_file() and dist_path in requested.parents:
                return FileResponse(requested)
        index_path = dist_path / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="react demo bundle is not available")
        return FileResponse(index_path)

    @app.get("/viewer", include_in_schema=False)
    @app.get("/viewer/{asset_path:path}", include_in_schema=False)
    def react_viewer(asset_path: str = ""):
        dist_path: Path | None = app.state.viewer_dist
        if dist_path is None or not dist_path.exists():
            raise HTTPException(status_code=404, detail="react viewer bundle is not available")
        if asset_path:
            requested = (dist_path / asset_path).resolve()
            if requested.is_file() and dist_path in requested.parents:
                return FileResponse(requested)
        index_path = dist_path / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="react viewer bundle is not available")
        return FileResponse(index_path)

    @app.post("/sessions/{session_id}/attach", response_model=AttachSessionResponse)
    def attach_session(session_id: str, request: AttachSessionRequest) -> AttachSessionResponse:
        return app.state.glial_coordinator.attach(session_id, request)

    @app.get("/sessions/{session_id}/snapshot", response_model=AttachSessionResponse)
    def get_snapshot(session_id: str) -> AttachSessionResponse:
        try:
            return app.state.glial_coordinator.get_snapshot(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc

    @app.post("/sessions/{session_id}/changes", response_model=SubmitChangeResponse)
    async def submit_change(session_id: str, request: SubmitChangeRequest) -> SubmitChangeResponse:
        try:
            response = app.state.glial_coordinator.submit_change(session_id, request.change)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        await app.state.glial_live_hub.broadcast(
            session_id,
            WebSocketAcceptedChangeEvent(change=response.accepted_change).model_dump(mode="json"),
        )
        return response

    @app.get("/sessions/{session_id}/replay", response_model=ReplayResponse)
    def replay(session_id: str, since_counter: int = 0) -> ReplayResponse:
        try:
            return app.state.glial_coordinator.replay(session_id, since_counter)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc

    @app.get("/remote-sessions", response_model=list[RemoteSessionSummaryModel])
    def list_remote_sessions(user_id: str) -> list[RemoteSessionSummaryModel]:
        return app.state.glial_coordinator.list_remote_sessions(user_id)

    @app.get("/remote-sessions/{session_id}", response_model=RemoteSessionLoadResponse)
    def get_remote_session(session_id: str, user_id: str) -> RemoteSessionLoadResponse:
        try:
            return app.state.glial_coordinator.get_remote_session(user_id, session_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"unknown remote session: {user_id}:{session_id}",
            ) from exc

    @app.put("/remote-sessions/{session_id}", response_model=RemoteSessionLoadResponse)
    def put_remote_session(
        session_id: str,
        user_id: str,
        request: UpsertRemoteSessionRequest,
    ) -> RemoteSessionLoadResponse:
        return app.state.glial_coordinator.save_remote_session(user_id, session_id, request)

    @app.delete("/remote-sessions/{session_id}", status_code=204)
    def delete_remote_session(session_id: str, user_id: str) -> None:
        deleted = app.state.glial_coordinator.delete_remote_session(user_id, session_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"unknown remote session: {user_id}:{session_id}",
            )

    @app.get("/shared-sessions/{session_id}", response_model=SharedSessionLoadResponse)
    def get_shared_session(session_id: str, user_id: str) -> SharedSessionLoadResponse:
        try:
            return app.state.glial_coordinator.get_shared_session(user_id, session_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"unknown shared session: {user_id}:{session_id}",
            ) from exc

    @app.put("/shared-sessions/{session_id}", response_model=SharedSessionLoadResponse)
    def put_shared_session(
        session_id: str,
        user_id: str,
        request: UpsertSharedSessionRequest,
    ) -> SharedSessionLoadResponse:
        return app.state.glial_coordinator.save_shared_session(
            user_id,
            session_id,
            snapshot=request.snapshot,
            title=request.title,
        )

    @app.get("/shared-sessions/{session_id}/contexts")
    def get_shared_contexts(session_id: str, user_id: str) -> dict:
        try:
            shared = app.state.glial_coordinator.get_shared_session(user_id, session_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"unknown shared session: {user_id}:{session_id}",
            ) from exc
        return shared.snapshot.get("contexts", {})

    @app.get("/shared-sessions/{session_id}/taps")
    def get_shared_taps(session_id: str, user_id: str) -> dict:
        try:
            shared = app.state.glial_coordinator.get_shared_session(user_id, session_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"unknown shared session: {user_id}:{session_id}",
            ) from exc
        return shared.snapshot.get("taps", {})

    @app.get("/shared-sessions/{session_id}/leases")
    def get_shared_leases(session_id: str, user_id: str) -> dict:
        try:
            shared = app.state.glial_coordinator.get_shared_session(user_id, session_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"unknown shared session: {user_id}:{session_id}",
            ) from exc
        return shared.leases

    @app.post("/shared-sessions/{session_id}/leases/{tap_id}", response_model=LeaseResponse)
    def request_shared_lease(
        session_id: str,
        tap_id: str,
        user_id: str,
        request: LeaseRequest,
    ) -> LeaseResponse:
        return app.state.glial_coordinator.request_tap_lease(
            user_id,
            session_id,
            tap_id,
            replica_id=request.replica_id,
            priority=request.priority,
        )

    @app.delete("/shared-sessions/{session_id}/leases/{tap_id}", status_code=204)
    def release_shared_lease(
        session_id: str,
        tap_id: str,
        user_id: str,
        replica_id: str | None = None,
    ) -> None:
        deleted = app.state.glial_coordinator.release_tap_lease(
            user_id,
            session_id,
            tap_id,
            replica_id=replica_id,
        )
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"unknown shared lease: {user_id}:{session_id}:{tap_id}",
            )

    @app.post("/shared-sessions/{session_id}/values", response_model=SharedSessionLoadResponse)
    def update_shared_value(
        session_id: str,
        user_id: str,
        request: SharedValueUpdateRequest,
    ) -> SharedSessionLoadResponse:
        return app.state.glial_coordinator.update_shared_value(
            user_id,
            session_id,
            path=request.path,
            grip_id=request.grip_id,
            value=request.value,
        )

    @app.websocket("/sessions/{session_id}/ws")
    async def session_websocket(session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        replica_id: str | None = None
        try:
            attach_message = WebSocketAttachRequest.model_validate(await websocket.receive_json())
            replica_id = attach_message.replica_id
            attached = app.state.glial_coordinator.attach(
                session_id,
                AttachSessionRequest(snapshot=attach_message.snapshot),
            )
            await app.state.glial_live_hub.register(session_id, replica_id, websocket)
            await websocket.send_json(
                WebSocketAttachedEvent(
                    session_id=attached.session_id,
                    snapshot=attached.snapshot,
                    last_clock=attached.last_clock,
                ).model_dump(mode="json")
            )

            while True:
                raw_message = await websocket.receive_json()
                message_type = raw_message.get("type")
                if message_type != "submit_change":
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"unsupported websocket message type: {message_type}",
                        }
                    )
                    continue
                message = WebSocketSubmitChangeRequest.model_validate(raw_message)
                accepted = app.state.glial_coordinator.submit_change(session_id, message.change)
                await app.state.glial_live_hub.broadcast(
                    session_id,
                    WebSocketAcceptedChangeEvent(change=accepted.accepted_change).model_dump(
                        mode="json"
                    ),
                )
        except WebSocketDisconnect:
            pass
        finally:
            if replica_id is not None:
                await app.state.glial_live_hub.unregister(session_id, replica_id)

    return app
