# Glial SDD Section 03: System Topology

## Overview

Glial is deployed as a routed, sharded coordination service rather than as a single monolith directly exposed to browsers.

This deployment only applies when a session is attached to Glial.

The default local-only persistence topology is:

1. one browser or runtime replica
2. one local persistence store, typically IndexedDB in browsers
3. no gateway, shard, or network coordination path

The recommended v1 topology is:

1. public edge load balancer
2. Glial gateway/router pool
3. internal Glial shard pool
4. session directory
5. durable session state store

## Participants

### Browser Replicas

Browser replicas connect to a stable public Glial origin when the session uses Glial. They should not know about shard topology or internal hostnames.

If the session is local-only, the browser does not connect to Glial and restores from its local persistence store.

### Headless And AI Replicas

Headless and AI-capable replicas connect using the same session model. They may participate as followers, origin primaries, or negotiated primaries depending on the tap ownership mode.

## Gateway/Router

The Glial gateway/router is the public-facing application layer for Glial traffic.

Responsibilities:

- accept incoming WebSocket or HTTP-based Glial traffic
- receive authenticated identity or claims from the host environment
- extract `session_id`
- look up the owning shard for that session
- create a new shard assignment if needed
- proxy or tunnel the connection to the owning shard

The gateway/router is Glial-aware. A generic L4 or L7 load balancer alone is not sufficient because one session must be pinned to one authoritative shard at a time.

## Shards

A shard is the authoritative Glial runtime for a set of sessions.

Shard responsibilities:

- maintain the session clock floor
- assign authoritative clocks to accepted deltas
- coordinate leases and primary ownership
- maintain replay windows
- build and serve snapshots
- broadcast live deltas

At any moment, one session has exactly one authoritative shard owner.

## Session Directory

The session directory maps:

`session_id -> shard_id`

It is used by the gateway/router to send all traffic for a session to the correct shard.

The session directory may be backed by Redis or another small durable coordination store.

## Durable Session State Store

Glial requires durable storage for at least:

- recent snapshots
- enough replay state to support reconnect
- shard recovery after failure

This store may be implemented separately from the session directory.

## External And Internal Boundaries

Recommended boundary model:

- browsers talk only to the public Glial origin
- gateways are public or edge-adjacent
- shards are internal-only
- durable stores are internal-only

This structure avoids browser CORS and topology problems while keeping shard ownership and routing internal to Glial.
