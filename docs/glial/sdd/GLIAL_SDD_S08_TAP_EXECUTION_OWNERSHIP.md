# Glial SDD Section 08: Tap Execution Ownership

## Overview

Glial does not replicate tap code. It coordinates which replica is allowed to execute a tap whose outputs are shared.

This means:

- TypeScript taps are not translated into Python taps
- Python taps are not translated into TypeScript taps
- different runtimes may have local implementations associated with the same semantic tap identity
- synchronization happens through shared state outputs, not shared executable code

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
