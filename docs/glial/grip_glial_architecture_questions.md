# Grip / Glial Session Persistence & Synchronization

## Ambiguity Review and Refinement Questions

This working note extracts the main ambiguities in the V0.2 proposal and proposes likely answers so the next revision can be sharper, more implementation-ready, and compatible across TypeScript and Python runtimes.

---

## 1. Stable identity and addressability

### Q1. What exactly is a “Context Path”, and how is it made deterministic across runtimes?
**Why this matters:** The proposal uses `[Context Path]#[Grip ID]` and `[Context Path]@tap:[Tap ID]`, but does not define the canonical path derivation algorithm. If JS and Python derive different paths for equivalent graphs, persistence and sync will break.

**Proposed answer:**
Define a canonical `ContextAddress` independent of in-memory object identity. Each context must have:
- a stable `contextType` or `role`
- a stable `localId` or `instanceKey`
- an ordered parent chain

Canonical format:
`/<root>/<segment-name>(<instance-key>)/...`

Rules:
- path segments are UTF-8 strings normalized to NFC
- reserved characters are percent-encoded
- parent ordering must be explicit and stable
- auto-generated runtime object IDs must never be used in persisted addresses

If a context has no developer-supplied key, the engine must declare it **ephemeral and non-persistable** by default.

### Q2. Can matcher-created or dual-context structures produce stable IDs, or are some inherently ephemeral?
**Why this matters:** The current proposal assumes all dynamic topology can be restored from the hydration buffer, but some matcher outputs may be conditional or anonymous.

**Proposed answer:**
Split contexts into two classes:
- **persistent contexts**: have explicit stable keys and participate in persistence/sync
- **ephemeral contexts**: runtime-only, not restored directly; they are rebuilt by replaying persistent graph state

Only persistent contexts may appear in canonical state IDs. Matcher-created contexts must either:
- carry an explicit persistent key supplied by matcher logic, or
- be excluded from durable state and rebuilt as a consequence of other durable inputs.

### Q3. Is the tap ID hash stable across language implementations and version upgrades?
**Why this matters:** `hash(sorted_input_grips + sorted_output_grips)` is under-specified and unsafe across languages, runtimes, and even library versions.

**Proposed answer:**
Do not use implementation-native hash functions. Define a canonical tap fingerprint spec:
- inputs: ordered list of provided grip IDs, destination param grip IDs, home param grip IDs, tap class/type name, developer name if present
- serialization: canonical JSON
- digest: SHA-256
- ID form: `sha256:<hex>`

Also allow explicit developer IDs and recommend them for any stateful tap.

### Q4. Should tap identity include versioning?
**Why this matters:** A persisted async cache from one tap implementation may be invalid or dangerous after the tap logic changes.

**Proposed answer:**
Yes. Add `tapSchemaVersion` or `persistenceVersion` into tap identity or metadata. State restore must verify compatibility before hydration. Incompatible state should be ignored or migrated.

---

## 2. Persistence scope and state model

### Q5. What categories of state are allowed to persist?
**Why this matters:** The proposal mentions drips and taps, but not whether request state, retry timers, diagnostics, semantic metadata, or controller state are durable.

**Proposed answer:**
Define four persistence classes:
1. **Durable value state** – drip values, atom values, durable derived values
2. **Durable tap cache state** – async cache entries, selected destination keys, resumable metadata
3. **Ephemeral runtime state** – timers, AbortControllers, pending requests, subscriptions, WeakRefs
4. **Diagnostic state** – histories, retry counters, debug traces; optional and usually not synchronized

Only classes 1 and selected parts of 2 should cross language/process boundaries.

### Q6. Should async tap request state be persisted and synchronized?
**Why this matters:** grip-core’s async tap design has per-destination state, history, listener counts, controller grips, and shared request-key state. Most of that is not suitable for cross-runtime durability.

