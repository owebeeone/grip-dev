# Glial Implementation Plan Phase 04: Glial Server Coordination

## Testing Plan

- add unit tests for authoritative clock assignment, including skew bound behavior
- add unit tests for lease grant, renew, revoke, and fallback behavior
- add snapshot and replay tests, including replay-window miss and `SyncReset`
- add integration tests against a local FastAPI-based Glial test server using HTTP and WebSocket transports
- add multi-client integration tests with duplicated, lost, and out-of-order delivery
- add shard recovery tests proving snapshots and replay state are sufficient for reconnect
- add end-to-end tests with one browser-like client and one Python headless client sharing a session
- add remote-session-catalog tests proving sessions are listed and loaded by authenticated user identity plus `glial_session_id`
- add remote backup tests proving source-state backups can be stored and reloaded without inventing a detached fork

## Goal

Implement the Glial server-side coordination layer described by the SDD.

This phase delivers the first working Glial service for shared sessions.

## Scope

- authoritative session clock assignment
- snapshot generation and replay windows
- session directory abstraction
- Glial lease and presence handling
- live delta fanout
- share-local-session session creation path
- durable server-side snapshot and replay backing store
- remote state storage adapter keyed by authenticated user identity and `glial_session_id`
- remote session catalog and lookup

## Expected Code Areas

- new `glial-router-py` package or service code in this repository
- routing and shard ownership code
- lease and clock processing code
- durable server-side snapshot and replay storage integration
- FastAPI server entry points and local integration test harness

## Work Items

1. Implement session ownership and authoritative clock handling.
2. Implement snapshot plus replay flows from the SDD message docs.
3. Implement lease and presence handling for negotiated primaries.
4. Implement durable snapshot and replay retention.
5. Implement the authenticated remote state storage adapter for backup and session catalog access.
6. Implement the first FastAPI-based gateway or routing entry point for shared sessions.
7. Provide a local test-server harness that Phase 05 client integration tests can reuse.
8. Validate interop with Phase 04 clients.

## Exit Criteria

- clients can share a session through one authoritative Glial service
- server clocks, replay, and reset behavior match the SDD
- negotiated-primary ownership works for taps that need it
- authenticated users can list and load remote sessions by `glial_session_id`
- remote backup storage exists alongside live shared-session routing
- reconnect and shard-loss recovery are correct at the protocol level

## Non-Goals

- production deployment hardening beyond the agreed v1 topology
- non-JavaScript or non-Python client support
- post-SDD delta-engine replacement for large JSON blobs
