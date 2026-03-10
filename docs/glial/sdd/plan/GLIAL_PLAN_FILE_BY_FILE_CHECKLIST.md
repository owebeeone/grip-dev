# Glial File-By-File Implementation Checklist

## Purpose

This checklist translates the revised SDD into concrete code changes.

It assumes the current codebase already has:

- source-state local persistence for headed runtimes
- atom tap export and restore hooks
- browser-local reload restore in the demo

The remaining work is to align the code with the revised SDD model:

- source-state backup and restore
- shared-state projection for headed and headless sharing
- browser session records
- remote session storage
- passive taps and tap materialization

## Change Categories

### Keep

These current pieces remain valid and should be evolved rather than removed:

- runtime-owned source-state local persistence
- atom tap export and restore hooks
- dirty suppression during hydrate or inbound apply
- local browser reload restore

### Add

These are new capabilities required by the revised SDD:

- separate shared-state projection builder and apply path
- browser session records
- remote session catalog and backup store
- passive taps and tap materialization registry
- headed versus headless hydrate rules
- local and remote session browser tooling

## `grip-core`

### `/Users/owebeeone/limbo/grip-dev/grip-core/src/core/local_persistence.ts`

- completed: current implementation now serves as the source-state backup projector path
- completed: `buildLocalPersistenceSnapshot()` remains the headed restore snapshot builder
- completed: shared-state projection builder now exists
- completed: shared-state projection apply path now exists
- ensure source-state restore registers real taps first, then restores source values
- completed: shared-state projection apply now uses passive taps through the materialization registry fallback
- add explicit comments distinguishing backup restore from shared projection

### `/Users/owebeeone/limbo/grip-dev/grip-core/src/core/grok.ts`

- completed: projector attachment APIs now exist: `attachProjector(projector)`, `detachProjector(id)`, and `listProjectors()`
- completed: source-state backup projector attach remains the current local restore path
- remaining: keep a shared projection projector implementation for Glial-routed sharing
- completed: tap materialization registry support exists
- add support for loading a logical `glial_session_id`
- ensure browser-session record data can be passed in without leaking browser APIs into core
- ensure inbound shared projection apply bypasses local dirty queue

### `/Users/owebeeone/limbo/grip-dev/grip-core/src/core/tap.ts`

- completed: tap materialization metadata interfaces exist
- completed: explicit passive tap support exists
- add optional hooks for exporting shared-state tap metadata separate from source-state backup values
- keep current persisted value hooks for source-state backup

### `/Users/owebeeone/limbo/grip-dev/grip-core/src/core/base_tap.ts`

- add shared-state export helpers for tap metadata if needed
- ensure execution mode and role are visible to shared projection export
- ensure follower or passive behavior is preserved during shared projection hydrate

### `/Users/owebeeone/limbo/grip-dev/grip-core/src/core/atom_tap.ts`

- keep current source-state export and restore hooks
- optionally add explicit distinction between source-state export and shared-state export if the API becomes separate
- ensure non-JSON handle grips remain excluded from persistence and sharing

### `/Users/owebeeone/limbo/grip-dev/grip-core/src/core/function_tap.ts`

- partial: shared projection can now capture and rehydrate function tap metadata through generic tap export
- do not add generic source-state backup unless the tap holds real durable internal state
- completed: follower and headless replicas can materialize function tap state via passive taps
- optionally add explicit internal-state export only when a concrete function tap truly owns durable state

### `/Users/owebeeone/limbo/grip-dev/grip-core/src/core/async_tap.ts`

- partial: shared projection can now capture and rehydrate async tap metadata through generic tap export
- keep source-state backup optional and tap-specific
- remaining: if async cache export is later needed, make it explicit and opt-in
- completed: follower and headless replicas can materialize async tap state via passive taps

### `/Users/owebeeone/limbo/grip-dev/grip-core/src/core/grip.ts`

- completed: canonical `getByKey()` lookup exists
- remaining: ensure shared projection hydrate can resolve grip IDs without re-parsing elsewhere

### `/Users/owebeeone/limbo/grip-dev/grip-core/src/index.ts`

- completed: passive tap and tap materialization registry APIs are exported
- partial: projector APIs and types are exported from runtime and local persistence

### `/Users/owebeeone/limbo/grip-dev/grip-core/tests/local_persistence.spec.ts`

- completed: source-state backup tests exist, including multiple-projector restore semantics
- completed: shared-state projection tests exist
- completed: follower or passive tap hydration is covered

### New test files under `/Users/owebeeone/limbo/grip-dev/grip-core/tests/`

- partial: passive tap materialization is covered in shared projection tests
- remaining: add explicit headed restore versus headless hydrate distinction tests
- add matcher restore tests proving source-state backup restore reruns matchers correctly
- add shared projection tests proving current active tap metadata is sufficient without rerunning matchers locally

## `grip-py`

### `/Users/owebeeone/limbo/grip-dev/grip-py/src/grip_py/core/local_persistence.py`

