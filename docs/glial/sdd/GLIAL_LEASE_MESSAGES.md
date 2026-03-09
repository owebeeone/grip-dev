# Glial Lease Messages

This appendix defines a minimal first-pass message set for negotiated tap primary ownership.

It is intended to support the lease, ownership, and presence sections of the Glial SDD.

## Assumptions

- Glial server is the central lease authority
- all messages are scoped by `session_id`
- each participant has a `replica_id`
- negotiated primary ownership is per tap
- Glial resolves conflicting requests
- priority may be part of a request, with higher priority winning
- liveness is checked by Glial

## Tap Reference

Each lease message identifies the tap being negotiated.

```python
from typing import Literal
from pydantic import BaseModel, Field


class TapRef(BaseModel):
    home_context_path: str
    tap_type: str
    tap_id: str
```

`tap_id` is the stable tap identity already discussed in the Glial resolutions. `home_context_path` is included because tap ownership is scoped to a specific tap instance in a specific graph position.

## Shared Envelope

```python
class LeaseMessageBase(BaseModel):
    message_id: str
    session_id: str
    replica_id: str
    sent_at_ms: int
    tap: TapRef
```

This is enough for a first pass.

If needed later, the envelope can gain:

- `trace_id`
- `causality_id`
- `claims_hash`

## Client -> Glial Messages

### LeaseRequest

Sent by a replica that wants negotiated primary ownership.

```python
class LeaseRequest(LeaseMessageBase):
    kind: Literal["lease_request"] = "lease_request"
    priority: int = Field(default=0)
    requested_ttl_ms: int = Field(default=60_000)
    reason: str | None = None
```

Notes:

- for now, higher `priority` wins
- `requested_ttl_ms` is advisory; Glial may clamp it

### LeaseRenew

Sent by the current negotiated primary to keep its lease alive.

```python
class LeaseRenew(LeaseMessageBase):
    kind: Literal["lease_renew"] = "lease_renew"
    lease_id: str
    term: int
```

### LeaseRelease

Sent by the current primary when voluntarily giving up ownership.

```python
class LeaseRelease(LeaseMessageBase):
    kind: Literal["lease_release"] = "lease_release"
    lease_id: str
    term: int
    reason: str | None = None
```

### ReplicaHeartbeat

Sent periodically so Glial can track liveness.

```python
class ReplicaHeartbeat(BaseModel):
    kind: Literal["replica_heartbeat"] = "replica_heartbeat"
    message_id: str
    session_id: str
    replica_id: str
    sent_at_ms: int
    active_lease_ids: list[str] = Field(default_factory=list)
```

This is replica-level, not tap-level.

It lets Glial detect disappearance of a negotiated primary even if a lease renew is missed.

## Glial -> Client Messages

### LeaseGranted

Authoritative response granting negotiated primary ownership.

```python
class LeaseGranted(BaseModel):
    kind: Literal["lease_granted"] = "lease_granted"
    message_id: str
    session_id: str
    tap: TapRef
    lease_id: str
    primary_replica_id: str
    term: int
    granted_priority: int
    expires_at_ms: int
    renew_by_ms: int
```

### LeaseDenied

Sent when another replica currently holds primary ownership or a higher-priority request wins.

```python
class LeaseDenied(BaseModel):
    kind: Literal["lease_denied"] = "lease_denied"
    message_id: str
    session_id: str
    tap: TapRef
    requested_replica_id: str
    current_primary_replica_id: str | None = None
    current_lease_id: str | None = None
    current_term: int | None = None
    retry_after_ms: int | None = None
    reason: str
```

### LeaseRenewed

Acknowledges a successful renew.

```python
class LeaseRenewed(BaseModel):
    kind: Literal["lease_renewed"] = "lease_renewed"
    message_id: str
    session_id: str
    tap: TapRef
    lease_id: str
    primary_replica_id: str
    term: int
    expires_at_ms: int
    renew_by_ms: int
```

### LeaseReleased

Acknowledges a voluntary release.

```python
class LeaseReleased(BaseModel):
    kind: Literal["lease_released"] = "lease_released"
    message_id: str
    session_id: str
    tap: TapRef
    lease_id: str
    previous_primary_replica_id: str
    previous_term: int
```

### LeaseRevoked

Authoritative server message indicating that a previously granted lease is no longer valid.

```python
class LeaseRevoked(BaseModel):
    kind: Literal["lease_revoked"] = "lease_revoked"
    message_id: str
    session_id: str
    tap: TapRef
    lease_id: str
    previous_primary_replica_id: str
    previous_term: int
    reason: str
```

Reasons may include:

- `expired`
- `superseded`
- `replica_lost`
- `session_closed`

### PrimaryChanged

Broadcast authoritative ownership change to all replicas in the session.

```python
class PrimaryChanged(BaseModel):
    kind: Literal["primary_changed"] = "primary_changed"
    message_id: str
    session_id: str
    tap: TapRef
    primary_replica_id: str
    mode: Literal["origin-primary", "negotiated-primary"]
    lease_id: str | None = None
    term: int
    effective_at_ms: int
```

This is the most important broadcast for followers.

Followers use this message to decide whether they should execute the tap or wait for replicated outputs.

### ReplicaLost

Broadcast when Glial detects a replica is gone.

```python
class ReplicaLost(BaseModel):
    kind: Literal["replica_lost"] = "replica_lost"
    message_id: str
    session_id: str
    replica_id: str
    detected_at_ms: int
```

This is useful for debugging and for any higher-level recovery logic.

## Suggested Union

```python
LeaseClientMessage = LeaseRequest | LeaseRenew | LeaseRelease | ReplicaHeartbeat

LeaseServerMessage = (
    LeaseGranted
    | LeaseDenied
    | LeaseRenewed
    | LeaseReleased
    | LeaseRevoked
    | PrimaryChanged
    | ReplicaLost
)
```

## Minimal Flow

### Acquire negotiated primary

1. Replica sends `LeaseRequest`
2. Glial compares against current owner and competing requests
3. Glial sends `LeaseGranted` or `LeaseDenied`
4. Glial broadcasts `PrimaryChanged` when ownership changes

### Keep ownership

1. Primary sends `LeaseRenew`
2. Glial replies with `LeaseRenewed`
3. Replica also keeps sending `ReplicaHeartbeat`

### Voluntary release

1. Primary sends `LeaseRelease`
2. Glial replies with `LeaseReleased`
3. Glial broadcasts `PrimaryChanged` if ownership falls back or transfers

### Lost primary

1. Glial stops receiving renewals and/or heartbeats
2. Glial emits `LeaseRevoked`
3. Glial broadcasts `ReplicaLost`
4. Glial broadcasts `PrimaryChanged` to the fallback owner, typically the origin primary if present

## Remaining Implementation Details

This message set still leaves a few implementation details open:

- whether headless replicas should request shorter TTLs by policy
- whether `PrimaryChanged` is enough or whether followers also need a full tap-role sync message
- whether origin-primary fallback should happen immediately or after a grace period

## First-Pass Defaults

Use these defaults for v1 unless the implementation plan changes them:

- default lease TTL: `60_000ms`
- renew by: `40_000ms`
- replica heartbeat cadence: `15_000ms`
- liveness timeout: `45_000ms`

Tie-break defaults:

- higher priority wins
- equal priority keeps the incumbent primary
- if there is no incumbent, first accepted request wins
- final tie-break is lexical `replica_id`
