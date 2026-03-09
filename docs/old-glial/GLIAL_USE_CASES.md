# GLIAL Use Cases (Draft)

## 1. Purpose

Capture concrete, high-value Glial use cases with explicit runtime behavior:

- what is synchronized
- how updates are represented (value vs operation)
- how backend persistence works (including rate limiting)
- where AI agents participate

This document complements the runtime model in `GLIAL_RUNTIME_MODEL.md`.

## 2. Cross-Cutting Rules

1. Reactor is authoritative for ordering and fanout, not business logic.
2. Backend provider clients perform IO (DB/API/LLM).
3. Writes are tagged with `graph_id`, `scope`, `grip`, `actor_id`, `seq`, `trace_id`.
4. For high-frequency shared state, sync operations/deltas instead of full objects.
5. Persistence uses write-behind with debounce + max-latency flush.

## 3. Known Shared-Document Mechanisms (Use Case 1 foundation)

### 3.1 OT (Operational Transform)

- Used historically in collaborative editors.
- Good for text collaboration with central server transform logic.
- Implementation complexity is moderate/high.

### 3.2 CRDT (Conflict-free Replicated Data Types)

- Examples: Yjs, Automerge.
- Strong convergence properties in distributed/offline scenarios.
- Excellent for eventually-consistent multi-writer collaboration.
- Payload and model complexity can be higher.

### 3.3 JSON Patch + Versioned Op Log (recommended v1 for structured JSON docs)

- RFC 6902 operations (`add`, `replace`, `remove`, etc.).
- Reactor orders operations and returns authoritative version.
- Simple projection path into Pydantic/dataclass backend models.
- Good fit when the document is sectioned JSON, not rich-text CRDT-first.

Recommended v1 path: JSON Patch op log now, with CRDT-ready abstraction boundary for later upgrade.

## 4. Use Case 1: Shared Sectioned Document

### 4.1 Scenario

A shared document is a JSON tree where each section is a node. Multiple actors edit concurrently. Small edits should not send the full document.

### 4.2 Canonical graph model

- Scope: `doc:{doc_id}`
- Grips:
  - `doc.version` (int)
  - `doc.snapshot` (optional periodic full snapshot)
  - `doc.op` (stream of operations)
  - `doc.section.{section_id}` (materialized section values)

### 4.3 Write path

1. Client generates op message with `base_version`.
2. Reactor validates ACL and version precondition.
3. Reactor applies op(s), increments `doc.version`, emits authoritative op event.
4. All subscribers receive op + version and update local projection.

Example op payload:

```json
{
  "doc_id": "D123",
  "base_version": 41,
  "op_id": "01H...",
  "actor_id": "session:S1",
  "ops": [
    {"op": "replace", "path": "/sections/intake/title", "value": "Updated title"}
  ]
}
```

### 4.4 Backend model sync (Pydantic/dataclass)

Backend provider keeps a materialized model:

1. Subscribe to `doc.op` stream.
2. Apply operations to in-memory model projection.
3. If version gap detected, fetch latest snapshot + replay tail ops.

### 4.5 Persistence strategy (rate-limited)

- Debounce flush: every `X=2s` after last mutation.
- Max flush interval: `10s` even under continuous edits.
- Persist both:
  - append-only op log (`doc_id`, `version`, `op`, metadata)
  - periodic snapshot (every N ops or every M seconds)

This minimizes DB writes while preserving recovery and auditability.

### 4.6 Conflict policy

- Structured fields: last-writer-wins at operation order boundary.
- Hot collaborative text regions: candidate for CRDT-backed section type later.

## 5. Use Case 2: Simple Persistent Shared Field (Theme Setting)

### 5.1 Scenario

A user or AI agent updates UI theme (`day/night`). Change should be shared to all active client instances for that user/session and persisted.

### 5.2 Canonical model

- Durable source: `user:{user_id}.settings.theme`
- Optional session override: `session:{session_id}.ui.theme_override`

### 5.3 Write path

1. Actor writes new theme value.
2. Reactor validates write authority.
3. Reactor fanouts update to subscribers (all tabs/devices in scope).
4. Backend provider upserts durable setting.

### 5.4 Persistence strategy (rate-limited)

- Debounce flush: `X=500ms`.
- Max flush interval: `5s`.
- DB operation: `UPSERT user_settings(user_id, theme, updated_at)`.

### 5.5 Why rate limiting still matters here

Even simple toggles can flap quickly (agent experimentation, rapid UI interaction); write-behind avoids unnecessary DB churn.

## 6. Use Case 3: OCR -> Agent/UI Co-Editing -> Submit -> Shared Validation

### 6.1 Scenario

User uploads scanned client form. Agent extracts data, navigates UI to "new client" form, pre-fills fields. User and agent can both correct validation errors before submit.

### 6.2 Scope split

- Session-only UI state:
  - `session.ui.route`
  - `session.form.new_client.prefill`
  - `session.form.new_client.errors`
  - `session.form.new_client.submit_status`
- Durable domain state:
  - `user/domain.client.{client_id}` (created on successful submit)

### 6.3 Flow