**Proposed answer:**
Persist only **cache entries and cache metadata** for async taps. Do **not** persist:
- AbortControllers
- pending in-flight request state
- retry timers
- listener counts
- controller grips
- ephemeral history by default

Persist optional diagnostic history only when explicitly enabled.

### Q7. Are full values and patches both first-class, or is one canonical?
**Why this matters:** `StateDelta` currently allows both `value` and `patch`, but does not define precedence or when each is valid.

**Proposed answer:**
Make the wire protocol explicit:
- `op: 'replace' | 'patch' | 'remove'`
- `payload` required for `replace` and `patch`
- `patch` uses canonical path-level LWW patch entries, not raw RFC 6902 alone

For v1 cross-language interoperability, default to **replace-only** for simplicity. Introduce patching only after canonical CRDT patch semantics are fully defined.

---

## 3. Hydration semantics

### Q8. Is hydration a one-shot bootstrap map or a durable local index with per-entry lifecycle?
**Why this matters:** The term “Hydration Buffer” sounds temporary, but the proposal also expects per-property HLC tracking and deletes.

**Proposed answer:**
Rename it to **State Plane Cache** or define two layers:
- **Persistent Store**: backing KV or log-backed store
- **Hydration Buffer**: startup/read-through in-memory index

Each entry should track:
- `id`
- `kind`
- `schemaVersion`
- `value`
- `hlc`
- `originReplica`
- optional `fieldClocks`
- optional `expiresAt`
- optional `tombstone`

### Q9. When is hydrated data considered stale or invalid?
**Why this matters:** A Python worker may restore values that are incompatible with the current code or already superseded.

**Proposed answer:**
Hydration should validate:
- schema version compatibility
- data type compatibility
- TTL / expiry
- optional application-level validator

Invalid or expired entries should be dropped before being offered to contexts/taps.

### Q10. How do we distinguish “temporarily hidden” from “permanently destroyed” contexts?
**Why this matters:** The delete rule is underspecified and could cause data loss if a context is detached briefly and later reappears.

**Proposed answer:**
Introduce explicit lifecycle states:
- `active`
- `inactive-detached`
- `disposed`

Only `disposed` may trigger durable deletion. Add optional grace-period GC or lease expiry before final remove.

---

## 4. Cross-language data model

### Q11. What serialization format is canonical across TypeScript and Python?
**Why this matters:** The proposal currently uses `any`, which is not a protocol.

**Proposed answer:**
Define a canonical JSON-compatible schema for all synchronized values.

Allowed scalar/domain types for v1:
- null
- boolean
- string
- integer / float
- array
- object with string keys

For non-JSON-native values use typed envelopes:
- datetime
- bytes
- decimal
- UUID
- bigint if needed

Example envelope:
`{"$type":"datetime","value":"2026-03-09T12:34:56.000Z"}`

Do not sync raw runtime objects, closures, class instances, exceptions, functions, WeakRefs, signals, or JS/Python-specific prototypes.

### Q12. How are Grip IDs made canonical across language ports?
**Why this matters:** Semantic state and persistence only work if both implementations refer to the same logical Grip identity.

**Proposed answer:**
Grip definitions must expose a canonical, developer-assigned string ID. Never derive synchronized Grip identity from package-local symbol identity or object identity. Recommend a namespace format such as:
`<domain>.<module>.<name>`

### Q13. How are semantic annotations shared between runtimes?
**Why this matters:** AI semantics are part of the proposal, and Python is now a peer runtime.

**Proposed answer:**
Semantics must be represented in a runtime-neutral schema attached to Grip definitions:
- `id`
- `type`
- `description`
- `mutable`
- `actionIntent`
- optional enum/options
- optional validation hints

Both JS and Python ports should load/export the same semantic schema.

---

## 5. Headless and server roles

### Q14. Is the Glial server authoritative, or only a relay?
**Why this matters:** The proposal describes it as a relay, but headless restore and session dumps imply some server-owned canonical state plane.

