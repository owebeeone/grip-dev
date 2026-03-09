# Glial SDD Section 06: Virtual Clock Model

## Overview

Glial uses a shared virtual clock to order synchronized updates.

The clock is used for:

- stale update elision in drips
- replay ordering
- reconnect recovery
- snapshot reconstruction

This is an ordering protocol, not wall-clock synchronization.

The Glial virtual clock does not replace replica-local mutation ordering or tap-generation lineage.

## Clock Structure

The canonical v1 clock structure is:

```json
{
  "wall_time_ms": 1741510000000,
  "logical_counter": 3,
  "replica_id": "glial"
}
```

Comparison is lexicographic:

1. `wall_time_ms`
2. `logical_counter`
3. `replica_id`

## Local Origin Ordering

Every synchronized mutation created on a replica must also carry replica-local ordering metadata.

V1 distinguishes three different notions of order:

- `origin_mutation_seq`: a strictly increasing per-replica sequence assigned when a synchronized mutation is created locally
- `origin_generation`: an optional per-replica lineage or request generation propagated through taps and drips so stale async results can be dropped
- `session_clock`: the authoritative Glial-issued clock assigned when the mutation is accepted

These are not interchangeable.

Rules:

- `origin_mutation_seq` preserves local happens-before order for multiple local mutations emitted before or during network delivery
- `origin_generation` is used for stale async result elision and causal lineage
- `session_clock` defines the final cross-replica ordering for accepted synchronized deltas

For the first implementation, `origin_mutation_seq` is the primary required runtime sequence.

`origin_generation` should remain an internal causal aid for async or delayed work where needed, not a reason to expose a new public sequence-only subscription model on drips.

`origin_mutation_seq` is assigned only when the replica originates a new synchronized or persistable mutation.

Applying a Glial-sourced authoritative update does not allocate a new local `origin_mutation_seq`.

Example:

- a button click that immediately updates `B` and starts an async request gets a new `origin_generation`
- any later async result caused by that click carries the same `origin_generation`
- if a second click produces a newer `origin_generation`, older async outputs must be dropped locally before sync
- each synchronized emitted delta still gets its own `origin_mutation_seq`

## Multiple Mutations From One Root Event

One local root event may emit multiple mutations.

Examples:

- one click updates more than one drip
- one function tap emits more than one provided grip
- one async completion updates one drip immediately and another later

V1 does not require a nested subsequence notation such as `200.1` or `200.2`.

Instead:

- `origin_generation` groups all mutations caused by the same root event or causal chain
- `origin_mutation_seq` orders each individual emitted mutation from that replica

So if one root event logically means “event 200”, the actual emitted mutations may simply be:

- `origin_generation = 200`
- `origin_mutation_seq = 501`
- `origin_mutation_seq = 502`
- `origin_mutation_seq = 503`

Grouping and ordering are separate concerns.

Each emitted mutation still gets a fresh `origin_mutation_seq`.

A tap output should not simply reuse the largest input sequence number as its own emitted mutation sequence.

If lineage from inputs matters, it should be carried separately as causal metadata rather than by reusing the emitted mutation sequence.

## What Local Sequence Does And Does Not Solve

Local sequence is useful for:

- ordering locally originated persisted or shared mutations
- ignoring older local updates for the same grip or value stream
- matching a locally pending shared change with its later authoritative Glial echo

Local sequence is not the primary solution for:

- stale completion from an outdated async request
- matcher-driven tap substitution

Those cases should be handled first by runtime behavior:

- async taps drop stale completions before publication using latest-request or latest-key logic
- matcher substitution disconnects the old producer so it no longer has a valid destination to publish into

If those runtime guarantees hold, local sequence remains simple and does not need to become a general-purpose rescue mechanism for every stale publication case.

## Authoritative Clock Source

Glial assigns the authoritative clock for every accepted synchronized delta.

Replicas may propose clocks and report their last observed Glial-issued clock, but the final accepted delta clock is assigned by Glial.

For accepted synchronized deltas:

- `replica_id` on the authoritative clock is `glial`
- `origin_replica_id` is carried separately on the delta

## Session Clock Floor

Each session has a current authoritative clock floor.

When a new session is created, the initial floor is:

- `wall_time_ms = current Glial server time`
- `logical_counter = 0`
- `replica_id = "glial"`

