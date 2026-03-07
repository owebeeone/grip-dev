# GRIP_PY Grok/Context Spec
Date: 2026-03-08
Status: Draft
Scope: `grip-py` context graph and Grok orchestration runtime

Related:
- `docs/GRIP_PY_DESIGN_SPEC.md` (Grip/Registry)
- `docs/GRIP_PY_DRIP_PROPOSAL.md` (Drip)
- `docs/GLIAL_SYSTEM_SPEC.md` (Glial kernel-level constraints)

## 1. Purpose

Define an implementation-ready design for `grip-py` Grok + Context graph, aligned with `grip-core` semantics where valid for Python, while preserving the current Drip design choice:

- keep `Drip.next(...)` non-blocking and synchronous
- do not expand Drip API in this phase
- implement context graph, resolver, and minimal tap support first

This document also defines a comprehensive unit-test parity plan against `grip-core`.

## 2. Scope and Non-Goals

In scope:
- `Grok`, `GripContext`, `GripContextNode`, graph lifecycle
- parent/child DAG semantics and priority inheritance
- producer/consumer linking and re-linking
- query-to-drip wiring (`grok.query(...) -> Drip[T]`)
- deterministic task queue and `grok.flush()` for tests
- minimal tap API + minimal concrete test tap implementations

Out of scope in this phase:
- full async tap stack (`AsyncTap`, retry, refresh, history)
- advanced matcher/query-evaluator integration (deferred phase)
- network transport and Glial relay concerns

## 3. Compatibility With `grip-core`

## 3.1 What ports directly

The following model is compatible and should be mirrored:
- context DAG with parent priorities
- nearest-provider resolution with shadowing by proximity/key
- one logical consumer drip per `(context, grip)`
- deferred zero-subscriber cleanup
- node-level provider/consumer bookkeeping
- explicit `grok.flush()` test barrier

## 3.2 Python-specific adaptations required

1. Use weakrefs for lifecycle identity, but do not use weak callbacks for core delivery.
2. Keep task scheduling strong; weak ownership checks happen inside callbacks.
3. Ensure any slotted classes intended for weakrefs include weakref support.
4. Keep graph mutations single-loop confined (or lock-protected entrypoint).
5. Provide explicit disposal/sweep paths; do not rely purely on GC timing.

## 3.3 Weak-task simplification decision

Do not implement a weak-callback queue in `grip-py`.

Instead:
- schedule strong wrappers on loop/task queue
- wrapper resolves weak owner reference at execution time
- callback no-ops if owner is gone/disposed

Example pattern:

```python
owner_ref = weakref.ref(node)

def run() -> None:
    owner = owner_ref()
    if owner is None or owner.disposed:
        return
    owner._zero_check_callback()

loop.call_soon(run)
```

This avoids nondeterministic dropped deliveries from callback GC.

## 4. Runtime Architecture

## 4.1 Core classes

1. `Grok`
- owns registry, graph, resolver, task queue
- exposes `query`, `register_tap`, `unregister_tap`, `flush`, `create_context`

2. `GripContext`
- public context object
- stores parent links with priorities
- delegates internal operations to `GripContextNode`

3. `GripContextNode`
- internal node for context graph
- tracks parents, children, producers, consumers, resolved providers
- owns node-level cleanup and consumer lifecycle hooks

4. `GrokGraph`
- `id -> node` registry
- sweep/reap logic
- edge cleanup and integrity helpers

5. `TaskQueue`
- deterministic ordering
- `submit`, `submit_weak_owner` (wrapper-based), `flush`

6. `SimpleResolver`
- producer selection and re-linking
- handles add/remove producer, add/remove consumer, parent relinking

## 4.2 Reference model for key maps

On `GripContextNode`:
- `producers: dict[Grip[Any], ProducerRecord]`
- `consumers: dict[Grip[Any], weakref.ref[Drip[Any]]]`
- `deleted_consumers: dict[Grip[Any], weakref.ref[Drip[Any]]]` (optional re-use window parity)
- `resolved_providers: dict[Grip[Any], GripContextNode]`
- `parents: list[ParentRef]` sorted by ascending priority
- `children: list[GripContextNode]`

