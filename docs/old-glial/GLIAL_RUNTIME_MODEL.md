# GLIAL Runtime Model (Draft)

## 1. Purpose

Define a concrete runtime mental model for Glial focused on the demanding target:

- highly concurrent server-side synchronization (many sessions, many graphs)
- async-first Drip behavior
- browser + backend + agent co-participation in one distributed graph

This is a runtime/behavior spec, not an API surface freeze.

## 2. Design Targets

1. Maximize throughput and parallelism without losing per-grip determinism.
2. Keep the Reactor a state broker (routing, ordering, ACL, fanout), not business-logic runtime.
3. Make slow subscribers non-catastrophic.
4. Support multi-session shared state (Google Docs/Firebase-like behavior).
5. Keep PySide6 integration possible, but optimize first for Glial server-side scale.

## 2.1 Kernel Invariants and Non-Goals

Glial is a synchronization kernel for Grip/Grok instances. Its job is to keep distributed graph state in sync, and not to execute application domain behavior.

Invariants:

1. Glial responsibilities are limited to routing, ordering, fanout, ACL checks, versioning, and sync/replay.
2. Glial does not execute business logic, domain validation, workflow decisions, or external side effects.
3. Application-specific `grip-py` taps/providers own domain logic and all IO (DB/API/LLM/tool calls).
4. Providers publish results (`state`, `status`, `error`, `progress`) back to the graph; Glial only synchronizes these updates.
5. Any behavior that can mutate external systems must be implemented outside the Reactor path and invoked through provider-side command handling.

Non-goals:

1. Reactor-hosted domain rule evaluation.
2. Reactor-managed transactional DB workflows.
3. Embedding product-specific orchestration logic into Glial core.

## 3. Runtime Mental Model

Glial is an evented graph fabric with explicit ownership and ordering boundaries.

- **Relay**: stateless websocket/http gateway, auth, sticky routing to Reactor shard.
- **Reactor**: authoritative graph runtime for a partition of `GraphID`s.
- **Clients**: browser, backend provider, agent. Same protocol; different capabilities.
- **Graph**: scoped key-value + stream graph hosted by exactly one Reactor at a time.

A `GraphID` is pinned to one Reactor (via registry) to avoid split-brain writes.

## 4. Core Identity and Scope Model

Each mutation/event is tagged with:

- `graph_id`
- `scope` (`session:{id}`, `user:{id}`, `doc:{id}`, `global`)
- `grip`
- `actor_id` (browser/backend/agent/service)
- `seq` (monotonic sequence within the owning Drip)
- `trace_id` (optional for observability)

Recommended scope semantics:

- `session:*`: ephemeral per connection/session state
- `user:*`: durable user model state
- `doc:*`: collaborative shared document/workspace state
- `global`: system-wide readonly or controlled writes

## 5. Drip Concurrency Contract

### 5.1 Why `Drip.next` should not be a blocking barrier

For Glial throughput, publishing and callback completion must be decoupled.
If `next` waits for all subscribers (`await gather(...)`) every time, one slow subscriber throttles the whole graph.

### 5.2 Proposed publish APIs

Use two publish paths:

- `next(value)` (sync): enqueue publish, return immediately (fast path)
- `next_threadsafe(value)` (sync): enqueue from non-loop thread safely
- `flush(seq: int | None = None)` (async): barrier when caller explicitly needs delivery completion up to sequence

This keeps ingestion fast while still supporting correctness points that need acknowledgement.

### 5.3 Ordering guarantees

- Per Drip: total order by `seq`
- Cross Drip: no global order guarantee
- Per Graph tick: coalescing may drop intermediate values for the same grip when configured

### 5.4 Async subscriber execution model

Async callbacks are dispatched concurrently by default (task fanout), but publish does not wait.

If a caller needs "all callbacks completed", it calls `await flush(seq)`.

## 6. Slow Subscriber Policy (Required Configuration)

`subscribe_async` must be parameterized; one policy is not enough.

Suggested policy fields:

- `mode`: `latest | serial | concurrent`
- `queue_size`: int (default 1)
- `overflow`: `drop_oldest | drop_newest | error` (default `drop_oldest`)
- `max_in_flight`: int (used by `concurrent`)
- `on_error`: `log_continue | propagate | collect` (default `log_continue`)

Recommended default:

