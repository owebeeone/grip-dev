# Glial SDD Section 14: Session Persistence Interface

## Overview

Grip runtimes need one engine-facing persistence contract.

The runtime must not depend directly on:

- IndexedDB details
- filesystem layout details
- Glial transport or message sequencing details

The persistence layer is not just a value bag.

It owns the canonical persisted session model, including:

- session and checkpoint metadata
- canonical paths and grip identifiers
- normalized snapshot and delta shapes
- local sequence metadata such as `origin_generation` and `origin_mutation_seq`
- authoritative Glial session clocks when a session is shared

In the normalized v1 payloads shown below, the field name may remain `session_id`.

Semantically that `session_id` is the logical `glial_session_id` described in Section 04.

V1 therefore defines one interface family:

- `GripSessionPersistence`: engine-facing coordinator interface
- `GripSessionStore`: mandatory durable local store
- `GripSessionLink`: optional live shared-session link, normally Glial
- `GripProjector`: runtime projection attachment used to observe and/or apply session state

This means:

- local-only browser persistence uses a local store and no link
- local-only Python persistence uses a local store and no link
- a shared session uses the same local store plus a Glial link
- the runtime may attach multiple projectors at once, for example local backup plus live shared projection

The browser also owns a separate browser-local session record.

That browser-local record maps:

- `browser_session_id`
- `glial_session_id`
- storage policy such as local, remote, or both
- whether the session should attach to Glial routing on load

Glial is not the only persistence implementation.

The local durable store remains mandatory even when Glial is attached.

## Why Store And Link Are Separate

The local store and the shared link solve different problems.

The store is responsible for:

- local session catalog
- durable session metadata
- local snapshot and incremental journal
- collapse or compaction
- restore after reload or process restart

The link is responsible for:

- attaching a local session to a shared session
- publishing local shared mutations
- receiving remote snapshots, replay, and live deltas
- maintaining Glial sync status

Trying to force Glial to pretend to be the only storage backend would make local-only persistence harder and would blur the authority boundary.

## Projector Model

The runtime should not hard-code separate top-level APIs such as:

- `attachLocalPersistence(...)`
- `attachSharedProjection(...)`

Instead, v1 should use a generic projector attachment model.

A projector is a runtime-facing integration object that declares:

- what kind of session projection it owns
- whether it consumes outbound local changes
- whether it can hydrate source-state backup
- whether it can apply inbound shared-state projection
- whether it exposes session catalog or browsing capabilities

This keeps the runtime integration generic while preserving explicit semantic distinctions between backup and shared projection.

### Projector Kinds

Recommended v1 projector kinds:

- `source-backup`
- `shared-projection`
- `mirror`

Examples:

- local-only browser restore uses one `source-backup` projector backed by IndexedDB
- a shared browser session may attach both a local `source-backup` projector and a remote `shared-projection` projector
- a debug session may attach an additional `mirror` projector

### Why Multiple Projectors Matter

Multiple projector attachment is desirable because:

- `both` mode naturally means local backup plus shared projection
- future debugging may want a second mirror or bridge projector
- future Glial bridge work may need one runtime to observe and relay between multiple Glial servers

The runtime should therefore support:

- `attachProjector(projector)`
- `detachProjector(id)`
- `listProjectors()`

rather than a pair of special-case attach methods.

The semantic distinction between source backup and shared projection remains important. It is represented by projector capabilities, not by separate hard-coded runtime entry points.

## Session Modes And Storage Policy

V1 needs three user-facing storage policies:

- `local`
- `remote`
- `both`

And two execution attachment states:

- detached
- Glial-routed

Rules:

- `local` means browser or process backup exists locally and reload restore uses it
- `remote` means the logical session is also backed by an authenticated remote state store keyed by `glial_session_id`
- `both` means both local backup and remote backup are maintained
- loading a remote session in the browser should, by default, attach it as a Glial-routed session rather than as a detached copy

## Backup Snapshot Versus Shared Projection

The persistence coordinator must support two persistence products:

- source-state backup snapshots for restore on capable headed runtimes
- full shared-state projection for Glial-routed sessions and headless followers

Rules:

