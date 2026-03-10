# Glial Implementation Plan Ordering

## Recommended Order

The recommended implementation order is:

1. Phase 01: local sequence foundation
2. Phase 02: session persistence abstractions
3. Phase 03: local durable stores
4. Phase 04: Glial server coordination
5. Phase 05: Glial client link and reconciliation

## Why This Order

The first three phases are intentionally local-first.

They establish:

- deterministic local mutation sequencing
- one runtime-facing persistence abstraction
- working local-only persistence in browsers and Python
- browser-local session records and local session browsing before any remote dependency

That gives a usable product baseline before any shared-session work starts.

After that, the server comes before client Glial attachment because:

- the client reconciliation path depends on authoritative server behavior
- replay, reset, lease, and clock semantics need a real implementation target
- remote backup and remote session catalog need a server-side authority before browser load or attach behavior can be finalized
- it reduces churn in the client link and persistence reconciliation code

## Dependency Rules

### Phase 01 -> Phase 02

Phase 02 depends on sequence metadata existing in the runtime change path.

### Phase 02 -> Phase 03

Phase 03 depends on stable persistence contracts and normalized change records.

### Phase 03 -> Phase 04

Phase 04 depends on local persistence because Glial sessions are layered onto local durable state, not a separate graph model.

### Phase 04 -> Phase 05

Phase 05 depends on a working Glial server core for:

- session creation
- authoritative clocks
- snapshot and replay
- lease ownership

## Parallelism Guidance

Limited parallel work is still possible.

Safe parallelism:

- test fixture work for later phases
- transport client wrappers that do not lock protocol semantics
- storage implementation spikes after Phase 02 contracts are stable

Unsafe parallelism:

- final client reconciliation logic before server authority behavior exists
- final Glial persistence semantics before local store contracts are stable

## Phase Gate

Do not start a later phase as the mainline implementation until the earlier phase exit criteria are met.