## 4.3 Lifecycle invariants

1. Node exists while referenced in active graph map.
2. Context object may be GC'd; node may remain until sweep conditions hold.
3. Node can be swept only when:
- context weakref is dead
- no live consumers
- no children
4. Removing node must unlink both directions:
- remove self from parents' children
- remove self from children's parents

## 5. Concurrency and Execution Model

1. `Grok` and resolver operations execute on one event loop thread by default.
2. Cross-thread entrypoints must use thread-safe scheduling (`call_soon_threadsafe`).
3. Task queue ordering must be deterministic (priority, then FIFO for ties).
4. `grok.flush()` is synchronous and drains pending internal task queue work.
5. Drip async subscriber completion is not awaited by `grok.flush()` in this phase.

## 6. Minimal Tap API for This Phase

## 6.1 Protocol surface

A minimal tap protocol is sufficient for context/grok testing:

```python
class Tap(Protocol):
    provides: tuple[Grip[Any], ...]

    def on_attach(self, home_context: GripContext) -> None: ...
    def on_detach(self) -> None: ...
    def on_connect(self, dest_context: GripContext, grip: Grip[Any]) -> None: ...

    def produce(self, *, dest_context: GripContext | None = None) -> None: ...
```

Also include optional destination lifecycle hooks for parity with `destination_lifecycle.spec.ts`:

```python
class TapDestinationContext(Protocol):
    def drip_added(self, grip: Grip[Any]) -> None: ...
    def drip_removed(self, grip: Grip[Any]) -> None: ...
    def on_detach(self) -> None: ...
```

## 6.2 Test-only concrete taps

Implement minimal test taps in `tests/core/helpers/test_taps.py`:
- `TestValueTap`: fixed values for `provides`
- `MultiValueTestTap`: map-based values for multiple grips
- `DestinationContextTestTap`: exposes per-destination context callbacks

These are sufficient to test graph semantics before production taps exist.

## 7. Planned File Layout

```text
grip-py/src/grip_py/core/
  grip.py                      # already implemented
  drip.py                      # already implemented
  task_queue.py                # new
  tap.py                       # new (Protocol/base types)
  base_tap.py                  # new (optional thin helper)
  context.py                   # new
  graph.py                     # new
  tap_resolver.py              # new
  grok.py                      # new
  use_grip.py                  # update to use real Grok.query

grip-py/tests/core/
  helpers/
    test_taps.py               # new
  test_task_queue.py           # new
  test_context.py              # new
  test_graph_gc.py             # new
  test_engine.py               # new
  test_tap_resolver.py         # new
  test_destination_lifecycle.py# new
  test_query.py                # phase 2
  test_matcher.py              # phase 2
```

## 8. Unit Test Parity Plan (Comprehensive)

Goal: replicate `grip-core` behavior coverage for Grok/Context stack before broadening taps.

## 8.1 Phase 1 (must-have before full taps)

### A. Task queue parity
Source: `grip-core/tests/task_queue.test.ts`

Target: `grip-py/tests/core/test_task_queue.py`

Scenarios:
1. lower numerical priority runs first
2. FIFO for equal priority
3. auto-flush behavior (if enabled)
4. cancellation of pending tasks
5. cancel-all behavior
6. randomized ordering/state scenario

Note: exclude weak-callback GC-drop semantics by design.

### B. Engine shared drip semantics
Source: `grip-core/tests/engine.spec.ts`

Target: `grip-py/tests/core/test_engine.py`

Scenarios:
1. repeated query returns same drip instance for same `(ctx, grip, provider)`
2. multi-subscriber behavior + first/zero subscriber callbacks
3. zero-subscriber drip re-use window behavior
4. parameter-driven updates re-evaluate output
5. register/unregister taps propagates to descendants
6. proximity-based provider selection independent of registration order

### C. Resolver scenarios (all 16)
Source: `grip-core/tests/tap_resolver.spec.ts`

Target: `grip-py/tests/core/test_tap_resolver.py`

