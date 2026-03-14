# Glial Next Issues

This note records what remains after the current SDD pass.

## No blocking pre-SDD issues remain

The current Glial SDD pass has enough resolved detail to move to phased planning.

## Remaining item: post-SDD delta protocol selection

Protocol engine selection is intentionally deferred until after the SDD.

Question:
- which replication or delta tool should be trialed first for JavaScript/TypeScript and Python if Glial later moves beyond replace-only large JSON entries?

## Optional tuning after planning starts

These are not blocking architecture issues:

- lease and heartbeat tuning
- replay retention tuning
- transport optimization
- richer authorization policy

## Adjacent follow-on design

This is not a blocker for the Glial SDD, but it should be designed explicitly during planning:

- concrete `GripSessionPersistence` implementations for IndexedDB, filesystem, and Glial-linked modes
- generic shared-tool grip materialization and mismatch diagnostics for viewer or control clients
- projector-grade live shared-session routing for headed demos and Python clients beyond the current viewer websocket path
