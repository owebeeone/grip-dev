# Glial SDD Section 16: Session Modes And Shared Projection

## Overview

Glial must support three related but distinct use cases:

1. local backup and restore
2. remote backup and restore
3. live shared projection across headed and headless replicas

These are not the same persistence product.

The design rule is:

- backup restore exists to rebuild a capable application runtime
- live shared projection exists to synchronize the current materialized graph across mixed replicas

## Session Records

### Browser Session Record

The browser keeps a browser-local record containing:

- `browser_session_id`
- `glial_session_id`
- storage mode: `local`, `remote`, or `both`
- attach mode: detached or Glial-routed

This is the record that survives reload and determines what logical session the browser should reopen.

### Glial Session Record

The logical persisted or shared session is keyed by `glial_session_id`.

This record may exist:

- only locally
- remotely in Glial-backed storage
- in both places

## Storage Modes

### Local

Local mode means:

- backup is written locally
- restore comes from the local store
- Glial is not required

### Remote

Remote mode means:

- backup is written to a remote authenticated Glial state store
- loading that remote session in the browser should by default attach it as a Glial-routed session

### Both

Both mode means:

- local backup is maintained
- remote backup is maintained
- the browser may still attach live to Glial when requested

## Headed Runtime Rules

A headed runtime with the full application code should:

1. register normal taps, tap factories, and matcher bindings
2. restore source-state backup values into stateful taps
3. let matcher selection and derived taps converge from that restored source state

This is true for:

- local restore
- remote backup restore

## Follower And Headless Rules

A follower or headless runtime should not be expected to recreate the application by rerunning tap logic.

Instead it should:

1. materialize passive taps from the shared-state projection
2. accept replicated context, drip, and tap metadata
3. accept replicated current values for function and async tap outputs
4. remain non-executing by default unless promoted through Glial ownership rules

This is the required model for:

- headed to headed follower replicas
- headed to headless replicas
- AI graph inspection

## Matcher Rules

Matchers are local executable policy.

Rules:

- capable headed restore reruns matchers after source-state hydrate
- follower and headless replicas do not rely on matcher reevaluation to reconstruct the live shared graph
- therefore the shared-state projection must carry the currently active tap set and actual outputs

## Async And Function Tap Rules

### Backup Restore

For backup restore:

- function and async outputs do not need to be persisted generically
- stateful source values are restored first
- function and async taps then recompute or refetch as needed

Async tap cache state is optional and tap-specific.

### Shared Projection

For live sharing:

- followers and headless replicas receive the current output state of function and async taps from Glial
- those taps are normally passive locally
- a primary executor is responsible for publishing the authoritative shared outputs

## AI Readability Requirements

An AI or headless runtime must be able to understand what a passive tap represents.

The hydrated shared graph therefore needs:

- stable tap identity
- tap type
- provided grips
- home and destination parameter grips
- current values
- execution mode and local role
- optional `purpose` and `description`

This metadata is what lets an AI understand:

- what a tap does
- which grips it controls
- whether it is primary or follower
- whether it is safe to request takeover

## AI Takeover Model

An AI or tool-driven replica may request negotiated primary ownership for a tap.

After lease grant:

- the passive tap may be replaced with a real executable local implementation if one exists
- or a tool-specific executable tap may be installed locally
- the new primary then publishes shared outputs back through Glial

This is how a headless or AI replica can override function or async behavior without requiring other replicas to run the same code.

## Remote Session Load Rule

When a browser loads a remote session, the default behavior is:

1. resolve the remote session by authenticated user identity plus `glial_session_id`
2. hydrate the local browser session record to point at that `glial_session_id`
3. attach the browser as a Glial-routed replica rather than as a detached copy

This keeps remote session load aligned with the live shared-session model rather than silently forking the session.