- refactor current implementation so it is explicitly the source-state backup projector path
- add shared-state projection builder
- add shared-state projection apply path
- keep current headed restore semantics for source-state backup
- ensure headless hydrate uses passive taps and shared outputs rather than rerunning local app logic

### `/Users/owebeeone/limbo/grip-dev/grip-py/src/grip_py/core/grok_impl.py`

- replace hard-coded local/shared attach assumptions with projector attachment APIs
- keep source-state backup and shared projection as projector kinds rather than top-level special-case APIs
- add tap materialization registry support
- add support for loading a logical `glial_session_id`
- ensure shared-state apply bypasses the local dirty queue

### `/Users/owebeeone/limbo/grip-dev/grip-py/src/grip_py/core/interfaces.py`

- add passive tap protocol support
- add tap materialization registry protocol
- add explicit split between source-state restore hooks and shared-state materialization metadata if needed

### `/Users/owebeeone/limbo/grip-dev/grip-py/src/grip_py/core/atom_tap.py`

- keep current source-state export and restore hooks
- ensure function grips or non-JSON values remain excluded

### `/Users/owebeeone/limbo/grip-dev/grip-py/src/grip_py/core/function_tap.py`

- add shared-state export metadata support
- support passive materialization
- only add source-state backup hooks where the tap truly owns durable state

### `/Users/owebeeone/limbo/grip-dev/grip-py/src/grip_py/core/async_tap.py`

- add shared-state export metadata support
- keep async cache backup optional and explicit
- support passive materialization

### `/Users/owebeeone/limbo/grip-dev/grip-py/tests/core/test_local_persistence.py`

- clarify that current tests are source-state backup tests
- add separate shared projection hydrate tests

### New test files under `/Users/owebeeone/limbo/grip-dev/grip-py/tests/core/`

- add passive tap materialization tests
- add headed restore versus headless hydrate distinction tests
- add matcher restore tests
- add shared projection convergence tests

## `glial-local-ts`

### `/Users/owebeeone/limbo/grip-dev/glial-local-ts/src/types.ts`

- completed: `browser_session_id` record types exist
- completed: browser session record maps to logical `glial_session_id`
- completed: browser session storage modes now include `local`, `remote`, and `both`
- clarify that normalized `session_id` payload fields mean logical `glial_session_id`
- add types for remote session summaries if separate from local session summaries
- add `GripProjector` types and capability flags

### `/Users/owebeeone/limbo/grip-dev/glial-local-ts/src/in_memory.ts`

- completed: in-memory support for browser session records exists
- add support for local and remote session catalogs in tests if useful
- completed: browser session records can now point at and reopen a logical session by mapping

### `/Users/owebeeone/limbo/grip-dev/glial-local-ts/src/indexeddb_store.ts`

- completed: browser session records now persist alongside logical session data
- completed: local session listing is supported
- completed: browser-session lookup can reopen the selected `glial_session_id`
- support the demo’s storage mode selection

### New session browser helper module in `glial-local-ts/src/`

- completed: session browser helper module exists
- completed: it reads and updates browser session records
- completed: it stays UI-agnostic so demo and future tools can reuse it

## `glial-local-py`

### `/Users/owebeeone/limbo/grip-dev/glial-local-py/src/glial_local/types.py`

- add logical `glial_session_id` wording or aliases where needed
- add remote session summary types if the Python side will also browse remote sessions
- add any browser-session-equivalent metadata only if Python has a parallel local launcher concept
- add `GripProjector` protocol or type definitions and capability flags

### `/Users/owebeeone/limbo/grip-dev/glial-local-py/src/glial_local/in_memory.py`

- support the revised logical session model
- keep backup store semantics separate from live link semantics

### `/Users/owebeeone/limbo/grip-dev/glial-local-py/src/glial_local/filesystem_store.py`

- ensure filesystem store is clearly source-state backup storage
- optionally support mirrored shared-state projection for debugging if desired

## `glial-net-ts`

### `/Users/owebeeone/limbo/grip-dev/glial-net-ts/src/client.ts`

- remaining: switch client assumptions from source-state backup to shared-state projection for Glial live attach
- completed: remote session list/load/save client calls now exist
- completed: remote session delete client call now exists
- support browser session record update after remote load
- support headed-to-headless and headed-to-headed follower hydration via passive taps
- keep pending-sync and confirmation logic for local mutations
- implement the client as a `shared-projection` projector rather than a special-case attach API

### New modules under `/Users/owebeeone/limbo/grip-dev/glial-net-ts/src/`

- add shared projection apply helpers
- completed: remote session catalog client support exists in the HTTP client
- add browser session record update helpers for “load remote session and attach”

## `glial-net-py`

### `/Users/owebeeone/limbo/grip-dev/glial-net-py/src/glial_net/client.py`

- remaining: switch client assumptions from source-state backup to shared-state projection for Glial live attach
- completed: remote session list/load/save/delete client calls now exist
- support headless hydration using passive taps
- completed: support remote session load by authenticated user plus `glial_session_id`
- support takeover requests for negotiated-primary taps
- implement the client as a `shared-projection` projector rather than a special-case attach API

