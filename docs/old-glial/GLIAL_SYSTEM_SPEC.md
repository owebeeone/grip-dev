# GLIAL System Specification

Status: Draft  
Version: 0.1  
Date: 2026-03-08  
Scope: Glial kernel and protocol contract for synchronizing distributed Grip/Grok runtimes

## 1. Purpose [Informative]

This document is the single implementation authority for Glial v1.

It consolidates:

- runtime/kernel constraints from `GLIAL_RUNTIME_MODEL.md`
- concrete workload behavior from `GLIAL_USE_CASES.md`
- high-level intent from `System Design_ Glial.md`

Where this spec conflicts with older docs, this spec wins.

## 2. Normative Language [Normative]

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as requirement levels.

## 3. System Boundaries [Normative]

### 3.1 Core Boundary

Glial is a synchronization kernel (Grip router + state broker). It MUST keep distributed graph state in sync and MUST NOT execute application business logic.

### 3.2 Glial Responsibilities

Glial MUST provide:

1. Connection handling, routing, and shard ownership.
2. Per-graph event ordering and fanout.
3. Access control enforcement for read/write/execute classes.
4. Versioning, event log, snapshot/replay.
5. Subscription lifecycle and provider availability signaling.
6. Backpressure handling and quota enforcement.

### 3.3 Non-Goals

Glial MUST NOT:

1. Execute domain validation or workflow rules.
2. Execute DB/API/LLM external side effects.
3. Host product-specific orchestration logic.
4. Guarantee distributed transactions across external systems.

Business logic and side effects MUST live in application-specific provider taps (for example `grip-py` providers).

## 4. Runtime Topology [Normative]

### 4.1 Components

1. Relay: stateless ingress, auth, sticky routing.
2. Reactor: authoritative host for active GraphIDs.
3. Clients: browser, backend provider, and agent clients using the same protocol.
4. Registry: shard map `GraphID -> Reactor`.

### 4.2 Graph Ownership

Each `GraphID` MUST have exactly one active Reactor owner at any point in time.

### 4.3 Sharding Default

The default deployment MUST run many GraphIDs per Reactor process and shard by `GraphID`. Per-session process/container isolation MAY be used only for strict tenant isolation or noisy-neighbor mitigation.

## 5. Identity, Scopes, and Events [Normative]

### 5.1 Required Event Metadata

Every mutation/event MUST include:

- `graph_id`
- `scope`
- `grip`
- `actor_id`
- `seq` (monotonic per grip stream)
- `event_id` (idempotency key)
- `ts` (server-assigned timestamp)
- `trace_id` (optional but SHOULD be present in production)

### 5.2 Scope Classes

Supported scope classes:

1. `session:{id}`: ephemeral session/UI state.
2. `user:{id}`: durable user-level state.
3. `doc:{id}`: collaborative shared document/workspace state.
4. `global`: system-level state.

### 5.3 Scope Precedence

When the same logical setting exists in multiple scopes, precedence MUST be:

1. `session:*` override
2. `user:*` baseline
3. `global` default

## 6. Drip and Publish Semantics [Normative]

### 6.1 Publish APIs

The kernel publish API MUST support:

1. `next(value)`: synchronous non-blocking enqueue.
2. `next_threadsafe(value)`: synchronous enqueue from non-loop thread.
3. `flush(seq: int | None = None)`: async barrier up to sequence.

`next` MUST NOT block on subscriber callback completion.

### 6.2 Ordering Guarantees

1. Per grip stream: total order by `seq`.
2. Cross grip streams: no global order guarantee.
3. Tick coalescing MAY collapse multiple updates to the same grip in one tick to final value.

### 6.3 Async Subscriber Policy

`subscribe_async` MUST accept a policy with:

- `mode`: `latest | serial | concurrent`
- `queue_size` (int)
- `overflow`: `drop_oldest | drop_newest | error`
- `max_in_flight` (for `concurrent`)
- `on_error`: `log_continue | propagate | collect`

Default policy MUST be:

- `mode=latest`
- `queue_size=1`
- `overflow=drop_oldest`
- `on_error=log_continue`

### 6.4 Parallel Execution

Async subscribers SHOULD be started concurrently. Publish completion MUST remain decoupled from callback completion unless caller explicitly waits via `flush`.

## 7. Data Synchronization Model [Normative]

### 7.1 Value vs Operation

1. Low-frequency scalar state MAY sync as value replace.
2. High-frequency collaborative state MUST sync as operations/deltas.

### 7.2 Document Collaboration (Use Case 1)

For sectioned JSON document collaboration, v1 MUST use a versioned operation log based on JSON Patch semantics.

Operation envelope MUST include:

- `doc_id`
- `base_version`
- `op_id`
- `actor_id`
- `ops[]`

Reactor MUST:

1. Validate ACL and version preconditions.
2. Apply operation in authoritative order.
3. Increment and emit `doc.version`.
4. Fanout op result to subscribers.

### 7.3 Conflict Policy

Default conflict policy MUST be:

