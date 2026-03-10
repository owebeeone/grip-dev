# Glial SDD Section 15: Package Boundaries

## Overview

The implementation should be split into packages that preserve the local-first architecture.

The key rule is:

- local persistence and the canonical session model must remain usable without any Glial network dependency

This section defines the recommended package boundaries for v1.

## Package Set

The recommended package set is:

- `glial-local-ts`
- `glial-local-py`
- `glial-net-ts`
- `glial-net-py`
- `glial-router-py`

V1 does not require `glial-router-ts`.

## `glial-local-ts` And `glial-local-py`

These packages own the canonical persisted session model and the engine-facing persistence contracts.

They are not just value bags.

They must define:

- session identity and metadata types
- canonical snapshot and normalized change types
- sync checkpoints
- local sequence metadata such as `origin_generation` and `origin_mutation_seq`
- `GripSessionPersistence`
- `GripSessionStore`
- `GripSessionLink` interface types
- `GripProjector` interface types
- in-memory or reference implementations that do not require Glial networking

They must not depend on:

- Grip runtime object classes such as concrete `Drip`, `Context`, or `Tap`
- Glial transport implementations
- router or shard server code

They may know about:

- canonical context paths
- grip IDs
- target kinds such as `drip` or `context`
- authoritative Glial `session_clock` fields when present

That means `glial-local-*` owns the shared data model, but not the runtime object graph.

## `glial-net-ts` And `glial-net-py`

These packages own client-side Glial communication.

They must:

- depend on `glial-local-*`
- implement the `GripSessionLink` contract
- implement `GripProjector` for shared projection attachment
- implement snapshot, replay, resync, and live delta handling
- implement Glial clock, lease, and protocol message handling needed by clients

They must not own:

- the canonical persisted session model
- local-only storage contracts
- router or shard server code

## `glial-router-py`

This package owns server-side Glial coordination.

It should implement:

- gateway or router entry points
- shard authority behavior
- session directory integration
- authoritative clock assignment
- snapshot and replay serving
- lease and presence handling
- authenticated remote state storage adapters for backup and session catalog access

It depends on:

- `glial-local-py`
- `glial-net-py`

V1 does not require a TypeScript router package.

## Dependency Direction

The required dependency direction is:

```text
grip-core -> glial-local-ts
grip-py   -> glial-local-py

glial-net-ts -> glial-local-ts
glial-net-py -> glial-local-py

glial-router-py -> glial-net-py + glial-local-py
```

Preferred rule:

- `grip-core` and `grip-py` depend on `glial-local-*`, not on `glial-net-*`

This keeps the local-only path clean and prevents Glial networking from becoming a mandatory runtime dependency.

Applications or integration layers may opt into `glial-net-*` when sharing is enabled.

## Why `glial-local-*` Is Not Just A Value Bag

If `glial-local-*` were only a raw value container, the important semantics would leak back into Grip runtime code or into each transport implementation.

That would duplicate logic for:

- canonical identifiers
- normalized change shapes
- local sequence and generation tracking
- sync checkpoints
- pending versus confirmed shared changes

So `glial-local-*` must own the canonical session semantics, while still remaining independent of concrete Grip runtime object types.

## Relationship To Grip Runtimes

`grip-core` and `grip-py` remain responsible for:

- runtime graph behavior
- concrete drip, tap, and context execution
- attaching one or more projectors to the runtime
- translating runtime changes into normalized persisted changes or projector events
- applying normalized persisted or projected changes back into runtime state
- tap materialization registries for reconstructing persisted tap records into either real local taps or passive taps

They should not own:

- transport message protocols
- server routing logic
- storage-specific catalog or session checkpoint semantics

Applications and demo tooling may add thin UI or CLI layers on top of these packages for:

- local session browsing
- remote session browsing
- session load or attach actions

## Local Storage Implementations

This SDD does not require separate package names for every storage backend.

V1 only requires that:

- browser IndexedDB-backed local persistence exists on the TypeScript side
- filesystem-backed local persistence exists on the Python side

Those implementations may live:

- inside `glial-local-*`
- or in closely related submodules

as long as the package boundary above remains intact.

## Non-Goals

This section does not require:

- one monolithic `glial` package
- a TypeScript router package
- a hard commitment today on whether every local backend is a separate package or a submodule
