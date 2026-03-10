# Glial Implementation Plan Phase 02A: Dirty-State Queue And Codecs

## Testing Plan

- add `grip-core` tests proving each persistable runtime object owns a reusable dirty-state object
- add `grip-core` tests proving repeated mutations while `is_queued=true` do not enqueue duplicates
- add `grip-core` tests proving `dirty_epoch` causes a node to be requeued if it changes during flush
- add `grip-core` tests proving explicit `set_deleted()` emits remove records even when the live object is gone
- add `grip-core` tests proving weakref loss is treated as a delete fallback rather than the primary lifecycle signal
- add `grip-core` tests proving flush order is deterministic for contexts, drips, taps, and removals
- add `grip-core` tests proving inbound persisted apply bypasses dirty enqueue and does not emit a second local dirty flush
- add `grip-core` tests proving `source="glial"` writes locally without being republished as local outbound change
- add `grip-core` tests proving hydrate restore also bypasses dirty enqueue
- add `grip-core` tests proving persisted tap records can be materialized into passive taps without local execution
- add `grip-py` tests proving the same dirty-state queue semantics as TypeScript
- add `grip-py` tests proving optional Python types such as `int | None` and `MyClass | None` are handled correctly
- add `grip-py` tests proving inbound persisted apply bypasses dirty enqueue and uses the same normalized apply path as hydrate restore
- add `grip-py` tests proving custom classes require a registered converter and that validation obeys `check_for_converter="immediate"` and `check_for_converter="lazy"`
- add `grip-py` tests proving a grip added after Grok start is validated immediately
- add `glial-local-ts` and `glial-local-py` tests proving normalized persisted records produced by dirty-state flush can be applied without backend-specific logic
- add materialization-registry tests proving an unknown tap type falls back to a passive tap rather than failing graph reconstruction

## Goal

Replace the earlier abstract "dirty refs map" discussion with a concrete runtime-owned dirty-state queue design.

This plan note defines:

- the per-node dirty-state objects
- the Grok-managed unflushed queue
- delete semantics
- reread-and-report semantics
- the inbound persisted-apply path
- tap materialization and passive-tap fallback
- Python persistence codec validation rules

## Why This Variant

The dirty-state object model is preferred because:

- each persistable runtime node carries its own reusable persistence state
- duplicate queue entries are naturally elided with `is_queued` (or epoch comparison)
- explicit remove handling is cheap
- flush work can remain backend-agnostic
- Grok only manages queueing and flush scheduling rather than detailed per-entity flag maps

The queue is still conceptually a coalescing queue, not an event journal.

The queue is only for locally originated runtime mutations.

Inbound Glial changes and local hydrate restore are not queued. They use a direct persisted-apply path.

## Core Design

### Persistable Runtime Objects

Each persistable runtime object owns one prebuilt dirty-state object:

- `GripContext` owns `ContextDirtyState`
- `Drip` owns `DripDirtyState`
- `Tap` owns `TapDirtyState`

The persisted identity is not the live object reference.

Each dirty-state object stores a canonical identity path so that a delete can still be emitted even if the runtime object has already been removed.

These dirty-state objects are for local mutation observation only.

They are not the mechanism used to apply inbound persisted changes.

### Dirty-State Base Shape

Language-neutral shape:

```python
@dataclass
class DirtyState(Generic[T]):
    node_ref: weakref.ReferenceType[T] | None
    identity: PersistIdentity
    source: PersistenceSource = "local"
    is_queued: bool = False
    deleted: bool = False
    dirty_epoch: int = 0

    def mark_dirty(self, source: PersistenceSource = "local") -> bool:
        ...

    def set_deleted(self, source: PersistenceSource = "local") -> bool:
        ...

    def report(self, codecs: PersistenceCodecRegistry) -> list[PersistedChange]:
        ...
```

Required behavior:

- `mark_dirty()` increments `dirty_epoch`
- `mark_dirty()` returns `True` only when the dirty state must be newly enqueued
- `set_deleted()` clears the live weak reference and marks the node as deleted
- `report()` emits normalized `PersistedChange` records and never writes directly to a backend

### Specialized Dirty-State Types

```python
class ContextDirtyState(DirtyState[GripContext]):
    context_changed: bool
    child_order_changed: bool

class DripDirtyState(DirtyState[Drip[Any]]):
    drip_changed: bool
    value_changed: bool
    tap_meta_changed: bool

class TapDirtyState(DirtyState[Tap]):
    tap_changed: bool
    active_outputs_changed: bool
```