- local backup and remote backup normally store source-state snapshots
- Glial live sharing uses the shared-state projection
- a local durable store may keep both the local source-state backup and a mirrored copy of the latest shared-state projection for debugging or reconnect

## Remote State Store Adapter

Remote backup is not the same thing as the live Glial delta link.

V1 therefore permits a Glial state storage adapter on the server side.

That adapter is keyed by:

- authenticated user identity or trusted claims from the host framework
- `glial_session_id`

The adapter is responsible for:

- remote session catalog
- remote snapshot storage
- loading a remote backup session by logical session id

The adapter is intentionally outside Glial authentication itself. Glial receives already-authenticated identity from the host environment.

## Engine-Facing Contract

The Grip runtime talks to `GripSessionPersistence`.

The interface is shown in language-neutral TypeScript-like form, but the same contract must exist in TypeScript and Python.

```typescript
type SessionMode = "local" | "shared";
type ChangeSource = "local" | "glial" | "hydrate" | "collapse";
type ChangeStatus =
  | "applied"
  | "pending_sync"
  | "confirmed"
  | "superseded";

interface SessionSummary {
  session_id: string;
  title?: string;
  mode: SessionMode;
  last_modified_ms: number;
  last_glial_session_clock?: VirtualClock;
}

interface SyncCheckpoint {
  attached: boolean;
  last_applied_clock?: VirtualClock;
  last_snapshot_clock?: VirtualClock;
  last_snapshot_id?: string;
}

interface PersistedChange {
  change_id: string;
  session_id: string;
  source: ChangeSource;
  status: ChangeStatus;
  origin_replica_id?: string;
  origin_mutation_seq?: number;
  origin_generation?: number;
  session_clock?: VirtualClock;
  target_kind: "context" | "child-order" | "drip" | "tap-meta" | "remove";
  path: string;
  grip_id?: string;
  tap_id?: string;
  payload?: object;
}

interface HydratedSession {
  summary: SessionSummary;
  snapshot: SessionSnapshot;
  applied_changes: PersistedChange[];
  pending_changes: PersistedChange[];
  sync_checkpoint: SyncCheckpoint;
}

interface NewSessionRequest {
  session_id?: string;
  title?: string;
  initial_snapshot?: SessionSnapshot;
}

interface EnableSharingRequest {
  session_id: string;
  mode: "share_local_session";
}

interface RemoveSessionRequest {
  session_id: string;
  scope: "local_only" | "local_and_shared";
}

type PersistenceEvent =
  | { kind: "delta"; change: PersistedChange }
  | { kind: "snapshot_reset"; snapshot: SessionSnapshot; checkpoint: SyncCheckpoint }
  | { kind: "sharing_state"; session_id: string; state: "detached" | "attaching" | "live" | "resyncing" | "error" };

interface GripSessionPersistence {
  newSession(request: NewSessionRequest): Promise<SessionSummary>;
  listSessions(): Promise<SessionSummary[]>;
  getSession(session_id: string): Promise<SessionSummary | null>;
  hydrate(session_id: string): Promise<HydratedSession>;
  subscribe(session_id: string, sink: (event: PersistenceEvent) => void): Promise<() => void>;
  writeIncrementalChange(session_id: string, change: PersistedChange): Promise<void>;
  replaceSnapshot(session_id: string, snapshot: SessionSnapshot, reason: "collapse" | "glial_resync" | "share_seed"): Promise<void>;
  collapse(session_id: string): Promise<void>;
  enableSharing(request: EnableSharingRequest): Promise<void>;
  disableSharing(session_id: string): Promise<void>;
  removeSession(request: RemoveSessionRequest): Promise<void>;
}
```

### Projector Interface

Language-neutral shape:

```typescript
type ProjectorKind = "source-backup" | "shared-projection" | "mirror";

interface GripProjector {
  projector_id: string;
  projector_kind: ProjectorKind;
  consumes_local_changes: boolean;
  supports_hydrate: boolean;
  supports_inbound_apply: boolean;
  supports_session_catalog?: boolean;
}
```

The concrete backup store and Glial link implementations may still exist underneath, but the runtime attaches projectors rather than calling storage-specific top-level entry points.

## Runtime Change Capture Model

The runtime must not attempt to persist directly from arbitrary low-level callbacks.

