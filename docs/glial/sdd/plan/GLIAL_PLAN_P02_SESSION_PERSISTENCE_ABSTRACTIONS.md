# Glial Implementation Plan Phase 02: Session Persistence Abstractions

## Testing Plan

- add contract tests for the `GripSessionPersistence` interface in TypeScript and Python
- add in-memory reference implementation tests for `newSession`, `listSessions`, `hydrate`, `writeIncrementalChange`, `replaceSnapshot`, `collapse`, and `removeSession`
- add subscription tests proving that normalized persistence events are emitted consistently
- add anti-loop tests proving `source="glial"` changes are not republished as local outbound changes
- add hydrate tests proving pending shared changes and sync checkpoints are returned separately
- add Grok changed-feed tests proving repeated dirty notifications coalesce before flush
- add remove-intent tests proving deleted contexts, drips, and taps are still persisted correctly after delayed flush
- add child-order and tap active-output tests proving persistence rereads final graph state at flush time rather than recording intermediate states

## Goal

Introduce the persistence abstraction layer defined in Section 14 of the SDD.

This phase creates the engine-facing contract and in-memory reference implementations, without durable storage engines yet.

## Scope

- define `GripSessionPersistence` in TypeScript
- define the matching protocol or ABC in Python
- define normalized types such as `PersistedChange`, `HydratedSession`, `SessionSummary`, and `SyncCheckpoint`
- add an in-memory `GripSessionStore`
- add a `NullGripSessionLink` or equivalent no-op shared link for local-only mode
- add the Grok-level changed facility that marks entities dirty and schedules delayed persistence flush
- wire the runtimes so local changes can be routed through the persistence abstraction via that changed facility

## Expected Code Areas

TypeScript:

- new persistence module under `grip-core/src/`
- exports from `grip-core/src/index.ts`
- runtime integration in `grip-core/src/core/grok.ts` and related graph coordination code

Python:

- new persistence module under `grip-py/src/grip_py/`
- interface definitions in `grip-py/src/grip_py/core/interfaces.py` or a dedicated persistence package
- runtime integration in `grip-py/src/grip_py/core/grok.py` and related graph coordination code

## Work Items

1. Define the shared persistence data structures in both runtimes.
2. Add a Grok-level changed-feed abstraction that records dirty refs and explicit remove intents.
3. Add delayed flush scheduling and coalescing rules for that changed feed.
4. Implement in-memory session catalog and snapshot plus change journal.
5. Integrate `hydrate` into runtime bootstrapping.
6. Route local applied changes through `writeIncrementalChange` using reread-on-flush materialization rather than synchronous direct writes.
7. Add subscription or callback support for normalized persistence events.
8. Keep Glial link optional and detached by default.

## Exit Criteria

- both runtimes expose a matching persistence API
- local-only sessions can be created, hydrated, updated, collapsed, and removed in memory
- both runtimes expose a Grok changed facility that coalesces dirty entity refs and explicit removes before flush
- the runtime no longer needs to know whether persistence is local-only or Glial-linked
- normalized change records are ready for durable backends in Phase 03

## Non-Goals

- no IndexedDB or filesystem backend yet
- no real Glial transport yet
- no gateway or shard implementation yet
