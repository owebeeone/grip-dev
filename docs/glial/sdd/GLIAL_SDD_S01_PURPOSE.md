# Glial SDD Section 01: Purpose

## Overview

Glial is the optional synchronization and coordination layer for persisted Grip/Grok sessions.

The default and most important v1 use case is local session persistence inside one runtime, especially browser reload restore from a local store such as IndexedDB.

Glial is introduced only when a session must be shared, remotely saved, or attached to additional replicas such as headless or AI-enabled participants.

When Glial is enabled, its job is to let multiple runtimes participate in the same shared Grip graph state while remaining correct under:

- reconnects
- duplicated, lost, or out-of-order messages
- multiple replicas under the same session
- distributed execution ownership for selected taps

The first distributed target is shared state across JavaScript/TypeScript and Python runtimes. The system is designed so that browsers, headless workers, and AI-enabled replicas can all participate in the same session when the user chooses to share it.

## Responsibilities

When enabled, Glial is responsible for:

- identifying and routing replicas into a shared session
- assigning authoritative virtual clocks to accepted synchronized deltas
- replicating graph state entries across replicas
- providing snapshot, replay, and resync behavior
- coordinating tap ownership for primary-owned taps
- detecting replica liveness and recovering from lost primaries
- maintaining enough durable session state to recover from reconnects and shard loss

## Design Goals For V1

The v1 design optimizes for:

- correctness before efficiency
- local persistence without mandatory network dependency
- stable canonical identity across runtimes
- simple recovery rules
- minimum browser complexity
- clean separation between replicated state and local runtime machinery
- a path to later protocol optimization without changing the core model

In practical terms, that means:

- a browser session can persist and restore locally without any Glial connection
- replace-only replication for large JSON values
- full resnapshot fallback when sync certainty is lost
- authoritative Glial-issued clocks on every accepted synchronized delta
- one stable public Glial origin for browsers

## Non-Goals

Glial is not responsible for:

- authenticating users
- executing product business logic
- translating TypeScript tap code into Python tap code, or vice versa
- replicating local runtime machinery such as timers, listeners, or in-flight async requests
- selecting the final long-term delta engine during this SDD pass

## V1 Scope

The SDD covers:

- the boundary between local-only persistence and Glial-attached sharing
- the session persistence interface used by local stores and optional Glial links
- package boundaries between `grip-*`, `glial-local-*`, `glial-net-*`, and `glial-router-*`
- the replicated graph state model
- virtual clocking
- snapshot and replay behavior
- tap execution ownership
- load balancing, routing, and shard ownership
- the Glial integration boundary with external authentication

Items deferred beyond this SDD are collected in Section 13.