`DripDirtyState` is the correct name. `GripDirtyState` is too vague because the persistable runtime node is the `Drip`, not the key definition.

### Identity Shapes

The identity must be structured enough to emit deletes after the runtime object is gone.

V1 shapes:

```python
@dataclass(frozen=True)
class ContextPath:
    path: str

@dataclass(frozen=True)
class DripPath:
    context_path: str
    grip_id: str

@dataclass(frozen=True)
class TapPath:
    home_path: str
    tap_id: str
```

## Grok Queue Contract

Grok owns:

- the unflushed queue of dirty states
- the trailing debounce timer
- the flush lifecycle flags

Suggested shape:

```python
@dataclass
class GrokPersistenceQueue:
    pending: deque[DirtyState[Any]]
    flush_scheduled: bool = False
    flush_running: bool = False
    flush_again: bool = False
```

Queue rules:

- when a dirty-state object changes, it calls `mark_dirty()`
- if `mark_dirty()` returns `True`, Grok appends that dirty-state object to `pending`
- if `is_queued=True`, the node is already pending and is not added again
- Grok flushes after a short trailing debounce

Queue exclusion rules:

- inbound Glial deltas do not call `mark_dirty()`
- hydrate restore does not call `mark_dirty()`
- collapse rewrite does not call `mark_dirty()`

## Flush Semantics

### Flush Is Reread-Based

The queue does not carry full persisted payloads.

Flush uses the dirty-state object to:

1. resolve the live runtime node through the weakref if it still exists
2. reread the current stable state from that runtime node
3. emit normalized `PersistedChange` records

This keeps the queue cheap and coalesces transient intermediate changes automatically.

### Dirty Epoch Rule

`dirty_epoch` is required to avoid dropping updates that occur during flush.

Flush behavior:

1. snapshot the dirty state's current `dirty_epoch`
2. clear `is_queued`
3. call `report()`
4. if `dirty_epoch` changed during report or write scheduling, requeue the same dirty-state object

This is the core correctness rule for overlapping runtime updates and delayed persistence.

### Deterministic Flush Ordering

The queue may be FIFO internally, but emitted records must be normalized into deterministic write order:

1. context upserts, shallowest path first
2. child-order updates, shallowest path first
3. drip upserts and value writes, sorted by context path then grip id
4. tap metadata writes, sorted by home path then tap id
5. removes, deepest path first

This means the queue object is not itself the durable ordering contract. The emitted change list is.

## Persisted-Apply Path

The runtime needs a second path in addition to the local dirty-flush path.

This persisted-apply path is used for:

- local hydrate restore
- inbound Glial snapshot reset
- inbound Glial replay
- inbound Glial live deltas

Rules:

- persisted apply writes normalized records into the local store as they are accepted
- persisted apply updates runtime graph state directly
- persisted apply runs under dirty-state suppression
- persisted apply does not allocate new local `origin_mutation_seq` values
- persisted apply must not republish inbound Glial changes as new local outbound changes

Required apply primitives:

- `apply_context_upsert`
- `apply_context_remove`
- `apply_child_order`
- `apply_drip_upsert_or_value`
- `apply_drip_remove`
- `apply_tap_meta`
- `apply_tap_remove`

## Delete Semantics

Explicit delete wins over GC.

Rules:

- runtime-managed removal must call `set_deleted()`
- weakref loss is only a fallback indicator for delete
- a dead weakref without explicit delete should still emit a remove record, but should also be treated as a useful debugging signal

Add-then-remove and remove-then-recreate within one debounce window are resolved by final live state:

- add then remove before flush: remove only, or collapse away during compaction
- remove then recreate with same identity before flush: final upsert wins and the delete is dropped

## Hook Points

The dirty-state objects are owned by the runtime nodes, but Grok-integrated hooks are needed to mark them dirty at the right times.

### Context Hooks

- context created
- parent added or removed
- child list changed
- context explicitly removed

### Drip Hooks

- drip created
- drip value changed
- drip explicitly removed
- tap metadata affecting the drip changed

### Tap Hooks

- tap attached
- tap detached
- active output set changed
- execution mode or role metadata changed if persisted

## Reporting Contract

`report()` must emit normalized persistence records, not backend calls.

This keeps the dirty-state layer reusable for:

- local-only persistence
- Glial-linked persistence
- tests using in-memory stores

`report()` may emit more than one record for a single node if that is the normalized shape.

Examples:

