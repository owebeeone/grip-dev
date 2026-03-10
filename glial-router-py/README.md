# glial-router-py

FastAPI-based Glial coordination service for local testing and early integration.

This package currently provides:

- attach or seed session endpoint
- snapshot fetch endpoint
- change submit endpoint with authoritative session clocks
- replay endpoint for missed changes
- websocket live session endpoint for attach plus accepted-change fanout
- remote backup session catalog, load, save, and delete endpoints
- pluggable remote backup stores with in-memory and filesystem adapters
- optional serving of the built `grip-react-demo` bundle at `/demo/`

The live session coordinator is intentionally single-process for the first integration phase.

Remote backup storage is configurable through the coordinator. The package exports:

- `InMemoryGlialCoordinator`
- `InMemoryRemoteSessionStore`
- `FilesystemRemoteSessionStore`

Typical local-development usage:

```python
from glial_router import (
    FilesystemRemoteSessionStore,
    InMemoryGlialCoordinator,
    create_app,
)

store = FilesystemRemoteSessionStore("./.glial-router-store")
coordinator = InMemoryGlialCoordinator(remote_session_store=store)
app = create_app(coordinator)
```

The current scope is:

- authoritative session clock assignment
- HTTP snapshot or replay flows
- websocket live change fanout
- remote backup catalog and load/save/delete
- optional same-origin React demo hosting

It does not yet implement:

- multi-shard directory routing
- negotiated-primary lease coordination
- durable replay-log compaction beyond the in-memory live session state