### New modules under `/Users/owebeeone/limbo/grip-dev/glial-net-py/src/glial_net/`

- add shared projection apply helpers
- completed: remote session catalog client support exists in the HTTP client
- add tap materialization integration for headless runtimes

## `glial-router-py`

### `/Users/owebeeone/limbo/grip-dev/glial-router-py/src/glial_router/app.py`

- completed: remote session catalog endpoints exist
- completed: remote session load and save endpoints exist
- completed: remote session delete endpoint exists
- completed: websocket live session attach and accepted-change fanout endpoint exists
- completed: built `grip-react-demo` bundle can be served from the router at `/demo/`
- add storage mode aware session creation or attach endpoints if needed

### `/Users/owebeeone/limbo/grip-dev/glial-router-py/src/glial_router/coordinator.py`

- keep live shared-session coordination
- completed: remote source-state backup integration exists in-memory
- completed: remote source-state backup now uses a dedicated storage adapter interface
- keep shared projection generation separate from backup snapshot storage

### New storage adapter module under `/Users/owebeeone/limbo/grip-dev/glial-router-py/src/glial_router/`

- completed: dedicated remote storage adapter module exists
- completed: in-memory remote state storage keyed by user identity plus `glial_session_id` exists
- completed: filesystem remote state storage adapter exists for local development and tests
- completed: delete support for remote backup sessions exists

### New test files under `/Users/owebeeone/limbo/grip-dev/glial-router-py/tests/`

- completed: remote session catalog/load/save tests exist
- completed: remote session delete tests exist
- completed: websocket live session fanout tests exist
- add headed-to-headless shared projection tests against the FastAPI server

## `grip-react-demo`

### `/Users/owebeeone/limbo/grip-dev/grip-react-demo/src/demo_session.ts`

- completed: expanded into a browser session record manager
- completed: stores `browser_session_id -> glial_session_id`
- completed: stores local/remote/both mode on the browser session record
- completed: supports listing local sessions
- completed: supports loading remote sessions
- completed: current browser session record now distinguishes local, Glial storage, and Glial shared kinds

### `/Users/owebeeone/limbo/grip-dev/grip-react-demo/src/bootstrap.tsx`

- completed: source-state local restore still works for local mode
- completed: bootstrap now reads the browser session record instead of a raw session ID
- completed: remote session kinds now attach a Glial-backed source-state sync loop on startup

### `/Users/owebeeone/limbo/grip-dev/grip-react-demo/src/App.tsx`

- partial: App now shows the current logical session and loads existing local sessions
- completed: App now shows the current logical session kind and storage mode
- completed: controls for local, remote, or both storage mode now exist
- completed: remote shared and remote storage session load/create controls now exist

### New session browser UI files under `/Users/owebeeone/limbo/grip-dev/grip-react-demo/src/`

- completed: local session list UI exists in `App.tsx`
- completed: remote session list UI exists in `App.tsx`
- completed: “load session” actions exist for local, Glial shared, and Glial storage sessions
- partial: current routing status is visible through the session-kind display, but richer attach status is still optional

### `/Users/owebeeone/limbo/grip-dev/grip-react-demo/src/demo_session.test.ts`

- completed: browser session record tests exist
- completed: local session browse and selection tests exist
- add remote session load default-routing tests

## New Cross-Cutting Files

### New passive tap implementations

Create passive tap implementations in:

- `/Users/owebeeone/limbo/grip-dev/grip-core/src/core/` completed
- `/Users/owebeeone/limbo/grip-dev/grip-py/src/grip_py/core/`

Required behavior:

- preserve tap identity and metadata
- preserve provided grip structure
- never execute locally
- allow shared values to appear in the runtime graph

### New tap materialization registry modules

Create registry modules in:

- `/Users/owebeeone/limbo/grip-dev/grip-core/src/core/` completed
- `/Users/owebeeone/limbo/grip-dev/grip-py/src/grip_py/core/`

Required behavior:

- map persisted tap metadata to a real executable tap or passive tap
- allow headed runtimes to use real implementations
- allow headless runtimes to use passive placeholders

## Suggested Implementation Order

1. Introduce projector contracts and replace hard-coded attach assumptions in `grip-core` and `grip-py`
2. Refactor current local persistence into explicitly named source-state backup projector paths
3. Add browser session records in `glial-local-ts` and update the demo
4. Add passive taps and tap materialization registries in both runtimes
5. Add shared-state projection build and apply paths in both runtimes
6. Add remote state storage adapter and remote session catalog in `glial-router-py`
7. Update `glial-net-ts` and `glial-net-py` to implement shared-projection projectors for live sharing
8. Add local and remote session browser UI in the demo

## Immediate Next Slice

The next practical slice should be:

- add passive taps and tap materialization registries in `grip-core`
- add shared-state projection build and apply paths in `grip-core`
- update `glial-net-ts` to attach as a real shared-projection projector
- add router-backed remote session catalog and demo remote-load flow

That gives a stable base before touching live headed/headless sharing.