Instead, each runtime provides a Grok-level changed facility that captures graph mutations and turns them into normalized persistence work.

The changed facility is responsible for:

- marking contexts, drips, taps, and child ordering as dirty when runtime changes occur
- recording explicit removes immediately, because removed entities may no longer be readable later
- coalescing repeated changes to the same entity within one flush window
- scheduling a delayed persistence flush rather than forcing synchronous durable writes on every graph mutation

The changed facility should enqueue dirty entity references, not fully materialized persisted records.

That allows the persistence layer to reread the current graph after the runtime has quiesced and persist the stable final state rather than transient intermediate states.

The local dirty queue is only for locally originated runtime mutations.

Glial-sourced deltas and local hydrate restore do not enter the dirty queue. They use a persisted-apply path described below.

### Dirty Entity Kinds

V1 dirty tracking should include:

- context upsert dirty
- context remove
- child-order dirty
- drip upsert dirty
- drip remove
- drip value dirty
- tap upsert dirty
- tap remove
- tap active-outputs dirty

The last item matters because matcher-driven resolution can change the set of active provided outputs without requiring a new tap identity.

### Flush Model

Persistence flush is intentionally delayed by a small trailing debounce.

The intended flow is:

1. runtime mutates graph state immediately
2. Grok marks the affected entities dirty immediately
3. a trailing debounce schedules a persistence flush
4. when the flush runs, the persistence adapter rereads current graph state for dirty entities
5. the adapter writes normalized `PersistedChange` records and updates the local materialized session view

This design means:

- repeated changes to the same entity before the flush are coalesced
- child order changes persist the final order only
- persistence observes a stable post-propagation graph rather than intermediate states
- Glial-sourced updates and local updates use the same normalized persisted change shape, but not the same enqueue path

### Remove Semantics During Delayed Flush

Removes cannot rely only on rereading current graph state, because the target may already be gone by the time the flush runs.

So the changed facility must record explicit remove intents for:

- removed contexts
- removed drips
- removed taps

The persistence layer may collapse an add-then-remove sequence away during compaction if the entity never became durably visible outside the debounce window.

### Relationship To Sequence Metadata

The changed facility is the point where `origin_mutation_seq` becomes useful to persistence.

Rules:

- locally originated persistable or shared changes receive a fresh `origin_mutation_seq`
- Glial-sourced authoritative applies do not allocate a new local sequence
- a delayed flush may persist several changed entities from one causal runtime turn, but each normalized persisted change still carries its own sequence where applicable

### Implementation Boundary

This changed facility belongs in the Grip runtime integration layer, not inside a specific local store implementation and not inside Glial transport code.

That keeps:

- local-only persistence
- Glial-linked persistence
- future alternative persistence backends

on the same normalized runtime change feed.

## Debug Session Browser

V1 must include a debug or developer-facing session browser similar in spirit to the graph dump tooling.

The session browser should allow:

- listing locally stored sessions
- listing remotely stored sessions available to the authenticated user
- loading a selected local session into the current browser runtime
- loading a selected remote session into the current browser runtime
- showing whether the loaded session is local-only, remote-backed, or Glial-routed

Loading a remote session should by default attach the browser to Glial routing for that `glial_session_id`.

## Runtime Apply Paths

V1 uses three distinct persistence-related runtime paths.

### 1. Local Mutation Observation Path

This is the normal path for UI interaction and local runtime behavior.

Flow:

1. the runtime mutates local graph state
2. the changed facility marks the affected nodes dirty
3. a delayed flush rereads current graph state
4. the flush emits normalized `PersistedChange` records
5. those records are written to the local store
6. if sharing is enabled, locally originated shared records are also published to Glial

This is the only path that uses the Grok dirty queue.

### 2. Inbound Persisted-Apply Path

This path is used for Glial-sourced deltas and Glial snapshot or replay application.

Flow:

1. the client receives normalized `PersistedChange` records or a snapshot from Glial
2. the client writes those records into the local durable store as they are accepted
3. the runtime applies those normalized records directly to graph state
4. the runtime performs that apply under dirty-queue suppression

Rules:

- inbound Glial changes bypass the local dirty queue
- inbound Glial changes do not allocate a new local `origin_mutation_seq`
- inbound Glial changes must not be republished as locally originated outbound changes
- local persistence should reflect inbound Glial records as they arrive, not wait for a later local flush

