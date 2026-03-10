"""FastAPI application factory for the Glial router."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .coordinator import InMemoryGlialCoordinator
from .models import (
    AttachSessionRequest,
    AttachSessionResponse,
    ReplayResponse,
    RemoteSessionLoadResponse,
    RemoteSessionSummaryModel,
    SubmitChangeRequest,
    SubmitChangeResponse,
    UpsertRemoteSessionRequest,
)


def create_app(coordinator: InMemoryGlialCoordinator | None = None) -> FastAPI:
    app = FastAPI(title="Glial Router")
    app.state.glial_coordinator = coordinator or InMemoryGlialCoordinator()

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
    def submit_change(session_id: str, request: SubmitChangeRequest) -> SubmitChangeResponse:
        try:
            return app.state.glial_coordinator.submit_change(session_id, request.change)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc

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

    return app
