# Glial Virtual Clock Synchronization Messages

This appendix defines a minimal first-pass protocol for synchronizing the Glial virtual clock across replicas.

The model is:

- each replica has a local virtual clock
- Glial maintains a per-session virtual clock floor
- Glial assigns the authoritative clock to every accepted synchronized delta
- replicas advance their local clock floor whenever they observe a Glial-issued clock

This is not wall-clock synchronization. It is ordering synchronization.

## Clock Model

```python
from typing import Literal
from pydantic import BaseModel


class VirtualClock(BaseModel):
    wall_time_ms: int
    logical_counter: int
    replica_id: str
```

Comparison is lexicographic by:

1. `wall_time_ms`
2. `logical_counter`
3. `replica_id`

## Common Clock Envelope

These fields are intended to be embedded into mutating client->Glial messages.

```python
class ClockObservation(BaseModel):
    proposed_clock: VirtualClock | None = None
    observed_session_clock: VirtualClock | None = None
```

Meaning:

- `proposed_clock`: the local clock the replica sampled for the outgoing mutation
- `observed_session_clock`: the latest Glial-issued session clock the replica has already seen

Glial merges these with the session clock and assigns the authoritative result.

These clock observations do not replace replica-local origin ordering metadata.

Glial must also apply a client clock skew bound before using client-supplied wall time for ordering.

V1 default:

- `max_client_clock_ahead_ms = 60_000`
- future-ahead client wall times beyond that bound do not advance the authoritative base

## Client -> Glial Messages

### ClockHello

Sent when a replica first connects.

```python
class ClockHello(BaseModel):
    kind: Literal["clock_hello"] = "clock_hello"
    message_id: str
    session_id: str
    replica_id: str
    sent_at_ms: int
    local_clock: VirtualClock | None = None
    last_seen_session_clock: VirtualClock | None = None
```

### ClockResyncRequest

Sent when a replica wants the latest session clock floor without waiting for another delta.

```python
class ClockResyncRequest(BaseModel):
    kind: Literal["clock_resync_request"] = "clock_resync_request"
    message_id: str
    session_id: str
    replica_id: str
    sent_at_ms: int
    local_clock: VirtualClock | None = None
    last_seen_session_clock: VirtualClock | None = None
```

This is mainly useful after reconnect or long idle periods.

### ClockObserveOnly

Optional lightweight message for a replica that has nothing else to send but wants to keep its floor aligned.

```python
class ClockObserveOnly(BaseModel):
    kind: Literal["clock_observe_only"] = "clock_observe_only"
    message_id: str
    session_id: str
    replica_id: str
    sent_at_ms: int
    observed_session_clock: VirtualClock | None = None
```

In practice, this can often be folded into heartbeat traffic instead of remaining a standalone message.

## Glial -> Client Messages

### ClockWelcome

Returned after `ClockHello`.

```python
class ClockWelcome(BaseModel):
    kind: Literal["clock_welcome"] = "clock_welcome"
    message_id: str
    session_id: str
    replica_id: str
    session_clock: VirtualClock
```

The replica must advance its local floor to at least `session_clock`.

### ClockResyncResponse

Returned after `ClockResyncRequest`.

```python
class ClockResyncResponse(BaseModel):
    kind: Literal["clock_resync_response"] = "clock_resync_response"
    message_id: str
    session_id: str
    replica_id: str
    session_clock: VirtualClock
```

### ClockAdvanced

Optional out-of-band Glial notice that the session floor has advanced.

```python
class ClockAdvanced(BaseModel):
    kind: Literal["clock_advanced"] = "clock_advanced"
    message_id: str
    session_id: str
    session_clock: VirtualClock
```

This is optional because most flows can piggyback clock advancement on other messages.

## Authoritative Clock Assignment

The most important rule is not a standalone message. It is how Glial processes any mutating client message.

Given:

- current Glial session clock
- `proposed_clock`
- `observed_session_clock`

Glial computes:

1. sanitize client-supplied clocks using the client skew bound
2. merge the highest valid observed value into the session clock floor
3. tick the session clock forward
4. assign that value as the authoritative clock for the accepted delta

That authoritative clock then appears on:

- the persisted/synchronized `GraphDelta`
- the origin replica's acknowledgement path
- replay batches
- live delta batches

## Suggested Mutation Acknowledgement Shape

Any Glial acknowledgement for an accepted mutation should carry the assigned clock.

```python
class MutationAccepted(BaseModel):
    kind: Literal["mutation_accepted"] = "mutation_accepted"
    message_id: str
    session_id: str
    replica_id: str
    accepted_delta_id: str
    assigned_clock: VirtualClock
```

This can be folded into another acknowledgement message if desired.

## Suggested Delta Broadcast Shape

Live and replay deltas should continue to use the authoritative clock.

```python
class GraphDelta(BaseModel):
    delta_id: str
    session_id: str
    origin_replica_id: str
    origin_mutation_seq: int
    origin_generation: int | None = None
    clock: VirtualClock
    caused_by_clock: VirtualClock | None = None
    target_kind: str
    path: str
    payload: dict | None = None
```

Replicas should:

- dedupe by `delta_id`
- preserve or validate same-replica source order using `origin_mutation_seq`
- compare clocks per target
- drop stale updates
- advance their local floor to at least `clock`

## Minimal Flow

### Connect

1. Replica sends `ClockHello`
2. Glial merges any provided clock into the session floor
3. Glial responds with `ClockWelcome(session_clock=...)`
4. Replica advances its local floor

### Local mutation

1. Replica samples or ticks a local clock
2. Replica assigns the next `origin_mutation_seq` and carries forward `origin_generation` when relevant
3. Replica sends a mutating message with `ClockObservation`
4. Glial preserves same-replica source order, merges clocks, and assigns an authoritative session clock
5. Glial persists/broadcasts the delta using that assigned clock
6. All replicas, including the origin, advance their local floor when they observe it

### Idle resync

1. Replica sends `ClockResyncRequest`
2. Glial responds with `ClockResyncResponse`
3. Replica advances its local floor

## Why this is enough for now

This gives us:

- a shared comparable clock on all synchronized deltas
- a simple connect/reconnect floor sync
- no dependency on perfectly ordered transport
- one authoritative place where clocks become final

## Remaining Open Details

These can wait for the SDD:

- exact HLC merge function details
- whether `ClockAdvanced` is needed in practice
- whether heartbeats should carry session clock floors implicitly
- whether every mutation needs a separate acknowledgement or can rely on echoed deltas