### 3. Local Hydrate Apply Path

This path is used for browser reload restore or local process restart restore.

Flow:

1. the runtime hydrates from the local durable snapshot and retained journal
2. the hydrated state is applied directly into the runtime
3. that apply runs under the same dirty-queue suppression used for inbound Glial changes

Rules:

- hydrate restore does not enqueue dirty nodes
- hydrate restore does not publish to Glial
- hydrate restore does not allocate new local sequence numbers

## Persisted Apply Operations

To support inbound Glial application and local hydrate restore, the runtime must expose normalized apply operations for each persisted node kind.

V1 requires runtime support for:

- `apply_context_upsert`
- `apply_context_remove`
- `apply_child_order`
- `apply_drip_upsert_or_value`
- `apply_drip_remove`
- `apply_tap_meta`
- `apply_tap_remove`

These operations are runtime-internal apply primitives. They are not a backend-specific storage API.

They must run under an apply context that suppresses dirty-state enqueue.

## Local Store Handling For Local And Glial Changes

The local durable store sees one normalized change model, but two main origins.

### Local-Origin Changes

Local-origin changes are emitted by the dirty-state flush.

Rules:

- local-only sessions write them as locally applied changes
- shared sessions may retain them as pending until Glial confirms or supersedes them

### Glial-Origin Changes

Glial-origin changes arrive already normalized.

Rules:

- they are written into the local store as they are accepted by the client
- they are then applied into the runtime through the persisted-apply path
- if they correspond to a previously pending local change, the local persistence layer should confirm, replace, or supersede that pending local record rather than duplicating both indefinitely

## Required Operation Semantics

### `newSession`

Creates a new local session record.

Rules:

- default mode is `local`
- the session is created locally even if the runtime later enables sharing
- the initial snapshot may be empty except for the root context

### `listSessions`

Returns locally known sessions.

Rules:

- this is a local catalog operation
- it must not require a Glial round trip
- shared sessions that were previously attached still appear in the local catalog

### `hydrate`

Loads the current durable view of a session.

Rules:

- it returns the latest collapsed snapshot
- it returns retained incremental applied changes newer than that snapshot
- it returns any pending unconfirmed shared changes separately
- it returns the last known sync checkpoint

This allows:

- local-only reload restore
- restore before later Glial attachment
- restore of the last known authoritative shared state

### `writeIncrementalChange`

Writes one normalized change into the local persistence system and updates the materialized local view.

Rules:

- the runtime calls this for local changes emitted by the dirty flush after it has already decided to apply them
- the persistence layer also uses the same normalized change shape internally for Glial-sourced changes
- one change write must be atomic with respect to the local materialized session state
- Glial-sourced writes should be recorded as they are accepted by the client rather than waiting for a later local dirty flush

### `replaceSnapshot`

Replaces the current durable snapshot atomically.

Required uses:

- collapse or compaction
- Glial resync reset
- initial remote seeding when sharing is first enabled

### `collapse`

Compacts the current materialized session state into a fresh snapshot.

Rules:

- collapse writes the current graph state from Section 05
- collapse clears obsolete incremental history already represented in that snapshot
- collapse preserves sync checkpoint metadata
- collapse preserves unresolved pending shared changes separately from the collapsed authoritative snapshot

### `enableSharing`

Attaches the current local session to a Glial link.

V1 required mode:

- `share_local_session`

`share_local_session` means:

1. collapse the current local session
2. seed or attach the Glial session using that collapsed snapshot
3. switch the local session mode to `shared`
4. begin replay or live synchronization

V1 does not require a separate `join_existing_remote_session` mode.

### `disableSharing`

Detaches the Glial link without deleting the local session.

Rules:

- the local durable session remains available
- further changes become local-only until sharing is re-enabled

### `removeSession`

Deletes a session.

Rules:

- default UI behavior should use `local_only`
- `local_and_shared` must be explicit because it may delete shared state beyond the local runtime

## Store And Link Internal Contracts

`GripSessionPersistence` is the engine-facing abstraction.

Implementations should usually be built from these two internal contracts.

