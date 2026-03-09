# Glial SDD Section 09: Lease And Presence

## Overview

Glial is the central lease authority for negotiated-primary taps.

Lease management is server-mediated and authoritative. Replicas do not negotiate ownership peer-to-peer.

## Required Messages

The v1 control-plane message families are:

- `LeaseRequest`
- `LeaseRenew`
- `LeaseRelease`
- `ReplicaHeartbeat`
- `LeaseGranted`
- `LeaseDenied`
- `LeaseRenewed`
- `LeaseReleased`
- `LeaseRevoked`
- `PrimaryChanged`
- `ReplicaLost`

## Lease Flow

### Request

1. Replica sends `LeaseRequest`
2. Glial evaluates current owner, priority, and liveness
3. Glial responds with `LeaseGranted` or `LeaseDenied`
4. If ownership changes, Glial broadcasts `PrimaryChanged`

### Renew

1. Current negotiated primary sends `LeaseRenew`
2. Glial verifies the lease is still valid
3. Glial responds with `LeaseRenewed`

### Release

1. Current negotiated primary sends `LeaseRelease`
2. Glial acknowledges with `LeaseReleased`
3. Glial broadcasts `PrimaryChanged` if ownership falls back or transfers

### Revoke

Glial sends `LeaseRevoked` when:

- the lease expires
- the replica is lost
- a higher-priority request supersedes the current owner
- the session closes

## Presence Detection

Replicas send `ReplicaHeartbeat` at the replica level.

Heartbeats are used for:

- liveness detection
- identifying lost negotiated primaries
- accelerating fallback when renewals alone are insufficient

## Default Timing

V1 defaults:

- lease TTL: `60_000ms`
- renew by: `40_000ms`
- replica heartbeat cadence: `15_000ms`
- liveness timeout: `45_000ms`

These values favor low control-plane chatter over aggressive failover.

Shorter requested lease TTLs are allowed, especially for headless or specialized replicas.

## Conflict Resolution

Default conflict rules:

- higher priority beats lower priority
- equal priority keeps the incumbent primary
- if there is no incumbent, first server-accepted request wins
- final tie-break is lexical `replica_id`

## Fallback Behavior

When a negotiated primary is lost:

- Glial revokes the negotiated lease
- Glial broadcasts `ReplicaLost`
- Glial broadcasts `PrimaryChanged`
- the origin primary resumes immediately if still present

V1 does not add an extra grace period after lease expiry or liveness failure.

## Role Synchronization

In v1, `PrimaryChanged` is sufficient as the authoritative ownership broadcast.

Replicas do not require a second full tap-role synchronization message before switching local runtime behavior.

## Security Constraint

Negotiated ownership is only valid within the existing authenticated claims envelope for the session.

Lease transfer must never create a privilege change.
