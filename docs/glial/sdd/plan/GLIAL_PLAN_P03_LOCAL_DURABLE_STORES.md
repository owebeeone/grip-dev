# Glial Implementation Plan Phase 03: Local Durable Stores

## Testing Plan

- add browser-side IndexedDB integration tests using deterministic fake IndexedDB support in CI and local tests
- add filesystem-backed Python tests using temporary directories
- add restart and rehydrate tests proving sessions survive process or page reload
- add save, collapse, and hydrate tests covering empty sessions, dirty sessions, collapsed sessions, and sessions with pending shared changes
- add collapse and compaction tests proving obsolete applied changes are removed while pending shared changes and checkpoints remain
- add session catalog tests for list, create, remove, and metadata persistence
- add corruption-handling tests proving hydrate fails closed or requests reset rather than inventing state

## Goal

Implement the first real local persistence backends:

- IndexedDB for TypeScript or browser runtimes
- filesystem storage for Python runtimes

This phase makes local-only persistence a working product feature.

## Scope

- durable `GripSessionStore` for browser environments
- durable `GripSessionStore` for Python environments
- local snapshot storage
- local incremental journal storage
- session catalog
- sync checkpoint storage
- collapse or compaction support

## Expected Code Areas

TypeScript:

- new IndexedDB-backed implementation under `grip-core/src/` or an adjacent browser package
- browser test harness and fake IndexedDB test utilities
- package bootstrap needed to run Vitest and IndexedDB-backed tests in `grip-core`

Python:

- filesystem-backed implementation under `grip-py/src/grip_py/`
- temp-directory based tests

## Work Items

1. Design concrete local storage layout for sessions, snapshots, changes, and checkpoints.
2. Implement `newSession`, `listSessions`, `hydrate`, `writeChange`, `replaceSnapshot`, `collapse`, and `removeSession`.
3. Ensure `collapse` preserves pending shared changes and sync checkpoint metadata.
4. Expose local-only reload restore flow in a small reference integration.
5. Validate that the local-only path works with no Glial service available.

## Exit Criteria

- browser sessions persist locally and restore after reload
- Python sessions persist locally and restore after process restart
- session catalog operations work locally
- collapse compacts local history correctly
- the runtime can rely on local persistence as the default path before any Glial attachment

## Non-Goals

- no live sharing yet
- no remote snapshot, replay, or lease handling yet
