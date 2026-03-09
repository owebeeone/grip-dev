# Glial Resolutions

Status: Working draft
Last updated: 2026-03-09

This document records accepted architectural resolutions for Grip/Glial.

---

## Resolution 001: Exported context identity must be stable

Status: Accepted

Contexts that are visible to Glial, persistence, graph export, or AI tooling must have stable logical identities.

We do not want random exported context names.

Notes:

- runtime object allocation may still be ephemeral
- internal cleanup behavior may still create and destroy context objects freely
- exported or persisted context identity must not depend on random runtime IDs

This means React creating the same logical UI structure multiple times must not create different persisted context identities just because component execution happened again.

---

## Resolution 002: Context structure and bound data are separate

Status: Accepted

A context identity describes structural role, not necessarily the current data item bound into that structure.

Examples:

- `weather-column(0)` and `weather-column(1)` are structural identities
- a table row slot may be `row-slot(0)`, `row-slot(1)`, `row-slot(2)`
- the current record bound into that slot is separate state, typically supplied by parameters or drips

This is important for virtualization and scrolling:

- slot identity should remain stable when appropriate
- bound row identity can change without redefining the structural context

We may still support contexts whose identity is data-keyed when that is the correct model, but that is a separate choice from structural slot identity.

---

## Resolution 003: Graph export includes the full structural graph

Status: Accepted

Graph export must include the full context graph, not only contexts that currently have active drips or taps.

That includes:

- contexts with no current taps
- contexts with no current drips
- parent and child connectivity
- enough metadata to reconstruct ordering where ordering matters

This is required for:

- faithful graph inspection
- persistence reasoning
- AI understanding of structure
- distinguishing absence of state from absence of structure

---

## Resolution 004: Graph export must expose current bindings, not just names

Status: Accepted

Names like `row-slot(1)` are not sufficient by themselves for AI or tooling to understand what the node currently represents.

Graph export should therefore carry both:

- structural identity
- current binding information

At minimum, exported graph data should be able to show things like:

- this is the second visible row slot
- it is currently bound to row ID `abc123`

This may be represented through destination parameters, grip values, or a dedicated binding section in the export, but the distinction must be visible.

---

## Resolution 005: Optional semantic purpose metadata may be attached to grips, contexts, and taps

Status: Accepted

Grips, contexts, and taps may optionally carry a short human-readable `purpose` or `description`.

This metadata is intended to help:

- AI graph interpretation
- debugging
- tooling
- architectural understanding

This metadata is useful context, but it is not a substitute for canonical identity or formal graph structure.

In other words:

- identity must still be explicit and machine-stable
- bindings must still be represented explicitly
- semantic descriptions are supplemental

---

## Resolution 006: Tap identity is based on home context, tap type, and provided grips

Status: Accepted

Tap identity should be simple and derivable from graph structure.

For now, the tap identifier basis is:

- home context identity
- tap type
- lowest lexical provided grip

Additional metadata should list:

- all provided grips
- home parameter grips
- destination parameter grips

This keeps tap identity compact while still allowing the full graph export to show theoretical connectivity and parameter dependencies.

---

## Resolution 010: Delta protocol engine selection is deferred until after the SDD

Status: Accepted

We are not selecting the replication/delta engine during the current SDD pass.

Decision:

- treat protocol engine selection as a post-SDD decision
- initial evaluation scope is JavaScript/TypeScript and Python only
- we can try an implementation, learn from it, and change course if needed

This keeps the current design effort focused on the graph model, identity, export shape, and session semantics without prematurely locking the implementation to a specific replication stack.

---

## Resolution 007: Context addresses use a canonical string path

Status: Accepted

Context identity will use a canonical string path rather than a list form.

Format:

- root is `/`
- child contexts append a segment name with `/` as separator
- examples: `/weather-column-0`, `/table/row-slot-1`

This keeps graph export simple because the graph can be represented as a map of `path -> ContextState`.

If needed, context names must avoid the path separator.

---

## Resolution 008: Matchers do not create contexts

Status: Accepted

Matchers are not part of the context identity problem.

For Glial purposes:

- matchers add and remove taps based on matched conditions
- matchers do not create contexts

That means the persistent-vs-ephemeral context question applies to contexts created by the application/runtime, not to matcher behavior.

---

## Resolution 009: Graph export uses `path -> ContextState`

Status: Accepted

Graph export will be a map from context path to `ContextState`.

Each `ContextState` contains:

- the context name
- the ordered list of child names
- a map of `grip-id -> DripState`

Each `DripState` contains:

- the drip name
- the current value
- a list of taps connected to that drip

Each exported tap entry contains:

- tap type
- the grips it actually provides at that location
- metadata
- optional cache state

This export shape is intended for graph inspection, persistence reasoning, and AI understanding.

---

