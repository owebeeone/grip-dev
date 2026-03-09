# Glial SDD Section 10: Gateway Router And Shards

## Recommended Deployment Shape

This section applies only to sessions that are attached to Glial.

The recommended Glial deployment is:

1. public edge load balancer
2. Glial gateway/router pool
3. internal Glial shard pool
4. session directory
5. durable session state store

## Why This Shape

This structure is recommended because:

- browsers need one stable public origin
- shard topology should remain internal
- one session must be pinned to one authoritative shard at a time
- session routing needs Glial awareness, not generic round-robin only

## Edge Load Balancer

The public edge load balancer is responsible for:

- TLS termination or forwarding, depending on deployment policy
- distributing new incoming traffic across Glial gateways
- keeping the public origin stable

The edge load balancer does not need to know Glial session ownership.

## Glial Gateway/Router

The gateway/router is the public application-layer entry point for Glial traffic.

Responsibilities:

- accept browser and replica connections
- receive already-authenticated identity or claims from the host environment
- extract `session_id`
- consult the session directory
- proxy the connection to the owning shard
- create a new shard assignment if no owner exists

The gateway/router may terminate WebSockets and proxy to an internal shard connection, or it may tunnel other transport forms. The browser only sees the stable public gateway origin.

## Shards

A shard is the authoritative owner for a set of sessions.

Responsibilities:

- session clock floor maintenance
- authoritative delta acceptance
- lease ownership and presence tracking
- snapshot generation
- replay window management
- live delta fanout

Every session is owned by exactly one shard at a time.

## Session Directory

The session directory maps:

`session_id -> shard_id`

Required properties:

- fast lookup
- atomic update on first assignment or failover
- shared visibility across gateways

The session directory is a control-plane dependency, not a browser-visible component.

## Durable State Store

The durable state store holds:

- recent snapshots
- replay state within the replay window
- enough durable session state to recover after shard loss

The exact storage implementation is not mandated by this SDD.

## Browser Recommendation

Browsers should connect to a stable Glial origin only when the session is using Glial.

Recommended pattern:

- browser connects to `/glial` on one stable public hostname
- gateway/router internally routes to the owning shard

This avoids:

- CORS complexity
- exposing shard topology to clients
- shard-aware reconnect logic in the browser

For local-only persistence, the browser does not connect to Glial and no router or shard path exists.

## Session Routing Rules

On first connect for a session:

1. gateway looks up `session_id`
2. if missing, gateway selects a shard
3. gateway writes the session directory entry
4. gateway proxies the session to that shard

On reconnect:

1. gateway looks up existing `session_id -> shard_id`
2. gateway proxies to that shard

On shard loss:

1. session directory entry is invalidated or replaced
2. reconnecting clients are routed to a new shard
3. new shard restores from durable state
4. clients recover through snapshot and replay rules

## Transport Independence

Glial’s logical protocol must tolerate lossy, duplicated, and out-of-order delivery.

That means the transport layer may evolve independently:

- WebSocket
- hanging GET or streaming HTTP
- future unreliable datagram-based transport

The gateway/router hides those transport details from the shard ownership model.
