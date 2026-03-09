# Glial SDD Section 05: Replicated State Model

## Overview

Glial replicates graph state entries, not runtime objects.

The replicated model is the canonical shared state plane for a session. Individual runtimes may project that state into:

- a Grip context graph
- a JSON hierarchy
- debugging or AI-facing graph views

All of those are projections of the same replicated entry model.

The same logical state model is also the basis for local-only persistence.

That means:

- a browser may persist and restore the graph locally without Glial
- when the user later chooses to share or remotely save the session, Glial attaches to the same logical state model rather than introducing a separate graph format

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

`role` is not part of the canonical shared replicated state. It may be included in per-replica exports or diagnostic views generated for a specific connected replica.

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