**Proposed answer:**
State this explicitly:
- **Replica model:** every engine is a replica
- **Glial server role:** authoritative for session membership and durable state-plane storage, but **not** authoritative for mutation ordering
- **Conflict resolution:** deterministic HLC/LWW at every replica, including server

So Glial is not a pure relay; it is a state-plane peer with persistence responsibilities.

### Q15. What is the handshake contract for a reconnecting Python worker?
**Why this matters:** “Identify the session” is not enough for safe recovery.

**Proposed answer:**
Handshake should include:
- protocol version
- runtime type (`browser`, `python-worker`, `ai-agent`, etc.)
- replica ID
- session ID
- supported schema versions
- supported patch modes (`replace-only`, `lww-map`, etc.)
- requested namespaces or capability scopes
- last applied checkpoint / last seen HLC if doing incremental catch-up

### Q16. Does a reconnecting headless client receive a full dump or an incremental catch-up?
**Why this matters:** Full dumps are simple but expensive; incremental replay is harder but cleaner.

**Proposed answer:**
Support both:
- v1: full state-plane dump plus live delta stream
- v2: checkpoint + delta catch-up from `sinceHlc`

Document that v1 uses full dump for simplicity.

---

## 6. Concurrency and conflict resolution

### Q17. Is HLC tracked per entry, per field, or both?
**Why this matters:** The document mixes entry-level and field-level clocks.

**Proposed answer:**
Define two modes explicitly:
- **Entry-LWW mode**: default for scalar or whole-object replacement values
- **Field-LWW mode**: optional for declared object-map state types

A state entry must declare which mode it uses. Do not silently mix them.

### Q18. Can RFC 6902 JSON Patch be used safely here?
**Why this matters:** The proposal already notes RFC 6902 breaks under reordering.

**Proposed answer:**
Not by itself. For distributed mode, use either:
- replace-only semantics, or
- a custom **LWW map patch** where each changed path carries its own HLC and delete marker

Do not describe raw JSON Patch as safe for active sync.

### Q19. How are deletions represented?
**Why this matters:** LWW systems need tombstones to beat delayed older writes.

**Proposed answer:**
Every delete must produce a tombstone carrying:
- `id` or `path`
- `hlc`
- `originReplica`
- optional `expiresAt`

Delayed older writes must lose to the tombstone until compaction.

### Q20. How are equal HLCs broken?
**Why this matters:** Total ordering is required.

**Proposed answer:**
Specify comparator:
1. physical time
2. logical counter
3. replica ID lexicographically

Replica IDs must therefore be globally unique and stable for the session.

### Q21. What is the causalityId used for?
**Why this matters:** It exists in the delta type but no semantics are defined.

**Proposed answer:**
Use `causalityId` only for tracing, grouping, and optional suppression of feedback loops in application logic. It should **not** participate in conflict resolution. Add a separate `originReplica` field for protocol-level loop prevention and authorship.

---

## 7. Loop prevention and delivery semantics

### Q22. Is “taint flag” enough to prevent echo loops across multiple replicas?
**Why this matters:** A local flag works inside one process, not across a relay with multiple peers.

**Proposed answer:**
No. Add protocol fields:
- `originReplica`
- `relayReplica` or `forwardedBy`
- `deltaId`

Each replica keeps a short-lived dedupe set of seen `deltaId`s. Echo suppression should be protocol-level, not only in-memory tainting.

### Q23. What delivery guarantee does Glial provide?
**Why this matters:** Retry, reconnection, and dedupe all depend on whether transport is at-most-once, at-least-once, or effectively-once.

**Proposed answer:**
Assume **at-least-once delivery** with deduplication by `deltaId`. This is the simplest reliable model for WebSocket reconnect scenarios.

---

## 8. Tap-specific persistence concerns

### Q24. Can async cache entries be shared safely between JS and Python taps?
**Why this matters:** A cached response format may differ by implementation even if the logical request key matches.