Scenarios 1..16 must be ported:
1. simple case
2. transitive case
3. shadowing by ancestor
4. priority-based resolution
5. shadowing by key
6. dynamic re-parenting
7. parent removal and relinking
8. producer removal fallback
9. add shadowing producer
10. no producer available
11. consumer in same context as producer
12. remove consumer
13. fallback to ancestor after self-producer removal
14. root de-prioritization behavior
15. diamond dependency resolution
16. cascading relinking after producer removal

Also port delta-application tests (`applyProducerDelta` equivalent) if evaluator layer is present.

### D. Destination lifecycle
Source: `grip-core/tests/destination_lifecycle.spec.ts`

Target: `grip-py/tests/core/test_destination_lifecycle.py`

Scenarios:
1. `dripAdded` on grip attach
2. `dripRemoved` on grip removal
3. `onDetach` when last grip removed
4. `onDetach` via forced destination cleanup
5. per-destination context retrieval behavior
6. independent contexts across multiple destinations

### E. GC cleanup and graph integrity
Source: `grip-core/tests/gc_cleanup.spec.ts`

Target: `grip-py/tests/core/test_graph_gc.py`

Scenarios:
1. stale child references are cleaned during sweep
2. complex parent-child cleanup preserves valid links
3. sanity check detects and cleans orphaned references

## 8.2 Phase 2 (query/matcher integration parity)

### A. Query builder/helpers
Source: `grip-core/tests/query.spec.ts`
Target: `grip-py/tests/core/test_query.py`

### B. Matcher integration
Source: `grip-core/tests/matcher.spec.ts`
Target: `grip-py/tests/core/test_matcher.py`

### C. Tap matcher integration with resolver
Source: `grip-core/tests/tap_matcher.integration.spec.ts`
Target: `grip-py/tests/core/test_tap_matcher_integration.py`

## 8.3 Phase 3 (full async tap stack parity)

Port coverage from:
- `async_tap.spec.ts`
- `async_retry.spec.ts`
- `async_state_transitions.spec.ts`
- `async_state_history.spec.ts`
- `async_state_publishing.spec.ts`
- `async_listener_tracking.spec.ts`

This phase depends on production `AsyncTap` and async request-state model.

## 9. Follow-on Tap Implementation Phases

## 9.1 Phase A: minimal test tap surface

Purpose:
- unblock Grok/context graph and resolver parity tests

Deliverables:
- protocol + tiny base tap
- test helper taps only

## 9.2 Phase B: production taps (core)

1. `AtomTap`
- fixed/simple state provider
- explicit set/update APIs
- immediate publish path

2. `FunctionTap`
- derives outputs from inputs/params
- deterministic recompute behavior

3. `AsyncTap`
- async request lifecycle
- cancellation, retry, refresh
- shared request state per destination key
- listener-aware scheduling

## 9.3 Phase C: query-evaluator/matcher-driven tap attribution

- declarative query binding
- attribution delta application
- partition merge/split behavior parity

## 10. Milestones and Acceptance Criteria

## Milestone M1: Context graph foundation

Accept when:
- task queue parity tests pass (phase 1A)
- engine + resolver 1..16 tests pass (phase 1B, 1C)
- destination lifecycle + GC cleanup tests pass (phase 1D, 1E)

## Milestone M2: Query/matcher integration

Accept when:
- query + matcher parity tests pass (phase 2)
- no regressions in M1 suite

## Milestone M3: Async tap stack

Accept when:
- async tap/retry/state/listener tracking suites pass (phase 3)
- performance and cancellation behavior validated under concurrency

## 11. Implementation Order Recommendation

1. `task_queue.py`
2. `context.py` + `graph.py` node lifecycle
3. minimal `tap.py` + test taps
4. `tap_resolver.py`
5. `grok.py` + `grok.flush()`
6. phase 1 parity tests
7. phase 2 query/matcher
8. phase 3 production taps (Atom -> Function -> Async)

## 12. Open Decisions

1. Keep `deleted_consumers` re-use window parity exactly, or simplify and rely on fresh Drip creation?
2. Expose graph sanity checks publicly (`grok.get_graph_sanity_check`) or keep test-only hooks?
3. Keep manual `grok.flush()` only, or also provide an async flush barrier in later phase?
