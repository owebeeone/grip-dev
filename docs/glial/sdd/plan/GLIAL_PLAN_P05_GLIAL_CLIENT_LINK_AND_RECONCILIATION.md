# Glial Implementation Plan Phase 05: Glial Client Link And Reconciliation

## Testing Plan

- add integration tests where a local shared change is written as `pending_sync` and later confirmed by Glial echo
- add integration tests where a competing authoritative remote change supersedes a pending local change
- add `share_local_session` tests proving a collapsed local session can seed a new shared session
- add replay and `SyncReset` tests proving local checkpoints update correctly
- add anti-loop tests proving Glial-sourced changes are persisted locally but never bounced back to Glial
- run client integration tests against the reusable local FastAPI-based Glial test server from Phase 04
- add cross-runtime TS/Python tests proving the same shared session converges under duplicate and out-of-order delivery

## Goal

Attach the local persistence model to Glial while preserving the local store as the durable baseline.

This phase implements the client-side `GripSessionLink` in both runtimes.

## Scope

- `enableSharing` and `disableSharing`
- `share_local_session` seeding flow
- outbound publication of local shared changes
- inbound application of Glial snapshot, replay, and live delta events
- normalization of Glial-sourced updates into `PersistedChange`
- sync checkpoint maintenance
- pending local change confirmation or supersession

## Expected Code Areas

TypeScript:

- new Glial client link implementation
- integration with browser persistence implementation

Python:

- new Glial client link implementation
- integration with filesystem persistence implementation

Shared protocol documents already exist under `docs/glial/sdd/`.

## Work Items

1. Implement `GripSessionLink` for client runtimes.
2. Wire `enableSharing` so local collapsed state seeds the shared session.
3. Persist outbound local shared changes as `pending_sync`.
4. On incoming authoritative Glial deltas, confirm or supersede pending local changes.
5. Persist Glial snapshots and replay results through the same local store path.
6. Expose share-state changes back to the runtime through persistence events.

## Exit Criteria

- a locally persisted session can be switched into shared mode
- local and remote changes reconcile through the normalized persistence pipeline
- authoritative Glial echoes confirm matching pending local changes
- remote winning changes supersede stale pending local changes
- both runtimes can participate in the same shared session model

## Non-Goals

- no Glial gateway, router, or shard HA implementation yet
- no production load-balancing rollout yet