**Proposed answer:**
Only if the tap declares:
- canonical request-key derivation
- canonical cached value schema
- shared `tapPersistenceVersion`

Otherwise cache state should be runtime-local, even if drip outputs are synchronized globally.

### Q25. Should request-key deduplication be local-only or cross-replica?
**Why this matters:** The current async tap design deduplicates by request key, but only within a runtime.

**Proposed answer:**
For v1 keep request execution local to each replica. Synchronize outputs, not in-flight request ownership. Cross-replica work deduplication is a separate concern and should not be entangled with the persistence protocol initially.

### Q26. How should controller grips behave across runtimes?
**Why this matters:** A JS controller grip exposing methods like `retry()` cannot be serialized to Python.

**Proposed answer:**
Controller grips are runtime-local affordances only. They must never be synchronized as executable objects. If remote control is needed, define explicit command drips or command events in the protocol.

---

## 9. Graph restoration and replay

### Q27. Is restoration driven purely by state hydration, or can actions/events be replayed?
**Why this matters:** Some graphs are easier to reconstruct from durable actions than from raw derived state.

**Proposed answer:**
State that v1 is **state-plane hydration**, not event sourcing. Derived topology is rebuilt by evaluating hydrated persistent inputs. Event replay may be introduced later for auditability but should not be implied in the current design.

### Q28. Are all active contexts included in `exportSemanticState()`, or only persistent ones?
**Why this matters:** AI state snapshots can become noisy or unstable if ephemeral contexts are exported indiscriminately.

**Proposed answer:**
Export only:
- active persistent contexts by default
- optionally selected ephemeral contexts when explicitly marked `semanticVisible`

The export must include stable IDs and mutability metadata, not raw runtime object references.

---

## 10. Suggested architecture decisions for the next revision

### Recommended defaults for V0.3
1. **Canonical IDs everywhere**
   - persistent context addresses
   - explicit grip IDs
   - explicit or SHA-256 tap IDs
   - persistence versioning

2. **Protocol-first state plane**
   - replace-only deltas for v1
   - JSON-compatible canonical value schema
   - `deltaId`, `originReplica`, `hlc`, `causalityId`, `schemaVersion`

3. **Clear persistence boundary**
   - persist drip values and selected tap cache state
   - do not persist timers, controllers, listeners, AbortControllers, WeakRefs

4. **Replica model**
   - Glial is a persistent state-plane peer, not only a relay
   - conflict resolution is decentralized via HLC/LWW

5. **Cross-language compatibility contract**
   - runtime-neutral schemas for grips, semantics, state entries, and tap cache payloads
   - same canonical comparator and hashing rules in JS and Python

6. **Safe deletion model**
   - tombstones + compaction
   - explicit `disposed` lifecycle state

7. **Keep distributed patching out of v1 unless fully specified**
   - replace-only first
   - add path-level LWW patches only once the CRDT format is nailed down

---

## 11. What the revision should explicitly add

The next revision of the proposal should include:
- a glossary for context, drip, tap, destination, replica, session, state plane
- canonical identity rules and examples
- a runtime-neutral wire schema
- a persistence-class table (durable vs ephemeral)
- a cross-language serialization section
- an authoritative lifecycle/state machine for restore, detach, dispose, delete
- a delivery and dedupe model
- explicit v1 scope vs future enhancements

---

## 12. Bottom line

The proposal already has the right high-level direction: stable IDs, lazy hydration, local-first deltas, and HLC-based eventual consistency. The main weaknesses are not conceptual; they are **protocol precision** problems.

To make it buildable across TypeScript and Python, the next revision needs to treat this as:
- a canonical identity problem,
- a canonical serialization problem,
- a durable-vs-ephemeral state boundary problem,
- and a replica protocol problem.

Once those are explicit, the architecture becomes much more concrete and testable.

