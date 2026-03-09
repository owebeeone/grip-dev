# Glial SDD Section 07: Snapshot Replay Resync

## Overview

Glial treats reconnect recovery as an application-level sync problem rather than assuming transport perfection.

The v1 recovery model is:

- first connect gets snapshot plus replay
- short reconnect attempts replay only
- if replay cannot be guaranteed, Glial sends a full resnapshot
- if the client detects sync uncertainty, it requests reset and Glial resends the full graph

## Local Browser Reload Without Glial

The default browser lifecycle does not require Glial.

For a local-only session:

- the browser persists the current session state to a local store, typically IndexedDB
- on reload, the browser restores from local snapshot and/or local replay data
- no Glial handshake, lease negotiation, or remote replay occurs

If the user later enables sharing, remote save, or headless participation, the runtime may attach the existing session to Glial and then begin using the Glial snapshot/replay flows defined below.

## Required Messages

Client-to-Glial:

- `SyncHello`
- `SnapshotAck`
- `SyncError`
- `ReplayAck` optional
- `LiveCursorUpdate` optional

Glial-to-client:

- `SyncPlan`
- `SnapshotBegin`
- `SnapshotChunk`
- `SnapshotEnd`
- `ReplayBegin`
- `DeltaBatch`
- `ReplayEnd`
- `SyncReset`

## Replay Window Defaults

V1 defaults:

- retain replay state for `5 minutes`
- or `10_000` deltas, whichever limit is reached first

If a reconnect cursor falls outside that window, Glial must fall back to a fresh snapshot.

## First Join Flow

1. Replica sends `SyncHello` with empty cursor
2. Glial replies with `SyncPlan(mode="snapshot_plus_replay")`
3. Glial sends `SnapshotBegin`
4. Glial sends one or more `SnapshotChunk` messages
5. Glial sends `SnapshotEnd`
6. Replica applies the snapshot and sends `SnapshotAck`
7. Glial sends `ReplayBegin`
8. Glial sends any replay deltas newer than the snapshot clock
9. Glial sends `ReplayEnd`
10. Live `DeltaBatch(stream="live")` continues

## Reconnect Flow

On reconnect, the replica sends `SyncHello` with:

- `last_applied_clock`
- `last_snapshot_clock`
- `last_snapshot_id`

Glial then decides:

- `replay_only` if the replay window safely covers the client cursor
- `snapshot_plus_replay` otherwise

V1 rule for local pending synchronized writes:

- a local synchronized mutation is speculative until the replica observes the echoed Glial delta carrying the authoritative clock
- on reconnect or `SyncReset`, the replica must not blindly replay a pre-disconnect pending mutation queue
- after snapshot/replay completes, the runtime may re-evaluate local intent and emit a new synchronized mutation against current state, or drop the stale local intent

This means v1 reconnect is authoritative-state recovery, not offline mutation queue replay.

## Sync Uncertainty Flow

If a client detects uncertainty, such as:

- missing prerequisite state
- inconsistent duplicate handling
- failed local apply
- uncertain ordering after local corruption

then the client sends `SyncError`.

Glial responds with:

- `SyncReset`
- followed by a fresh snapshot and replay as needed

V1 always chooses correctness over incremental repair complexity.

## Delete And Re-Add Sequencing

Delete and re-add are ordered by authoritative Glial clocks.

Rule:

- the later authoritative clock wins

There is no special delete stream in v1. Deletion is just another synchronized change with a later clock.

Because pre-resync local pending writes are not blindly replayed in v1, Glial does not yet require tombstones to protect against resurrection from a disconnected local queue.

## Snapshot Format

Snapshots are chunked for transport but logically represent one consistent view through `snapshot_clock`.

Each `SnapshotChunk` carries `SnapshotEntry` values:

- `path`
- `entry_clock`
- `payload`

Each `payload` corresponds to the snapshot `ContextState` schema defined in Section 05.

## Live Delta Flow

Once the replica is caught up:

- Glial sends live `DeltaBatch` messages
- replicas dedupe by `delta_id`
- replicas preserve or validate same-replica source order using `origin_mutation_seq`
- replicas compare entry clocks locally
- replicas drop stale or duplicate updates

For v1, separate per-delta acknowledgement is not required in steady state. The origin replica treats the echoed live delta containing the authoritative clock as confirmation that the mutation was accepted.

If Glial cannot safely preserve or reconstruct same-replica source order, it should choose `SyncReset` rather than guessing.

## Optional Cursor Updates

`LiveCursorUpdate` may be sent periodically so Glial knows how far a replica has caught up, but v1 correctness does not depend on it.

## Shard Recovery Interaction

If a shard is replaced:

- a new authoritative shard loads the latest durable snapshot and available replay state
- reconnecting clients resume through the same snapshot/replay rules
- if replay continuity cannot be guaranteed, Glial sends a full resnapshot