- `ContextDirtyState.report()` may emit:
  - one context upsert
  - one child-order record
- `DripDirtyState.report()` may emit:
  - one drip upsert or value record
  - one drip tap-metadata record
- `TapDirtyState.report()` may emit:
  - one tap metadata record

The dirty-state `report()` path is only for locally originated runtime mutations.

Inbound persisted application already starts with normalized `PersistedChange` records and therefore bypasses `report()`.

## Tap Materialization Registry

Persisted tap records do not contain executable code.

When a persisted snapshot or delta creates or updates tap structure, the runtime must reify that tap record through a local materialization registry.

The registry decides whether to create:

- a real executable local tap
- a passive tap placeholder

Passive taps are required for:

- follower-only replicas
- headless runtimes that should preserve graph shape but not execute local tap logic
- runtimes that recognize the persisted graph shape but do not implement that tap type locally

The registry must therefore support:

- lookup by persisted `tap_type`
- construction of a real local tap when execution is allowed
- fallback creation of a passive tap when execution is not allowed or no local implementation exists

## Value Serialization

Value serialization is not part of the dirty queue itself.

It belongs to a persistence codec registry used by `report()`.

### TypeScript Rules

V1 TypeScript keeps this simple:

- JSON-compatible values persist as-is
- no special converter provider is required by default
- custom TS codecs can be added later if class-instance support becomes necessary

### Python Rules

Python needs explicit registry behavior because runtime type information is richer.

V1 rules:

- JSON-native Python values need no converter:
  - `None`
  - `bool`
  - `int`
  - `float`
  - `str`
  - `list[...]` when the contained type is persistable
  - `dict[str, ...]` when the contained type is persistable
- `T | None` is handled automatically by unwrapping the optional type
- custom classes require a registered converter for the non-optional class
- arbitrary multi-branch unions beyond optional are deferred

Examples:

- `int | None`: automatic
- `list[int]`: automatic
- `MyClass | None`: requires converter for `MyClass`
- `A | B | None`: deferred in v1

### Python Registry Validation Policy

The Python registry should support:

- `check_for_converter="immediate"`
- `check_for_converter="lazy"`

Rules:

- `immediate`: validate converter requirements when the grip is registered
- `lazy`: validate when Grok persistence starts or when the grip is first persisted or hydrated
- if Grok is already started and a new grip is added, validation is immediate even in lazy mode

This is enough for v1.

## Expected Code Areas

TypeScript:

- `grip-core/src/core/grok.ts`
- `grip-core/src/core/context.ts`
- `grip-core/src/core/drip.ts`
- `grip-core/src/core/base_tap.ts`
- tap materialization registry support in `grip-core` runtime integration
- new persistence coordination module under `grip-core/src/core/` or `grip-core/src/persistence/`

Python:

- `grip-py/src/grip_py/core/grok_impl.py`
- `grip-py/src/grip_py/core/context.py`
- `grip-py/src/grip_py/core/drip.py`
- `grip-py/src/grip_py/core/base_tap.py`
- tap materialization registry support in `grip-py`
- Python registry converter support in the grip registry or a closely related module

## Work Items

1. Add per-node dirty-state ownership to contexts, drips, and taps.
2. Add Grok-managed queueing and debounce scheduling.
3. Add normalized `report()` emission for each dirty-state subtype.
4. Add explicit delete plumbing so runtime removals call `set_deleted()`.
5. Add dirty-epoch requeue behavior.
6. Add persisted-apply primitives that update runtime state under dirty suppression.
7. Add tap materialization registry support plus passive tap fallback.
8. Add TypeScript JSON-pass-through serialization wiring.
9. Add Python converter protocol, registration, and validation policy.
10. Keep all emitted records and persisted-apply operations backend-agnostic and compatible with `glial-local-*` stores.

## Exit Criteria

- every persistable runtime node has a reusable dirty-state object
- duplicate dirty queue entries are elided through `is_queued`
- flush rereads live node state and emits normalized persistence records
- explicit remove and weakref-fallback delete behavior are both covered by tests
- inbound persisted apply bypasses dirty enqueue and updates runtime state directly
- tap materialization registry can create either real taps or passive taps during persisted apply
- Python converter validation is implemented with immediate and lazy modes
- TypeScript remains JSON-first with no mandatory custom codec provider in v1

## Non-Goals

- no attempt to persist arbitrary Python unions beyond optional types
- no custom TypeScript class-instance persistence in v1
- no backend-specific writes from dirty-state objects
- no Glial transport behavior in this phase note
