# Glial Implementation Plan Phase 01: Local Sequence Foundation

## Testing Plan

- add unit tests in `grip-core` proving that every locally originated persistable or shared change carries a monotonic `origin_mutation_seq`
- add unit tests in `grip-py` proving the same sequence assignment rules
- add regression tests showing one root event can produce multiple persisted or shared mutations and each gets a fresh sequence without nested subsequence notation
- add regression tests documenting current async stale-completion behavior rather than replacing it
- add matcher substitution regression tests showing the old async producer cannot publish into a destination after it is disconnected
- add unit tests for tap ownership APIs proving default `mode` and runtime `role` values for `AtomValueTap`, `FunctionTap`, and `AsyncTap`
- add unit tests proving a tap can transition between `primary` and `follower` role without changing its stable tap identity
- add parity tests or golden graph-dump tests so TypeScript and Python expose the same sequence metadata semantics where available
- add tests proving the new metadata path does not change normal value-notification behavior for existing drip subscribers

## Goal

Add the local sequencing model needed by persistence and Glial change records to `grip-core` and `grip-py`.

This phase implements:

- `origin_mutation_seq` as the strictly increasing order for locally originated persistable or shared mutations
- the runtime plumbing needed to surface that metadata into persistence or sync adapters
- local tap ownership APIs exposing `mode` and runtime `role`
- regression coverage around the existing async freshness and matcher substitution behavior

This phase does not include persistence or Glial networking yet.

It also does not replace the existing async-tap latest-only and disconnect behavior that already handles the primary stale-request problem inside one runtime.

## Scope

- define local sequence metadata types in both runtimes
- add a local sequence allocator in both runtimes
- assign a new `origin_mutation_seq` only when the runtime originates a persistable or shared change record
- carry that metadata through the internal change path used by future persistence or Glial adapters
- keep sequence assignment off ordinary internal async freshness handling and off remotely sourced Glial applies
- add local runtime APIs so taps expose ownership `mode` and current `role`
- default local-only role resolution so taps start in a deterministic role before any Glial lease coordination exists
- keep sequence-sensitive behavior internal rather than adding a new public sequence-only subscription API
- expose sequence metadata in debug or graph-dump views where helpful for tests and later phases

## Expected Code Areas

TypeScript:

- `grip-core/src/core/drip.ts`
- `grip-core/src/core/atom_tap.ts`
- `grip-core/src/core/function_tap.ts`
- `grip-core/src/core/async_tap.ts`
- `grip-core/src/core/base_tap.ts`
- `grip-core/src/core/graph_dump.ts`
- `grip-core/src/core/grok.ts` or `grip-core/src/core/graph.ts` if sequence allocation needs a shared owner

Python:

- `grip-py/src/grip_py/core/drip.py`
- `grip-py/src/grip_py/core/atom_tap.py`
- `grip-py/src/grip_py/core/function_tap.py`
- `grip-py/src/grip_py/core/async_tap.py`
- `grip-py/src/grip_py/core/base_tap.py`
- `grip-py/src/grip_py/core/graph_dump.py`
- `grip-py/src/grip_py/core/grok.py` or `grip-py/src/grip_py/core/graph.py`

## Design Rules

- one root event may emit multiple persisted or shared mutations
- each such emitted mutation gets its own fresh `origin_mutation_seq`
- no nested sequence notation such as `200.1` is introduced
- emitted change records do not reuse the largest input sequence number as their own sequence
- if async taps need causal lineage, they track latest request or key freshness internally
- stale async results are primarily prevented by async tap latest-only behavior before publication
- matcher substitution is primarily prevented by disconnecting the old producer before it can publish again
- Glial-sourced authoritative updates must not allocate a new local mutation sequence when applied
- tap ownership `mode` and runtime `role` must exist before Glial networking, even if negotiated-primary transitions are implemented later
- local-only runtime defaults are:
  - `AtomValueTap` -> `mode=replicated`
  - `FunctionTap` -> `mode=origin-primary`, `role=primary`
  - `AsyncTap` -> `mode=origin-primary`, `role=primary`
- this phase does not require a new per-grip stale-elision mechanism for ordinary local runtime flow
- no new public value-plus-sequence subscription mode is introduced in this phase

## Work Items

1. Add sequence carrier types or fields to the local persistable or shared change path in both runtimes.
2. Add a local sequence allocator owned by the graph or grok runtime.
3. Plumb `origin_mutation_seq` into the internal session-change envelope without changing the public Drip API.
4. Add tap ownership APIs exposing `mode` and runtime `role` in both runtimes.
5. Add regression coverage for current async tap latest-only and matcher disconnect behavior.
6. Add debug visibility so failing tests can inspect sequence metadata and tap role metadata.
7. Align TS and Python naming and behavior before moving on.

## Exit Criteria

- every locally originated persistable or shared mutation in both runtimes has a deterministic `origin_mutation_seq`
- one causal chain can emit multiple persisted or shared mutations while each output still gets a fresh sequence
- the runtime exposes enough internal metadata to build the Phase 02 persistence abstraction
- taps in both runtimes expose stable ownership `mode` and runtime `role` APIs with agreed defaults
- async completions made stale by newer requests remain covered by current runtime behavior
- matcher-substituted old producers cannot publish into disconnected destinations
- TypeScript and Python behavior is aligned enough to support the shared persistence layer in Phase 02

## Non-Goals

- no IndexedDB or filesystem persistence
- no Glial protocol messages
- no session catalog
- no snapshot or replay transport
- no public subscription API that emits on sequence-only changes
