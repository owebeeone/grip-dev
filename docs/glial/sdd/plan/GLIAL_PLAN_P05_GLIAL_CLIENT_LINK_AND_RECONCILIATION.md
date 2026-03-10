# Glial Implementation Plan Phase 05: Glial Client Link And Reconciliation

## Testing Plan

- add integration tests where a local shared change is written as `pending_sync` and later confirmed by Glial echo
- add integration tests where a competing authoritative remote change supersedes a pending local change
- add `share_local_session` tests proving a collapsed local session can seed a new shared session
- add replay and `SyncReset` tests proving local checkpoints update correctly
- add anti-loop tests proving Glial-sourced changes are persisted locally but never bounced back to Glial
- add tests proving inbound Glial tap records materialize into real taps or passive taps according to local registry and execution policy
- run client integration tests against the reusable local FastAPI-based Glial test server from Phase 04
- add cross-runtime TS/Python tests proving the same shared session converges under duplicate and out-of-order delivery
- add headed-to-headless tests proving passive taps and current shared outputs are sufficient to hydrate an AI-visible graph
- add tests proving a remote session load in the browser defaults to Glial-routed attachment rather than detached copy
- add tests proving AI-readable tap metadata includes purpose, description, provided grips, param grips, and ownership metadata where available

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
- tap materialization and passive-tap fallback during inbound graph reconstruction
- headed-to-headless shared projection using passive taps and current shared outputs
- browser behavior for loading a remote session into a Glial-routed replica

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
6. Apply inbound Glial state through the persisted-apply path rather than through the local dirty queue.
7. Materialize inbound tap records through the local tap registry, falling back to passive taps when execution is unavailable or disallowed.
8. Support headless or AI replicas that hydrate passive taps and current shared outputs without local application tap code.
9. Ensure remote session load updates the browser session record and attaches as Glial-routed by default.
10. Expose share-state changes back to the runtime through persistence events.

## Exit Criteria

- a locally persisted session can be switched into shared mode
- local and remote changes reconcile through the normalized persistence pipeline
- authoritative Glial echoes confirm matching pending local changes
- remote winning changes supersede stale pending local changes
- inbound Glial graph state reconstructs taps through the local materialization registry without requiring cross-language tap translation
- headless replicas can hydrate a readable passive graph from shared-state projection alone
- a browser loading a remote session becomes Glial-routed by default
- both runtimes can participate in the same shared session model

## Non-Goals

- no Glial gateway, router, or shard HA implementation yet
- no production load-balancing rollout yet