```typescript
interface GripSessionStore {
  newSession(request: NewSessionRequest): Promise<SessionSummary>;
  listSessions(): Promise<SessionSummary[]>;
  getSession(session_id: string): Promise<SessionSummary | null>;
  hydrate(session_id: string): Promise<HydratedSession>;
  writeChange(session_id: string, change: PersistedChange): Promise<void>;
  replaceSnapshot(session_id: string, snapshot: SessionSnapshot, reason: string): Promise<void>;
  collapse(session_id: string): Promise<void>;
  removeSession(request: RemoveSessionRequest): Promise<void>;
}

interface GripSessionLink {
  enableSharing(request: EnableSharingRequest, checkpoint: SyncCheckpoint, snapshot: SessionSnapshot): Promise<void>;
  disableSharing(session_id: string): Promise<void>;
  publishChange(change: PersistedChange): Promise<void>;
  subscribe(session_id: string, sink: (event: PersistenceEvent) => void): Promise<() => void>;
}
```

This split is recommended, but the runtime still sees one `GripSessionPersistence`.

## Local Implementations

Required local implementations:

- TypeScript browser: IndexedDB-backed `GripSessionStore`
- Python runtime: filesystem-backed `GripSessionStore`

The exact file layout or IndexedDB object-store layout is not mandated by the SDD.

What is mandated:

- atomic session snapshot replacement
- durable incremental change writes
- durable session catalog
- durable sync checkpoint storage

## Shared Implementation

The required shared implementation is a Glial-backed `GripSessionLink`.

It must:

- use the Glial snapshot, replay, and live delta protocols from Sections 06 through 10
- map Glial deltas into `PersistedChange`
- never require the runtime to understand Glial transport details directly

## Local Persistence Of Glial-Sourced Updates

When a Glial-sourced update arrives, it must be written into local persistence through the same normalized change pipeline as a local change.

Rules:

- the incoming remote delta is normalized into `PersistedChange(source="glial", status="confirmed", ...)`
- it is written to the local store atomically with the materialized local graph update
- it updates the local sync checkpoint
- it must not be republished back to Glial

This gives one local durable history regardless of where the change came from.

## Overlap Between Local And Remote Changes

The persistence layer must support overlap between:

- locally generated changes
- remotely received authoritative Glial changes

V1 rules:

1. local-only session
   Local changes are final and are ordered by local write order
2. shared session
   Local changes are written immediately as `pending_sync`
3. when the matching authoritative Glial echo arrives
   The matching pending change becomes `confirmed`
4. when a different authoritative Glial change wins first
   The pending local change becomes `superseded`

Matching should use:

- `origin_replica_id`
- `origin_mutation_seq`

when those are available.

For shared sessions, the materialized durable state must follow the authoritative Glial `session_clock`, not the earlier speculative local write.

## Required Anti-Loop Rule

The persistence layer must never bounce a Glial-sourced change back into Glial as though it were a new local mutation.

Required rule:

- `source="glial"` changes are durable local writes only
- only `source="local"` shared changes are eligible for outbound publication

## Hydrate And Reload Rules

On reload:

- the runtime hydrates from the local store first
- if the session is local-only, that hydrate result is final
- if the session is shared, the hydrate result is the starting local durable state before Glial replay or resync

Pending shared changes may be restored locally, but under the v1 reconnect rules they are not blindly republished after a reset boundary.

## Collapse Rules In Shared Sessions

Collapse is local storage compaction, not a Glial protocol event by itself.

Rules:

- collapse may happen while a session is shared
- collapse must preserve the current authoritative materialized shared state
- collapse must preserve unresolved pending shared changes and sync checkpoint metadata
- collapse must not invent a new Glial clock

## Concrete V1 Implementations

Recommended concrete implementations:

- `IndexedDbGripSessionPersistence`
- `FilesystemGripSessionPersistence`
- `IndexedDbPlusGlialSessionPersistence`
- `FilesystemPlusGlialSessionPersistence`

The combined implementations may be built by composing:

- a local `GripSessionStore`
- an optional `GripSessionLink`

## Non-Goals

This section does not require:

- one universal binary serialization format for all stores
- one universal file layout
- one mandatory database engine
- automatic conflict-free offline mutation replay across a Glial reset boundary
