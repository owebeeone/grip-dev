# Glial SDD Section 08: Tap Execution Ownership

## Overview

Glial does not replicate tap code. It coordinates which replica is allowed to execute a tap whose outputs are shared.

This means:

- TypeScript taps are not translated into Python taps
- Python taps are not translated into TypeScript taps
- different runtimes may have local implementations associated with the same semantic tap identity
- synchronization happens through shared state outputs, not shared executable code

This section applies to live shared projection. It does not change the simpler backup-restore rule where a capable local runtime may restore source-state and rerun its own taps normally.

## Ownership Modes

### `replicated`

All replicas may apply the tap behavior locally.

Use this for:

- simple state-setting behavior
- `AtomValueTap`-style updates
- other cases where replicated local application is harmless and deterministic

### `origin-primary`

The replica where the tap originates is the default primary executor.

Use this for:

- `FunctionTap` by default
- `AsyncTap` by default
- taps that should not execute redundantly across replicas

Non-origin replicas are followers.

### `negotiated-primary`

A replica may request primary execution ownership through Glial lease negotiation.

Use this for:

- tool-driving taps
- headless backend integrations
- AI- or service-specific taps that must run on a designated environment

## Replica Roles

For any given tap instance, a replica is in one of two runtime roles:

- `primary`
- `follower`

Rules:

- primaries execute the tap and publish synchronized outputs
- followers do not execute the tap and instead wait for replicated outputs

## Default Mode Selection

Recommended v1 defaults:

- `AtomValueTap` -> `replicated`
- `FunctionTap` -> `origin-primary`
- `AsyncTap` -> `origin-primary`
- service, AI, or tool taps -> `negotiated-primary`

These defaults can be overridden by explicit tap configuration.

## Origin Primary And Fallback

For `origin-primary` taps:

- the origin replica is primary while present
- if a negotiated primary temporarily supersedes it, the origin remains the fallback owner
- if the negotiated primary disappears, the origin resumes immediately if still present

## Negotiated Primary

For `negotiated-primary` taps:

- the candidate replica requests ownership from Glial
- Glial grants, denies, renews, or revokes the lease
- all replicas learn ownership through Glial broadcast messages

Glial is the only authority that can assign negotiated-primary ownership.

## Tap Metadata In Export

Tap export metadata must include:

- `mode`
- replica-local `role`
- provided grips
- home and destination parameter grips
- optional cache metadata or cache state

This allows tools and AI systems to understand not only what a tap can provide, but also whether the local replica is actively executing it.

## Tap Materialization Registry

Persisted tap metadata is not enough by itself to recreate executable tap behavior.

Runtimes therefore require a tap materialization registry that maps persisted tap metadata to a local runtime tap instance.

The registry is responsible for deciding whether a persisted tap record becomes:

- a real executable local tap
- a passive non-executing placeholder tap

This is necessary because:

- Glial does not replicate tap code
- one runtime may know how to execute a tap type while another does not
- a replica may intentionally follow rather than execute even when it recognizes the tap type

## Passive Taps

V1 permits passive taps.

A passive tap is a local runtime tap object that preserves graph shape and persisted metadata but does not execute tap logic locally.

Use cases:

- headless replicas that never execute local tap behavior
- follower replicas for `origin-primary` or `negotiated-primary` taps
- replicas that understand a tap record structurally but do not have a local executable implementation for that tap type
- AI-facing replicas that need graph understanding and value mutation capabilities without local application tap code

Passive taps must:

- preserve tap identity and metadata
- preserve provided grip structure
- remain non-executing locally
- allow the runtime graph to faithfully represent the persisted shared graph

Passive taps may still allow:

- direct value setting for replicated state grips
- primary-takeover requests for negotiated-primary taps

They must not:

- run function or async evaluation locally unless promoted to a real executable tap implementation through the local registry and Glial ownership rules

## Registry Decision Rules

When materializing a persisted tap record, the runtime should:

1. look up the tap type in the local materialization registry
2. if a local executable implementation exists and local policy allows execution, create the real tap
3. otherwise create a passive tap

This keeps structural graph fidelity separate from local execution capability.

## Headed Versus Headless Rules

### Headed Runtime Restore

A headed runtime with real application tap code should:

1. register its normal taps, factories, and matcher bindings
2. restore source-state values into stateful source taps
3. let the runtime recompute derived and async outputs as needed

### Shared Follower Or Headless Runtime

A follower or headless runtime should:

1. materialize passive taps from the shared-state projection
2. apply replicated drip values directly from Glial
3. avoid local execution of function and async taps by default

This is the key distinction between:

- backup restore into a capable application runtime
- live shared projection into a follower or headless runtime
