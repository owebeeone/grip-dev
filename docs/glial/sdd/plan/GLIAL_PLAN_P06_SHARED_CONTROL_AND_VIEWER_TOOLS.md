# Glial Implementation Plan Phase 06: Shared Control And Viewer Tools

## Testing Plan

- add integration tests for a Python control client listing local and remote sessions, attaching to a chosen `glial_session_id`, and reading the routed shared projection
- add integration tests for listing contexts, drips, and taps from a shared session without application-specific tap code loaded locally
- add integration tests for negotiated-primary request, grant, release, and fallback through the FastAPI Glial router
- add integration tests proving a control client can set JSON-compatible shared values by canonical `grip_id` and that headed replicas converge on the result
- add tests proving unknown `grip_id` values materialize dynamically in generic viewer and control clients
- add tests proving local typed grip definitions are only used when compatible and mismatches fall back to raw generic grips with diagnostics
- add headed-to-headless tests proving the Python control client can inspect passive taps and request primary takeover for a supported tap
- add web viewer tests proving a routed shared session can be rendered from a raw shared-session Grok mapped into a viewer Grok
- add tests proving the viewer remains stable as contexts, taps, and active outputs are added, removed, or replaced by matcher-driven changes
- add cross-runtime tests proving a browser viewer, a headed demo runtime, and the Python control client all observe the same routed session state

## Goal

Build the generic tooling needed to operate and inspect a live Glial-routed session without depending on the original application UI code.

This phase introduces:

- a Python command-driven control client
- a generic React viewer application
- dynamic shared-grip materialization for unknown routed graphs

## Why This Phase Exists

The current codebase has:

- local source-state persistence
- remote backup storage
- routed source-state synchronization for the demos

It does not yet have a generic way to:

- inspect any routed session by canonical graph identity
- list taps and request negotiated primary ownership
- drive a session from a headless or AI-oriented client
- render an arbitrary shared graph in a generic viewer when the application grip registry is unknown or mismatched

This phase closes that gap.

## Scope

- Python control client for shared session inspection and control
- generic web viewer for routed shared sessions
- dynamic grip materialization for generic shared clients
- mismatch-safe handling when canonical `grip_id` values do not match local typed definitions
- lease and negotiated-primary controls exposed through tooling
- routed shared-state inspection of contexts, drips, taps, values, and ownership metadata

## Out Of Scope

- natural-language AI behavior itself
- production auth UX beyond the existing authenticated-user assumptions
- final visual polish of the generic web viewer

## Python Control Client

Create a Python app, tentatively `glial-control-py`, that can operate as a CLI first and optionally grow a REPL later.

Required capabilities:

- list local sessions
- list remote sessions
- select or attach a session by `glial_session_id`
- show routed session metadata and replica identity
- list contexts
- list drips and current values
- list taps, modes, roles, provides, purpose, and description
- request negotiated primary for a tap
- release negotiated primary for a tap
- set or replace a shared drip value by canonical `grip_id`
- watch the routed session for live changes

The client must work without the original application tap implementations loaded locally.

## Generic Web Viewer

Create a separate React app, tentatively `glial-viewer-ts`, not the existing `grip-react-demo`.

The viewer should use Grip internally and keep two distinct Groks:

1. a raw shared-session Grok
2. a viewer Grok

### Raw Shared-Session Grok

Responsibilities:

- mirror the routed shared projection faithfully
- create generic grips dynamically by canonical `grip_id`
- materialize passive taps and current values
- surface mismatch diagnostics where the local type registry cannot safely bind a grip

### Viewer Grok

Responsibilities:

- provide stable viewer-focused grips and contexts
- derive browseable UI state from the raw shared-session Grok
- support filtered views such as sessions, contexts, taps, leases, and value inspectors

This keeps the viewer UI stable even when the routed shared graph changes shape.

## Dynamic Grip Materialization Rules

Generic shared clients must support graphs that contain grips they have never seen before.

Rules:

- canonical `grip_id` is the durable identity
- unknown grip IDs materialize as generic JSON-value grips
- known grip IDs may bind to local typed grip definitions only when the shared value encoding is compatible
- incompatible or unknown grip IDs must remain in generic raw form
- mismatch state must be visible in debug or viewer tooling

## Router And Client Work Needed

Phase 06 depends on extending the current router and client code from source-state session sync to true shared-projection inspection and control.

Required additions:

- list taps, contexts, drips, and lease state from the routed shared session
- negotiated-primary request and release endpoints
- server-issued lease updates and fallback notifications
- shared projection subscription stream suitable for a control client and a viewer
- client-side helpers in `glial-net-py` and `glial-net-ts` for these operations

## Expected Code Areas

New packages:

- `/Users/owebeeone/limbo/grip-dev/glial-control-py`
- `/Users/owebeeone/limbo/grip-dev/glial-viewer-ts`

Existing packages likely to change:

- `/Users/owebeeone/limbo/grip-dev/glial-router-py`
- `/Users/owebeeone/limbo/grip-dev/glial-net-py`
- `/Users/owebeeone/limbo/grip-dev/glial-net-ts`
- `/Users/owebeeone/limbo/grip-dev/grip-core`
- `/Users/owebeeone/limbo/grip-dev/grip-py`

## Work Items

1. Finish true shared-projection routing in `glial-net-ts` and `glial-net-py` rather than polling source-state snapshots.
2. Expose shared-session graph inspection endpoints and lease negotiation endpoints from `glial-router-py`.
3. Add dynamic generic shared-grip materialization support where a local typed grip registry is absent or incompatible.
4. Build the Python control client on top of the routed shared-projection APIs.
5. Build the React viewer with a raw shared-session Grok feeding a stable viewer Grok.
6. Add mismatch diagnostics and raw JSON value editing support for generic clients.
7. Add headless takeover flows for negotiated-primary taps where a local implementation exists.

## Exit Criteria

- a Python control client can inspect and control a routed shared session without application-specific UI code
- a generic React viewer can browse an arbitrary routed shared session
- unknown or mismatched grips do not break hydration and are visible as generic raw shared values
- negotiated-primary requests can be issued and observed from the control client
- headed demo runtimes, the viewer, and the control client all converge on one routed shared session

## Current Status

This phase is now partially implemented.

Implemented:

- local backup and restore
- remote session backup storage
- router-hosted React demo bundle
- router-hosted `glial-viewer-ts` bundle
- routed demo session sync by polling source-state snapshots
- shared-session snapshot publishing from headed demos
- passive taps and shared-projection helpers in `grip-core`
- Python shared projection hydrate and passive tap materialization support
- dynamic shared-grip materialization for unknown canonical `grip_id` values
- Python control client with session listing, graph inspection, lease negotiation, release, and value updates
- generic React viewer with routed shared-session browsing, lease requests, and shared value updates
- UI tests for viewer session load, refresh, lease request, and value updates

Still remaining if we want the full end-state described earlier:

- live shared-projection subscription instead of poll-based refresh
- true `GripProjector`-style Glial client attachment for shared sessions
- explicit mismatch diagnostics in the viewer when local typed grips do not safely bind
- stronger multi-client convergence tests across headed demo, viewer, and Python control client in one run
