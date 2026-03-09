# Glial SDD Section 13: Deferred Items

## Post-SDD Delta Engine Selection

The final replication or delta engine is intentionally deferred until after this SDD.

Initial evaluation scope after the SDD:

- JavaScript/TypeScript
- Python

## Fine-Grained JSON Replication

V1 uses replace-only replication for large mutable JSON at entry granularity.

Deferred work:

- path-level JSON patch semantics
- CRDT-style structured merge for large documents
- tool selection for fine-grained blob replication
- tombstones or delete-retention semantics needed for true offline queued mutation replay

## Protocol Optimizations

The first implementation prioritizes correctness.

Deferred optimizations include:

- smarter incremental repair instead of full resnapshot on sync uncertainty
- transport-aware batching and chunking optimization
- replay pruning strategies driven by observed client cursors
- optional separate mutation acceptance acknowledgements

## Non-JavaScript/Non-Python Targets

The SDD is written to keep future expansion possible, but cross-runtime implementation work is deferred for:

- Kotlin or Java
- Swift
- additional mobile or embedded environments

## Richer Authorization Policy

The Glial core boundary with authentication is defined, but richer authorization policy remains future work.

Deferred items include:

- capability-based policy
- more detailed per-operation authorization rules
- audit policy beyond basic coordination tracing
