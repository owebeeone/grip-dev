# Glial SDD Section 12: Failure And Recovery

## Replica Disconnect

If a replica disconnects:

- its connection is removed from the shard
- if it held negotiated-primary ownership, lease expiration or missing heartbeats trigger loss handling
- on reconnect, it resumes through snapshot/replay rules
- locally buffered synchronized writes that were not yet confirmed by echoed authoritative Glial deltas are not blindly replayed across the reconnect boundary

## Lost Negotiated Primary

If the negotiated primary disappears:

- Glial revokes the lease
- Glial broadcasts `ReplicaLost`
- Glial broadcasts `PrimaryChanged`
- the origin primary resumes immediately if still present

Followers do not guess. They wait for Glial’s authoritative ownership messages.

## Lost Origin Primary

If an origin primary disappears and no negotiated primary exists:

- the tap becomes temporarily unowned
- followers continue to wait for replicated output
- if the origin reconnects, it resumes as origin primary
- if policy later permits negotiation, another replica may acquire ownership

## Duplicate Or Out-Of-Order Delta Delivery

If a replica receives duplicated or out-of-order deltas:

- dedupe by `delta_id`
- compare entry clocks
- ignore stale updates

This is the normal case, not an exceptional case.

## Replay Window Miss

If a reconnecting replica presents a cursor older than the retained replay window:

- Glial sends `SyncReset`
- Glial sends a fresh snapshot
- replay then resumes only for deltas newer than the snapshot clock
- the replica must treat any older unconfirmed local synchronized writes as stale local intent requiring re-evaluation, not as authoritative queued deltas

## Client-Detected Sync Uncertainty

If a replica cannot trust its local state application:

- it sends `SyncError`
- Glial responds with `SyncReset`
- Glial resends the full graph snapshot

V1 intentionally prefers resnapshot over complex partial repair.

## Shard Loss

If a shard fails:

- the session directory mapping is invalidated or remapped
- reconnecting clients are sent to a new shard
- the new shard restores durable snapshot and replay state
- clients recover through the normal snapshot/replay protocol

## Durable Store Unavailability

If the durable session state store is unavailable, Glial must prefer correctness over partial service.

Recommended behavior:

- existing in-memory sessions on healthy shards may continue while they remain healthy
- new failover, replay, or recovery operations that cannot be made correct should fail closed
- Glial should not invent missing replay or snapshot data

## Stale Local Async Completion

If a local async tap completes after a newer authoritative state has already been accepted:

- the completion must be elided locally based on the current entry clock
- stale outputs must not overwrite newer synchronized state

This is one reason clocks must propagate through taps and drips, not just across the network.