## Resolution 011: Session ID is shared, replica ID is per participant

Status: Accepted

A `session_id` identifies the shared Glial state for a group of cooperating clients.

A `replica_id` identifies one concrete participant within that session.

Notes:

- all replicas participating in the same shared state use the same `session_id`
- each replica has its own `replica_id`
- replicas under one session are expected to converge to the same replicated state

---

## Resolution 012: The persistence boundary is graph state, not runtime machinery

Status: Accepted

Glial replicates graph state entries and does not replicate local runtime machinery.

Replicated state includes:

- contexts
- graph connectivity
- child ordering
- drip current values
- semantic metadata
- tap metadata
- optional tap cache metadata/state where appropriate

Local-only runtime machinery includes:

- subscribers and listener counts
- UI mount state
- task queue state
- timers
- in-flight async requests
- abort controllers
- controller objects
- function objects and local executable code

---

## Resolution 013: Tap execution uses explicit ownership modes

Status: Accepted

Tap execution is not assumed to run everywhere symmetrically.

The required ownership modes are:

- `replicated`
- `origin-primary`
- `negotiated-primary`

Meaning:

- `replicated`: normal replicated operation; suitable for simple state-setting behavior such as atom-style updates
- `origin-primary`: the originating replica is the default primary executor; non-primary replicas follow replicated outputs
- `negotiated-primary`: a replica may acquire primary execution ownership for a tap through negotiation

For primary-owned taps, non-primary replicas are followers and wait for updates from the primary.

---

## Resolution 014: Negotiated primaries require presence detection and fallback

Status: Accepted

If a tap is operating in `negotiated-primary` mode, the system must detect when the negotiated primary leaves.

Required behavior:

- replica presence/leave must be detectable
- negotiated primary loss must release primary ownership
- when the negotiated primary disappears, the original primary takes over if still present
- other replicas remain followers unless a new negotiation succeeds

This is a requirements-level resolution only. The exact lease/heartbeat/protocol mechanism is still open.

---

## Resolution 015: Replicas in one session must share the same JWT claims envelope

Status: Accepted

Replicas participating in the same session must use the same JWT/auth claims envelope for Glial-controlled behavior.

This requirement exists to prevent accidental privilege changes when execution ownership moves between replicas.

Implications:

- negotiation must not be a path to claim escalation
- running a function/tool on a different replica must not silently change authorization context

This is a minimum security requirement and does not fully define the final authorization design.

---

## Resolution 016: Glial server is the central lease authority for negotiated primaries

Status: Accepted

Primary ownership negotiation is Glial-mediated, not peer-to-peer.

Required behavior:

- a replica requests primary ownership from Glial
- Glial issues leases for negotiated primaries
- Glial checks liveness for leased primaries
- Glial resolves competing requests
- priority may be part of the request, with highest priority winning

The exact message flow is an SDD concern.

---

## Resolution 017: Reconnect and delivery semantics must tolerate loss, duplication, and reordering

Status: Accepted

Reconnect behavior should not rely on a perfect transport stream.

Protocol requirement:

- messages may be lost
- messages may be duplicated
- messages may arrive out of order

Rebuilding the logical state stream is therefore an application/protocol responsibility, not a transport assumption.

This means the protocol should be workable over an unreliable unordered transport model even if the initial implementation uses WebSockets or hanging GETs.

---

## Resolution 018: The current graph export outline is sufficient for the SDD pass

Status: Accepted

We do not need to finalize the exact exported JSON field names during the current SDD pass.

For now, the accepted outline is:

- `path -> ContextState`
- each `ContextState` contains the context name, ordered child names, and `grip-id -> DripState`
- each `DripState` contains the drip name, current value, and connected taps
- each exported tap includes tap type, actual provided grips, metadata, and optional cache state

Exact field naming and serialization details can be refined later.

---

## Resolution 019: Authentication is outside Glial

Status: Accepted

Glial is not responsible for authenticating users.

Glial should receive an already-authenticated identity or claims envelope from the host environment.

Examples:

- user ID
- JWT claims
- equivalent authenticated claims provided by a framework such as FastAPI

Glial is responsible for using those claims consistently, not for performing authentication itself.

---

## Resolution 020: Glial does not impose a message size limit

Status: Accepted

Glial does not define a protocol-level message size limit.

Any size limits belong to lower layers such as:

- transport
- hosting framework
- deployment environment

This keeps message sizing out of Glial core responsibilities.

---

## Resolution 021: Every synchronized delta carries a virtual clock

Status: Accepted

Every synchronized delta must carry a comparable virtual clock stamp.

This clock is used for:

- stale update elision in drips
- replay and resync
- reconnect recovery
- conflict handling in the sync protocol

The clock must be propagated through taps and drips so that local runtime update handling and network synchronization use the same ordering basis.

