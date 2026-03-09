# Glial SDD Section 02: Terminology

## Session

A session is the persisted identity of one Grip graph state.

A session may be:

- local-only on one replica with no Glial involvement
- shared through Glial across multiple cooperating replicas

All replicas participating in the same shared session use the same `session_id`.

In v1, `session_id` is the top-level shared graph identity. A separate `graph_id` is not introduced.

## Replica

A replica is one concrete participant in a session. Each replica has its own `replica_id`.

A local-only browser session still has one runtime replica even if it never connects to Glial.

Examples:

- a browser tab
- a Python headless worker
- an AI-enabled backend participant

## Grip

A Grip is the canonical identifier for a logical value in the graph. Grip IDs are runtime-neutral and are serialized in canonical form.

For JavaScript/TypeScript and Python, the canonical grip key is `<scope>:<name>`.

## Context

A context is a structural node in the Grip graph. In Glial, exported and replicated contexts have stable logical identities expressed as canonical string paths.

Example paths:

- `/`
- `/weather-column-0`
- `/table/row-slot-1`

## Drip

A drip is the consumer-facing state entry for a grip within a context. In the replicated Glial model, a `DripState` carries the current value, its current clock, and tap connectivity metadata.

## Tap

A tap is a producer of one or more grips. In Glial, taps are identified structurally, not by runtime object identity.

Tap code is local to each runtime. Glial does not replicate executable tap implementations. It only coordinates ownership and replicates state outputs and metadata.

## Primary

The primary is the replica currently authorized to execute a primary-owned tap.

## Follower

A follower is a replica that does not execute a primary-owned tap locally and instead waits for the replicated outputs produced by the primary.

## Lease

A lease is the server-issued grant that authorizes a replica to hold negotiated-primary ownership for a specific tap for a bounded period of time.

## Snapshot

A snapshot is a materialized view of persisted graph state.

When a session is attached to Glial, a snapshot is taken through a specific Glial-issued clock boundary.

## Replay

Replay is the delivery or reapplication of deltas newer than a replica’s last applied checkpoint so that state can be restored incrementally.

In local-only persistence this may come from a local persistence log.

In Glial-managed sharing this comes from Glial replay.

## Resync

Resync is the process of restoring a replica to current shared state after initial connect, reconnect, or detected sync uncertainty.

## Virtual Clock

A virtual clock is the comparable ordering stamp attached to synchronized deltas and synchronized snapshot entries when a session is managed by Glial.

It is not wall-clock synchronization. It is the shared ordering basis for:

- stale update elision
- replay
- reconnect recovery
- conflict handling

## Ownership Modes

Glial defines three tap execution ownership modes:

- `replicated`
- `origin-primary`
- `negotiated-primary`

These determine whether a tap may run everywhere, only on its origin replica, or on a negotiated owner.