- `mode=latest`
- `queue_size=1`
- `overflow=drop_oldest`
- `on_error=log_continue`

Behavior for "new value arrives before callback completes":

- `latest`: keep only newest pending value (coalescing)
- `serial`: queue in order (subject to queue_size)
- `concurrent`: run multiple callback instances up to `max_in_flight`

## 7. Reactor Event-Loop Model

- Reactor runs one asyncio loop per process.
- Internal work is actor/mailbox style: operations become commands on per-graph queues.
- Concurrent inbound writes are serialized at graph command queue boundary.
- Fanout and network sends are async tasks; bounded buffers protect loop health.

This model gives deterministic graph mutation order without blocking network IO.

## 8. Should async subscribers run "in parallel with gather"?

Yes for execution, no for default publish barrier.

- Execution: create tasks for eligible async subscribers immediately (parallel progress).
- Barrier: only when explicitly requested (`flush`), then await completion.

This preserves maximal parallelism and avoids turning each write into a global sync point.

## 9. Deployment Model for Grok/Glial

Recommended default:

- many session graphs per Reactor process
- shard by `GraphID`
- sticky routing via Relay + registry

Avoid defaulting to one container/process per session. Reserve it for strict isolation tenants or known noisy neighbors.

Benefits of multi-session Reactor:

- better CPU/memory utilization
- shared connection infrastructure
- lower ops overhead

Risks and mitigations:

- noisy neighbors -> per-tenant quotas, optional isolation class
- hotspot docs -> shard/migrate by graph affinity

## 10. Database Access Model

For Glial principles, keep DB/IO in provider clients (backend taps), not Reactor.

- Reactor: routing, ordering, ACL, replication, snapshotting
- Provider: business logic + DB/API calls

Provider processes should use async pooled DB access:

- per-process connection pool
- bounded concurrency
- idempotency keys on writes
- retries with backoff for transient failures

Optional optimization later:

- colocated provider worker in same pod/host as Reactor for latency, while preserving logical boundary.

## 11. Multi-Session Sharing Model (Firebase-like)

Use shared `doc:{doc_id}` scopes as collaboration anchor.

- writes are operations/events, not blind full-state overwrites for high-frequency paths
- Reactor assigns order and version
- clients apply updates reactively
- persistence: append op-log + periodic snapshots

Minimum model for v1:

- optimistic local update + server ack/version
- conflict policy per grip (LWW for simple values, operation merge for collaborative types)
- presence grips (`doc.presence.*`) for awareness

## 12. Agent Model

Treat agent as first-class actor (like browser/backend):

- own `actor_id`, auth principal, ACL envelope
- can subscribe to session/user/doc scopes
- can propose or apply writes based on policy
- all writes auditable with actor metadata

This keeps human and AI interactions in the same graph semantics.

## 13. Failure and Recovery

- Provider disconnect: affected grips marked `stale` with status update.
- Reactor restart: restore graph from latest snapshot + op-log tail.
- Backpressure breach: apply overflow policy; emit metrics and warnings.
- Network partition: reconnect with last seen version, replay delta/snapshot.

## 14. Observability Requirements

Must-have metrics:

- publish rate, fanout rate, dropped events
- per-subscriber lag and queue depth
- callback duration distribution
- flush latency percentiles
- graph command queue depth
- websocket send backlog

Must-have tracing fields:

- `graph_id`, `scope`, `grip`, `actor_id`, `seq`, `trace_id`

## 15. Recommended V1 Decisions

1. Keep `next`/`next_threadsafe` as non-blocking enqueue APIs.
2. Add `flush(seq)` for explicit barrier semantics.
3. Implement `subscribe_async` with configurable policy (`mode`, overflow, error handling).
4. Reactor remains IO-free; backend providers perform DB/API calls with pools.
5. Shard many graphs per Reactor; avoid per-session container default.
6. Introduce `doc:*` scope and op-log+snapshot for shared collaboration.
7. Model agent as authenticated actor with ACL and audit trail.

## 16. Open Questions for Next Pass

1. Do we need per-grip configurable durability (memory-only vs persisted op-log)?
2. Which grips require strict serial subscriber mode by default?
3. Should `flush` wait for local subscribers only, or also downstream network delivery ACKs?
4. Do we adopt CRDTs for specific collaborative grip types in v1, or defer to v2?
5. What are initial quota defaults (writes/sec, queued callbacks, max in-flight)?
