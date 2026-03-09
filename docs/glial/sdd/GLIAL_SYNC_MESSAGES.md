# Glial Snapshot And Resync Messages

This appendix defines a minimal first-pass message set for snapshot, replay, reconnect, and live delta streaming.

It assumes:

- Glial is the central coordination point
- messages may be lost, duplicated, or received out of order
- every synchronized delta carries a virtual clock
- drips and taps propagate that clock so stale updates can be elided locally as well as over the wire

## Virtual Clock

The exact clock implementation can still be refined, but messages need a comparable clock stamp.

```python
from typing import Any, Literal
from pydantic import BaseModel, Field


class VirtualClock(BaseModel):
    wall_time_ms: int
    logical_counter: int
    replica_id: str
```

Comparison is lexicographic by:

1. `wall_time_ms`
2. `logical_counter`
3. `replica_id`

## Delta Envelope

This is the common unit for replay and live streaming.

```python
class GraphDelta(BaseModel):
    delta_id: str
    session_id: str
    origin_replica_id: str
    origin_mutation_seq: int
    origin_generation: int | None = None
    clock: VirtualClock
    caused_by_clock: VirtualClock | None = None
    target_kind: Literal["context", "child-order", "drip", "tap-meta", "remove"]
    path: str
    grip_id: str | None = None
    tap_id: str | None = None
    payload: dict[str, Any] | None = None
```

Notes:

- `clock` is the authoritative ordering stamp for this delta
- `origin_mutation_seq` preserves local source order within one origin replica
- `origin_generation` preserves causal lineage for async or delayed outputs
- `caused_by_clock` is optional lineage for tap-driven updates
- `path` is the canonical context path
- exact `payload` shape depends on the graph export schema and can remain flexible for now

## Client Sync State

On reconnect, the replica tells Glial what it believes it has already applied.

```python
class SyncCursor(BaseModel):
    last_applied_clock: VirtualClock | None = None
    last_snapshot_clock: VirtualClock | None = None
    last_snapshot_id: str | None = None
```

`last_applied_clock` is the most important field.

## Snapshot Entry Requirement

Each snapshot entry must carry its own current entry clock.

For the first pass, treat snapshot content as:

```python
class SnapshotEntry(BaseModel):
    path: str
    entry_clock: VirtualClock
    payload: dict[str, Any]
```

The exact payload shape can still follow the later `ContextState` schema work.

## Client -> Glial Messages

### SyncHello

Sent on initial connect or reconnect.

```python
class SyncHello(BaseModel):
    kind: Literal["sync_hello"] = "sync_hello"
    message_id: str
    session_id: str
    replica_id: str
    sent_at_ms: int
    cursor: SyncCursor = Field(default_factory=SyncCursor)
```

This is the entry point for both first join and reconnect.

### SnapshotAck

Sent after the client has fully applied a snapshot.

```python
class SnapshotAck(BaseModel):
    kind: Literal["snapshot_ack"] = "snapshot_ack"
    message_id: str
    session_id: str
    replica_id: str
    snapshot_id: str
    applied_through_clock: VirtualClock
```

### ReplayAck

Sent after replay batches have been applied up to a certain point.

```python
class ReplayAck(BaseModel):
    kind: Literal["replay_ack"] = "replay_ack"
    message_id: str
    session_id: str
    replica_id: str
    replay_id: str
    applied_through_clock: VirtualClock
```

This can be omitted in a simpler first implementation, but it is useful if Glial wants positive confirmation before pruning replay state.

### LiveCursorUpdate

Optional periodic cursor update from the client during steady-state sync.

```python
class LiveCursorUpdate(BaseModel):
    kind: Literal["live_cursor_update"] = "live_cursor_update"
    message_id: str
    session_id: str
    replica_id: str
    last_applied_clock: VirtualClock
```

This helps the server know how far a replica has caught up.

### SyncError

Sent by the client when it detects local sync uncertainty and wants a full reset.

```python
class SyncError(BaseModel):
    kind: Literal["sync_error"] = "sync_error"
    message_id: str
    session_id: str
    replica_id: str
    reason: str
    last_applied_clock: VirtualClock | None = None
```

## Glial -> Client Messages

### SyncPlan

Glial tells the replica what sync path it will use.

```python
class SyncPlan(BaseModel):
    kind: Literal["sync_plan"] = "sync_plan"
    message_id: str
    session_id: str
    replica_id: str
    mode: Literal["snapshot_only", "replay_only", "snapshot_plus_replay"]
    plan_id: str
```

Typical use:

- first join: `snapshot_plus_replay`
- short reconnect: `replay_only`
- reconnect after compaction/gap: `snapshot_plus_replay`

### SnapshotBegin

Starts a snapshot transfer.

```python
class SnapshotBegin(BaseModel):
    kind: Literal["snapshot_begin"] = "snapshot_begin"
    message_id: str
    session_id: str
    replica_id: str
    plan_id: str
    snapshot_id: str
    snapshot_clock: VirtualClock
```

`snapshot_clock` means the snapshot is a materialized view of state through that clock boundary.