1. User uploads PDF -> `session.upload.current_file`.
2. OCR/LLM provider consumes file and emits structured candidate object.
3. Agent writes:
  - route change (`session.ui.route = "/clients/new"`)
  - prefill object (`session.form.new_client.prefill = {...}`)
4. UI renders prefill.
5. User or agent triggers submit command.
6. Backend validates and writes success/error grips.
7. Both user UI and agent observe identical validation state.

### 6.4 Persistence

- Session grips are ephemeral (not persisted by default).
- Durable write occurs on successful submit into domain DB tables.
- Optional audit trail records agent-proposed vs user-edited fields.

## 7. Use Case 4: Agentic Dynamic Workflow Page (Holy Grail)

### 7.1 Scenario

Per-user/per-enterprise workflow with custom fields, AI recommendations, and action orchestration (email/calendar/tasks). Route includes selected client and workflow.

### 7.2 Canonical model

- Workflow schema: `workflow:{workflow_id}.schema` (durable)
- Client workflow instance state: `workflow:{workflow_id}.client:{client_id}.state` (durable + reactive)
- Agent scratchpad: `workflow:{workflow_id}.user:{user_id}.agent_state` (durable, policy-controlled)
- Route grip: `session.ui.route = "/workflow/{workflow_id}/client/{client_id}"`

### 7.3 Flow

1. AI or user selects workflow + client.
2. Client subscribes to workflow schema and current instance state.
3. UI renders dynamic form/components from schema grips.
4. AI publishes recommended actions (`send_email`, `schedule_meeting`, etc.) as structured proposals.
5. User accepts/edits/rejects actions.
6. Approved actions execute via backend providers; status flows back into graph.

### 7.4 Persistence and sharing

- Schema and workflow state use write-behind persistence (e.g., `X=1-2s`, `max=10s`).
- Enterprise controls determine who can read/clone/share workflows.
- Actions are auditable (`who proposed`, `who approved`, `who executed`).

## 8. Additional Complex Use Cases

### 8.1 Multi-User + Agent Co-Pilot on the Same Record

- Multiple humans + agent edit a case file simultaneously.
- Human approval required for external side effects.
- Full actor-attributed audit log and replay.

### 8.2 Long-Running Agent Plans with Interrupt/Resume

- Agent executes multi-step workflow over minutes/hours.
- Plan state stored in graph grips + durable checkpoints.
- User can pause, modify step N, then resume from checkpoint.

### 8.3 Cross-Session Presence + Handover

- Support/manager "mounts" live user graph.
- Presence grips indicate who is watching/editing.
- Handover protocol transfers control without losing state.

### 8.4 Offline/Intermittent Client Reconciliation

- Client queues local ops while offline.
- Reconnect performs version sync and op replay.
- Conflicts resolved by policy (LWW, reject/rebase, or CRDT section type).

### 8.5 Policy-Guarded Enterprise Skill Sharing

- AI-created workflow templates shared across teams.
- Versioned templates with approval pipeline.
- Tenant/org ACLs gate rollout and data access.

## 9. Backend Read/Write Patterns

### 9.1 Reads

- Read-through subscribe: backend provider hydrates initial state on first subscription.
- Cache projected model in memory per active graph/workflow.

### 9.2 Writes

- Command grips for side-effectful operations (submit/send/schedule).
- State grips for derived/current state.
- Idempotency keys for retriable writes.

### 9.3 Persistence worker

Use per-scope write-behind workers:

- coalesce by `(entity_id, field/path)`
- flush on debounce timeout
- force flush on max interval
- flush on graceful shutdown

## 10. AI Session Management Model

### 10.1 Always-on vs on-demand

Recommended default: **on-demand with warm TTL**.

- Spawn/attach agent when requested or when workflow policy requires.
- Keep warm for `N` minutes after last relevant event.
- Tear down when idle to control cost.

Use **always-on** only for premium/high-touch scenarios that truly need continuous monitoring.

### 10.2 Agent memory layers

1. Session memory (ephemeral, `session:*` grips)
2. User memory (durable, consented profile/preferences)
3. Workflow memory (durable per workflow instance)
4. Org memory (policy-governed shared knowledge)

### 10.3 Guardrails

- Action classes: `observe`, `suggest`, `apply_local`, `execute_external`
- Default to `suggest` for high-risk operations (email/send/payment)
- Require explicit user or policy approval for external side effects
- Record all agent-originated writes with actor metadata

## 11. Suggested V1 Implementation Order

1. Use Case 2 (simple settings) for end-to-end durability path.
2. Use Case 1 (sectioned document with JSON Patch log + snapshots).
3. Use Case 3 (OCR and shared form state/validation loop).
4. Use Case 4 subset (dynamic schema render + proposal/approval actions).

## 12. Open Decisions

1. Initial op format for Use Case 1: strict RFC 6902 only, or typed domain ops + JSON Patch fallback?
2. Snapshot cadence defaults: every N ops vs time-based vs hybrid.
3. Which action classes require mandatory human approval per tenant policy?
4. Default agent TTL and cost budget caps.
5. Minimum ACL matrix for user/agent/support in shared sessions.