## Client Clock Skew Bound

Client-supplied clocks are advisory only.

V1 defines a maximum allowed client-ahead skew:

- `max_client_clock_ahead_ms = 60_000`

Rules:

- if a client-supplied `proposed_clock.wall_time_ms` is more than `max_client_clock_ahead_ms` ahead of current Glial wall time, it must not advance the authoritative base
- if a client-supplied `observed_session_clock.wall_time_ms` is more than `max_client_clock_ahead_ms` ahead of current Glial wall time, it must not advance the authoritative base
- Glial may log the event, ignore the offending future-ahead component, or reject the request by policy
- v1 default behavior is to ignore the future-ahead component for ordering and continue using Glial-issued clocks

## Clock Assignment Algorithm

For v1, Glial uses this assignment rule for accepted mutations:

1. Sanitize client-supplied clocks using the client skew bound
2. Let `base` be the maximum of:
   - current session clock floor
   - client `observed_session_clock`, if provided
   - client `proposed_clock`, if provided
3. Preserve known same-replica source order using `origin_mutation_seq` before stamping authoritative clocks
4. Let `now_ms` be the current Glial server time
5. If `now_ms > base.wall_time_ms`:
   - assigned clock = `(now_ms, 0, "glial")`
6. Otherwise:
   - assigned clock = `(base.wall_time_ms, base.logical_counter + 1, "glial")`
7. Set the session clock floor to the assigned clock

This is enough for v1 because all authoritative synchronized ordering comes from Glial.

If Glial cannot safely preserve or reconstruct same-replica source order, it should force replay or full resync rather than guessing.

## Replica Responsibilities

Each replica maintains a local clock floor.

Rules:

- when a replica receives a Glial-issued clock, it must advance its local floor to at least that value
- when a replica creates a synchronized mutation, it must assign the next `origin_mutation_seq`
- when a replica starts a new local causal chain, it should assign a new `origin_generation`
- when a replica emits a local mutation request, it may attach:
  - `proposed_clock`
  - `observed_session_clock`
- synchronized mutation messages should also carry `origin_mutation_seq` and, when relevant, `origin_generation`
- local-only runtime updates that are not synchronized do not need Glial-issued clocks
- Glial-sourced updates applied into the local runtime do not allocate a new `origin_mutation_seq`; they keep their authoritative `session_clock`

## Propagation Through Taps And Drips

Every synchronized update must propagate its authoritative clock through the runtime.

Rules:

- drips store the latest applied clock for their current value
- drips and taps that care about async staleness should also track the latest relevant `origin_generation`
- drips should also ignore incoming local values older than the last applied sequence for that same grip or value stream
- taps receiving synchronized input must preserve or carry forward the relevant current clock context
- async and function taps may also attach `caused_by_clock` to indicate lineage from an earlier synchronized input
- async outputs caused by an older `origin_generation` must be dropped before publication if a newer generation for the same local causal chain already exists

Taps do not need one global input subsequence comparison across all input grips.

Instead:

- each grip input is first stale-elided independently
- the tap evaluates against the latest materialized value set
- if grip `A` has already advanced past local sequence `501`, a later arrival for grip `A` at local sequence `500` is ignored
- a newer value for grip `B` may still trigger another evaluation even if grip `A` has not changed

Normal value subscribers do not need a separate public subscription mode for sequence-only changes in v1.

`caused_by_clock` is informational lineage. It does not replace the authoritative ordering clock on the emitted synchronized delta.

## Snapshot Clocks

Every snapshot entry carries its own `entry_clock` or `value_clock`.

This allows a replica restoring from snapshot to rebuild its local stale-elision state without replaying the full history.

## Stale Update Elision Rule

For any target entry:

- if `incoming_clock > current_clock`, apply the update
- otherwise, ignore it as stale or duplicate

This rule is the same for:

- live deltas
- replay deltas
- local synchronized updates echoed back from Glial

For local async execution, generation-based stale elision happens before synchronized publication.

## Why Per-Entry Clocks Matter

Per-entry clocks are necessary because Glial does not guarantee perfect transport order and does not rely on a single perfect stream.

Using one clock per synchronized target gives a uniform recovery rule for:

- reconnect after missed messages
- duplicate delivery
- out-of-order arrival
- full snapshot restore
