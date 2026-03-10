# Glial SDD Section 05: Replicated State Model

## Overview

Glial replicates graph state entries, not runtime objects.

The replicated model is the canonical shared state plane for a session. Individual runtimes may project that state into:

- a Grip context graph
- a JSON hierarchy
- debugging or AI-facing graph views

All of those are projections of the same replicated entry model.

The same logical state model is also the basis for local-only persistence.

Glial v1 uses two related but distinct persistence products:

- a source-state snapshot for backup and restore on a runtime that has the real application tap code
- a full shared-state projection for Glial-routed sharing, follower replicas, and headless replicas

That means:

- a browser may persist and restore the graph locally without Glial
- when the user later chooses to share or remotely save the session, Glial attaches to the same logical state model rather than introducing a separate graph format

The important rule is:

- backup restore only needs enough state to rebuild the intended executable graph on a capable runtime
- live shared projection must carry the current materialized graph state, including outputs of taps that a follower or headless replica will not execute locally

## Persistence Boundary

Replicated state includes:

- contexts
- context connectivity
- ordered child lists
- drip current values
- tap metadata
- semantic metadata
- optional tap cache metadata or cache state where safe

Local-only runtime state includes:

- listeners and subscriptions
- UI mount state
- task queue state
- timers
- in-flight async requests
- abort controllers
- controller objects
- executable function objects

## Source-State Snapshot Versus Shared-State Projection

### Source-State Snapshot

The source-state snapshot is the backup or restore format used by:

- local browser reload restore
- local Python process restore
- remote backup restore into a capable headed runtime

The source-state snapshot stores:

- deterministic contexts and child ordering
- stateful tap-owned durable values such as atom values
- optional tap cache state only when a tap explicitly opts in
- enough session metadata to rebuild matcher inputs and stable graph structure

The source-state snapshot does not need to persist every derived function or async output.

The expected restore flow is:

1. register the normal application taps, factories, and matcher bindings
2. hydrate the source-state snapshot into the stateful source taps
3. let matcher selection, function taps, and async taps converge from that restored source state

### Shared-State Projection

The shared-state projection is the Glial-routed session model used by:

- headed-to-headed live sharing
- headed-to-headless sharing
- follower replicas that do not execute function or async taps locally
- AI graph inspection and tool-driven takeover

The shared-state projection stores:

- the full materialized context graph
- current drip values
- tap metadata
- active-output shape
- semantic metadata needed for understanding and passive materialization

The shared-state projection is the state that Glial routes and fans out.

## Top-Level Snapshot Shape

The canonical Glial-managed snapshot shape is:

```json
{
  "session_id": "sess_123",
  "session_clock": {
    "wall_time_ms": 1741510000000,
    "logical_counter": 8,
    "replica_id": "glial"
  },
  "contexts": {
    "/": { "...": "ContextState" },
    "/weather-column-0": { "...": "ContextState" }
  }
}
```

The `contexts` object is the authoritative materialized graph.

In normalized payloads, the field name may remain `session_id`, but semantically that value is the `glial_session_id`.

Local-only persistence may store the same logical graph state without requiring an active Glial connection.

## ContextState

Each context is stored by canonical path.

```json
{
  "path": "/table/row-slot-1",
  "name": "row-slot-1",
  "purpose": "Second visible row slot in the virtualized table",
  "description": "Structural row slot that is rebound during scrolling",
  "entry_clock": {
    "wall_time_ms": 1741510000100,
    "logical_counter": 0,
    "replica_id": "glial"
  },
  "children": ["cell-0", "cell-1", "cell-2"],
  "drips": {
    "table:row-id": { "...": "DripState" },
    "table:row-data": { "...": "DripState" }
  }
}
```

Rules:

- `path` is the canonical context path
- `name` is the final segment name
- `children` is the ordered list of immediate child names
- child names must be unique under a parent
- `entry_clock` is the current authoritative clock for the context entry itself

## DripState

Each `DripState` is stored under the grip ID it represents.

```json
{
  "grip_id": "table:row-id",
  "name": "row-id",
  "purpose": "Current bound record ID for this row slot",
  "description": "Used to understand which record is currently bound to the slot",
  "is_binding": true,
  "value_clock": {
    "wall_time_ms": 1741510000200,
    "logical_counter": 0,
    "replica_id": "glial"
  },
  "value": "abc123",
  "taps": [
    { "...": "TapExport" }
  ]
}
```