1. Structured fields: order-based last-writer-wins.
2. Specialized high-contention fields MAY define custom merge policy.

CRDT-backed field types MAY be added later without changing core routing semantics.

## 8. Persistence and Recovery [Normative]

### 8.1 Write-Behind Persistence

Persistence MUST run as write-behind workers outside Reactor business logic.

Required behavior:

1. Debounce window per entity/path.
2. Max flush interval under continuous updates.
3. Coalescing by `(entity_id, field/path)`.
4. Graceful shutdown flush.

### 8.2 Default Cadence

Default persistence cadence:

1. Simple settings: debounce `500ms`, max flush `5s`.
2. Shared docs/workflow state: debounce `2s`, max flush `10s`.

### 8.3 Durable Artifacts

For collaborative document scopes, persistence MUST store:

1. Append-only op log.
2. Periodic snapshots.

Recovery MUST restore latest snapshot then replay op-log tail.

### 8.4 Idempotency

All externally persisted writes SHOULD be idempotent by `event_id`/`op_id`.

## 9. Provider (Tap) Contract [Normative]

### 9.1 Provider Role

Providers are the only components that MAY execute IO or domain logic.

### 9.2 Command vs State

Application design MUST separate:

1. Command grips for intent/side-effect triggers.
2. State grips for current/derived state.

Providers MUST emit explicit result grips for success/error/progress.

### 9.3 Availability Signaling

If a provider disconnects, Reactor MUST publish status transitions for affected grips (for example `live -> stale`).

## 10. AI Agent Runtime Model [Normative]

### 10.1 Agent as First-Class Actor

Agents MUST be represented as authenticated actors with explicit `actor_id` and ACL policy envelope.

### 10.2 Action Classes

Agent writes/actions MUST be classified:

1. `observe`
2. `suggest`
3. `apply_local`
4. `execute_external`

Default policy SHOULD require approval for `execute_external`.

### 10.3 Lifecycle

Default lifecycle SHOULD be on-demand with warm TTL.

Always-on agents MAY be enabled for specific premium or operational workflows.

### 10.4 Audit

All agent-originated writes MUST be auditable with actor identity and trace metadata.

## 11. Security and Multi-Tenancy [Normative]

### 11.1 ACL

ACL MUST be enforced at Reactor on every mutation and subscription.

### 11.2 Tenant Isolation

Quota controls MUST exist for:

1. writes/sec
2. queue depth
3. max in-flight callbacks
4. websocket fanout backlog

### 11.3 Enterprise Sharing

Cross-user/workflow sharing MUST be explicit and policy-gated. Default MUST be deny.

## 12. Protocol Surface (V1) [Normative]

### 12.1 Required Message Classes

1. `SUBSCRIBE`
2. `UNSUBSCRIBE`
3. `PROVIDE`
4. `UNPROVIDE`
5. `NEXT_VALUE`
6. `NEXT_OP`
7. `STATUS`
8. `ACK`
9. `ERROR`
10. `HEARTBEAT`

### 12.2 Delivery Semantics

1. At-least-once delivery for network messages.
2. Deduplication by `event_id`/`op_id` at receiver.
3. Reconnect with last seen version to receive delta replay or snapshot+tail.

## 13. Use Case Mapping [Normative]

### 13.1 Use Case 1: Shared Sectioned Document

MUST use operation sync with version checks and op-log+snapshot durability.

### 13.2 Use Case 2: Shared Theme Setting

MUST use value sync plus upsert persistence with write-behind.

### 13.3 Use Case 3: OCR and Form Co-Editing

Session UI grips MUST remain ephemeral by default. Durable writes MUST occur only through provider command handling.

### 13.4 Use Case 4: Dynamic Agentic Workflow

Workflow schema/state/scratchpad MUST be policy-scoped and auditable. External actions MUST pass action-class gating.

## 14. Observability and Operability [Normative]

### 14.1 Required Metrics

1. publish rate
2. fanout rate
3. dropped event count
4. subscriber lag and queue depth
5. callback latency distribution
6. flush latency
7. graph command queue depth
8. websocket send backlog

### 14.2 Required Tracing Dimensions

Tracing MUST include `graph_id`, `scope`, `grip`, `actor_id`, `seq`, `event_id`, and `trace_id` where available.

### 14.3 Replay Tooling

Operations tooling MUST support snapshot+tail replay for deterministic incident reconstruction.

## 15. V1 Milestones [Informative]

1. Implement settings path end-to-end (Use Case 2).
2. Implement sectioned document op-log path (Use Case 1).
3. Implement OCR/form shared validation loop (Use Case 3).
4. Implement bounded subset of dynamic workflow (Use Case 4).

## 16. Open Decisions [Normative Pending]

The following remain unresolved and MUST be decided before v1 freeze:

1. Whether `flush` includes network delivery acknowledgment or only local completion.
2. Snapshot cadence defaults by workload type.
3. Per-grip durability classes and default assignments.
4. Initial tenant quota defaults.
5. Exact ACL matrix for user, support, backend, and agent actors.