---

## Resolution 022: Glial assigns the authoritative session clock for accepted deltas

Status: Accepted

Glial is the authority that assigns the final session clock stamp to accepted replicated deltas.

Replicas may propose or observe clocks, but the authoritative clock on a synchronized delta is the clock assigned by Glial for that session.

Replicas must advance their local clock floor when they observe a server-issued session clock.

---

## Resolution 023: Lease defaults favor low chatter over fast failover

Status: Accepted

The default lease policy should avoid saturating the connection with lease traffic.

Defaults:

- default lease TTL: `60_000ms`
- default renew point: `40_000ms`
- default replica heartbeat cadence: `15_000ms`
- default liveness timeout: `45_000ms`

Conflict defaults:

- strictly higher priority beats lower priority
- equal priority keeps the incumbent primary
- if there is no incumbent, first server-accepted request wins
- final tie-break is lexical `replica_id`

Shorter lease requests are allowed and may be appropriate for headless or specialized replicas.

---

## Resolution 024: On sync uncertainty, Glial falls back to a full resnapshot

Status: Accepted

The first implementation should prefer correctness over incremental recovery complexity.

Required behavior:

- reconnect attempts replay from the client's last applied clock
- if Glial cannot safely replay, it sends a fresh full snapshot
- if the client detects a local sync error or uncertainty, it requests a reset and Glial resends the full graph

This gives a simple and resilient baseline. Later versions may optimize replay and gap repair.

---

## Resolution 025: Snapshot entries carry per-entry clocks

Status: Accepted

Every replicated entry in a snapshot must include its current entry clock.

This allows the client to:

- rebuild local per-target clock state from a snapshot
- elide stale deltas after reconnect
- apply replay/live deltas using the same local comparison rules

---

## Resolution 026: New Glial sessions start from a server-seeded clock

Status: Accepted

When Glial creates a new session clock domain, it seeds the session clock from the server.

Initial value:

- `wall_time_ms` = current Glial server time
- `logical_counter` = `0`
- `replica_id` = `"glial"`

This gives every new session a deterministic initial clock floor.

---

## Resolution 027: Large mutable JSON is replace-only at entry granularity in v1

Status: Accepted

Glial does not need a separate replication protocol for large mutable JSON values in v1.

Instead, a large JSON value is treated as a replicated entry and synchronized using the existing clocked delta protocol.

Required behavior:

- the JSON value is replicated as a single entry
- updates are full-value replace operations
- the entry carries one authoritative Glial-issued clock
- stale updates are elided by comparing the incoming entry clock with the current local entry clock
- snapshots carry both the JSON value and its entry clock

If this proves too coarse later, the next step is to split the JSON into stable sub-entries with separate clocks.

True fine-grained JSON patching or CRDT-style blob replication remains deferred until after the SDD.

---

## Resolution 028: Local-only persistence is the default; Glial is opt-in

Status: Accepted

The default session lifecycle is local persistence in one runtime, especially browser reload restore from IndexedDB or an equivalent local store.

Glial is enabled only when a session must be:

- shared across multiple replicas
- attached to headless or AI participants
- remotely saved and later resumed beyond one local runtime

This means:

- local browser reload must not require any Glial service
- Glial extends the persistence model into shared coordination rather than replacing local persistence
- the local-only path is the primary baseline use case for v1

---

## Resolution 029: Persistence uses a mandatory local store and an optional Glial link

Status: Accepted

Grip runtimes use one engine-facing persistence contract, but that contract is backed by:

- a mandatory local durable session store
- an optional Glial shared-session link

This means:

- IndexedDB and filesystem persistence are first-class implementations
- Glial is an attachment to the local store model, not a replacement for it
- local and Glial-sourced changes must be normalized into one persisted change model

---

## Resolution 030: One root event may emit many mutations without nested subsequences

Status: Accepted

One root local event or causal chain may emit multiple concrete mutations.

V1 handles this by separating:

- `origin_generation` for grouping by causal root
- `origin_mutation_seq` for ordering individual emitted mutations

This means:

- we do not need nested sequence notation like `200.1`
- drips compare freshness per grip or value stream
- taps evaluate against the latest materialized input set after per-grip stale elision

---

## Resolution 031: `glial-local-*` owns the canonical session model; `glial-net-*` is optional

Status: Accepted

The Glial packaging boundary for v1 is:

- `glial-local-ts` and `glial-local-py` own the canonical persisted session model and persistence interfaces
- `glial-net-ts` and `glial-net-py` own client-side Glial communication
- `glial-router-py` owns server-side routing, shard, clock, snapshot, replay, and lease coordination

`glial-local-*` is not just a value bag.

It owns:

- canonical session metadata
- normalized snapshot and delta types
- sequence and checkpoint semantics

It does not own concrete Grip runtime objects.