Rules:

- `grip_id` is the canonical grip key
- `value_clock` is the authoritative clock for the current value
- `is_binding` marks drips that explicitly describe current context bindings
- `value` must use the value encoding rules defined below

## TapExport

Connected taps are exported as metadata attached to drips.

```json
{
  "tap_id": "/table/row-slot-1@FunctionTap:table:row-data",
  "tap_type": "FunctionTap",
  "mode": "origin-primary",
  "role": "follower",
  "actual_provides": ["table:row-data"],
  "provides": ["table:row-data", "table:row-id"],
  "home_param_grips": [],
  "destination_param_grips": ["table:row-id"],
  "purpose": "Provides row data for the current bound record",
  "description": "Runs on the origin primary and followers wait for replicated output",
  "metadata": {},
  "cache_state": null
}
```

Rules:

- `mode` is one of `replicated`, `origin-primary`, or `negotiated-primary`
- `role` is replica-local derived runtime state, typically `primary` or `follower`
- `actual_provides` is the subset actually connected at this location
- `cache_state` is optional and must be JSON-serializable if present
- tap records are persisted as structural and execution-policy metadata, not as executable code

`role` is not part of the canonical shared replicated state. It may be included in per-replica exports or diagnostic views generated for a specific connected replica.

## Runtime Materialization Of Persisted State

Persisted graph state may be projected back into a live runtime graph.

That runtime materialization must distinguish:

- local observation of runtime changes
- inbound application of persisted state

Inbound persisted application is used for:

- local hydrate restore
- Glial snapshot reset
- Glial replay
- Glial live deltas

Those inbound applies must update the runtime graph directly and must not re-enter the local dirty queue.

## Tap Reification Rules

Persisted tap records do not carry executable code.

When a runtime reconstructs graph state from persisted data, a tap record must be reified through a local tap materialization registry.

Possible outcomes:

- create a real local tap if the runtime has a matching executable implementation and policy allows it
- create a passive tap if the runtime is follower-only, headless, or lacks a local executable implementation

This preserves faithful graph shape across mixed runtimes without requiring cross-language tap translation.

## Matcher And Active-Tap Rules

Matchers are code and policy, not authoritative persisted state by themselves.

Rules:

- on a capable headed runtime restoring from backup, matchers rerun after source-state hydrate
- the restored stateful tap values determine which matcher-selected taps become active
- on a follower or headless replica, the current active tap set is taken from the shared-state projection rather than rerun locally
- therefore Glial must export the currently active tap metadata and actual provided outputs, not just the static matcher definitions

## Value Encoding

V1 values must be JSON-compatible.

Allowed native forms:

- `null`
- `boolean`
- `number`
- `string`
- `array`
- `object` with string keys

If a value is not naturally JSON-compatible, it must use a typed envelope.

Example:

```json
{
  "$type": "datetime",
  "value": "2026-03-09T09:00:00.000Z"
}
```

Executable values are never synchronized.

Forbidden synchronized values:

- functions
- controllers
- abort signals
- class instances with runtime behavior
- subscriptions

## Async Cache Rules

Async tap cache persistence is optional and opt-in.

Rules:

- v1 does not require generic async cache save or restore
- an async tap may explicitly export cache state if the cache is JSON-safe and materially improves restore behavior
- if an async tap does not opt in, source-state restore simply re-executes or refetches after hydrate
- followers and headless replicas do not require async cache state to display current shared outputs because the shared-state projection already carries the latest published values

## Delta Targets

Live and replay deltas address the same replicated model.

The v1 target kinds are:

- `context`
- `child-order`
- `drip`
- `tap-meta`
- `remove`

The delta payload mirrors the corresponding snapshot substructure.

## Large JSON Entries

Large mutable JSON is replace-only at entry granularity in v1.

That means:

- a large JSON blob may be the `value` of one `DripState`
- updates replace the entire blob
- the blob is ordered by one authoritative `value_clock`

If later performance requires finer granularity, the JSON can be split into multiple stable entries without changing the overall Glial model.