### SnapshotChunk

Transfers snapshot content in chunks.

```python
class SnapshotChunk(BaseModel):
    kind: Literal["snapshot_chunk"] = "snapshot_chunk"
    message_id: str
    session_id: str
    replica_id: str
    snapshot_id: str
    chunk_index: int
    is_final_chunk: bool = False
    entries: list[SnapshotEntry]
```

For now the exact `payload` inside each `SnapshotEntry` remains intentionally deferred.

### SnapshotEnd

Marks snapshot completion.

```python
class SnapshotEnd(BaseModel):
    kind: Literal["snapshot_end"] = "snapshot_end"
    message_id: str
    session_id: str
    replica_id: str
    snapshot_id: str
    snapshot_clock: VirtualClock
```

After `SnapshotEnd`, the client should have a complete materialized state through `snapshot_clock`.

### ReplayBegin

Starts replay of deltas newer than the replica's cursor or newer than a delivered snapshot.

```python
class ReplayBegin(BaseModel):
    kind: Literal["replay_begin"] = "replay_begin"
    message_id: str
    session_id: str
    replica_id: str
    plan_id: str
    replay_id: str
    from_exclusive_clock: VirtualClock | None = None
```

### DeltaBatch

Carries replay deltas or live deltas.

```python
class DeltaBatch(BaseModel):
    kind: Literal["delta_batch"] = "delta_batch"
    message_id: str
    session_id: str
    replica_id: str
    stream: Literal["replay", "live"]
    replay_id: str | None = None
    low_clock: VirtualClock | None = None
    high_clock: VirtualClock | None = None
    deltas: list[GraphDelta]
```

The same shape can be used for:

- replay after reconnect
- steady-state live sync

Even if batches arrive out of order, the client can still:

- dedupe by `delta_id`
- compare `clock`
- elide stale updates per target locally

### ReplayEnd

Marks completion of replay catch-up.

```python
class ReplayEnd(BaseModel):
    kind: Literal["replay_end"] = "replay_end"
    message_id: str
    session_id: str
    replica_id: str
    replay_id: str
    replayed_through_clock: VirtualClock | None = None
```

After `ReplayEnd`, the replica is considered caught up through `replayed_through_clock`.

### SyncReset

Sent when the server cannot honor the client cursor and requires a fresh snapshot.

```python
class SyncReset(BaseModel):
    kind: Literal["sync_reset"] = "sync_reset"
    message_id: str
    session_id: str
    replica_id: str
    reason: str
```

Reasons may include:

- `cursor_too_old`
- `snapshot_missing`
- `replay_window_pruned`
- `server_restart`

## Suggested Union

```python
SyncClientMessage = SyncHello | SnapshotAck | ReplayAck | LiveCursorUpdate | SyncError

SyncServerMessage = (
    SyncPlan
    | SnapshotBegin
    | SnapshotChunk
    | SnapshotEnd
    | ReplayBegin
    | DeltaBatch
    | ReplayEnd
    | SyncReset
)
```

## Minimal Flows

### First join

1. Client sends `SyncHello` with empty cursor
2. Glial sends `SyncPlan(mode="snapshot_plus_replay")`
3. Glial sends `SnapshotBegin`
4. Glial sends one or more `SnapshotChunk`
5. Glial sends `SnapshotEnd`
6. Client sends `SnapshotAck`
7. Glial sends `ReplayBegin`
8. Glial sends replay `DeltaBatch` messages newer than `snapshot_clock`
9. Glial sends `ReplayEnd`
10. Live `DeltaBatch(stream="live")` continues

### Short reconnect

1. Client sends `SyncHello(cursor=last_applied_clock)`
2. Glial decides replay window is available
3. Glial sends `SyncPlan(mode="replay_only")`
4. Glial sends `ReplayBegin(from_exclusive_clock=client.last_applied_clock)`
5. Glial sends replay `DeltaBatch` messages
6. Glial sends `ReplayEnd`
7. Live `DeltaBatch(stream="live")` continues

### Reconnect after gap/compaction

1. Client sends `SyncHello(cursor=last_applied_clock)`
2. Glial cannot safely replay from that cursor
3. Glial sends `SyncReset`
4. Glial sends `SyncPlan(mode="snapshot_plus_replay")`
5. Snapshot and replay proceed as for first join

### Client-detected sync uncertainty

1. Client detects a local sync uncertainty or apply error
2. Client sends `SyncError`
3. Glial sends `SyncReset`
4. Glial sends a fresh snapshot and replay as needed

## Runtime Rule

The client runtime should track the latest applied clock for each relevant target and use that to elide stale or duplicated deltas.

That same rule should apply whether the update came from:

- local tap/drip propagation
- replay after reconnect
- live sync from Glial
- snapshots rebuilding local state via `entry_clock`

## Remaining Open Details

This still leaves a few SDD-level choices open:

- replay window retention
- whether `ReplayAck` is required
- whether `SnapshotChunk` should carry hashes
- whether `DeltaBatch` should include sequence numbers in addition to clocks
- how much snapshot chunking should be transport-aware
