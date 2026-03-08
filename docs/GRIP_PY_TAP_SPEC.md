# GRIP_PY_TAP_SPEC
Date: 2026-03-08
Status: Implemented baseline (phase-tracked parity with `grip-core`)
Scope: Tap model, Tap API, and Tap test/implementation plan for `grip-py`

## 1. Purpose
Define and track the Tap model for `grip-py` while maintaining implementation parity targets.

This spec focuses on:
- Base Tap destination handling (including destination parameters)
- FunctionTap synchronous behavior with destination-aware inputs
- AsyncTap optional features (concurrency, cancellation, cache TTL, in-flight retention)
- Partial-output overlap and per-grip attribution semantics for matcher integration
- A strict TDD implementation process and acceptance artifacts

## 2. Alignment Target
Primary behavioral target is `grip-core` in:
- `src/core/base_tap.ts`
- `src/core/function_tap.ts`
- `src/core/async_tap.ts`
- `src/core/graph.ts`
- `src/core/tap_resolver.ts`
- `src/core/query_evaluator.ts`
- `src/core/matcher.ts`

For Python, API shape may differ where needed, but semantics should match unless explicitly noted.

## 3. Core Tap Model
## 3.1 Tap Interface (Python)
Every Tap must define:
- `provides: tuple[Grip[Any], ...]`
- `destination_param_grips: tuple[Grip[Any], ...] | None`
- `home_param_grips: tuple[Grip[Any], ...] | None`
- `on_attach(home_context)`
- `on_detach()`
- `on_connect(dest_context, grip)`
- `on_disconnect(dest_context, grip)`
- `produce(*, dest_context: GripContext | None = None, **opts)`

Optional per-destination state factory:
- `create_destination_context(destination) -> TapDestinationContext | None`

## 3.2 Producer/Destination Granularity
A producer relationship is per `(tap, home_context)` but output ownership is per `Grip`.

Required semantics:
- A tap can provide many grips.
- Different grips may resolve to different taps at the same consumer context.
- Output overlap between taps is allowed.
- Ownership of overlapping grips is tracked per grip, not per whole tap.

## 3.3 Destination Management
Each producer keeps per-destination records.
Each destination stores:
- destination context node
- visible grips for that destination
- optional destination-specific Tap context
- destination parameter subscriptions and cached values

Required lifecycle behavior:
- first connection of a destination creates destination record and subscribes destination params
- adding a grip to an existing destination triggers initial produce for that destination
- removing last grip from destination triggers detach cleanup for that destination
- destination param changes call `produce_on_dest_params(dest_context, grip)` when implemented

## 3.4 Resolver Precedence and Selection
Static resolver precedence (no matcher):
- nearest provider in context DAG
- parent priority order respected
- non-root ancestors preferred before root when traversing equal breadth levels
- provider choice is per-grip

Same-context overlap rule in static mode:
- latest producer assignment for a specific grip in that context wins for that grip

Matcher-driven overlap rule (future integration):
- resolver applies attribution deltas per grip
- winner chosen by query evaluator score, then binding-id tie-break
- grips can transfer between taps without tearing unrelated grip ownership

## 3.5 Publish Semantics
Publishing must only affect destinations where the tap is currently resolved for that grip.

Implications:
- if a closer provider overshadows an ancestor for grip `G`, ancestor publish on `G` must not update that destination
- multi-grip publish should update only grips visible in each destination

## 4. FunctionTap Spec
FunctionTap is synchronous and deterministic.

Primary use cases:
- value conversion (for example km -> miles)
- projection from larger objects (for example selected row fields)
- formatting derived values

## 4.1 Inputs
FunctionTap may read:
- home params (from provider/home context lineage)
- destination params (from destination context lineage)
- optional local state (phase 2b)

## 4.2 Compute Contract (v1)
`compute(dest_context) -> dict[Grip[Any], Any]`

v1 required behavior:
- compute uses current home/destination param snapshots
- produce may target one destination (`dest_context=...`) or all active destinations
- destination parameter change recomputes only affected destination
- home parameter change recomputes all active destinations

Phase 2b (implemented):
- optional state grips and handle grip parity with `grip-core`
- `compute(args)` receives `FunctionTapComputeArgs`
- compatibility shim: legacy `compute(ctx)` style still works
- `handle_grip` publishes a handle supporting `get_state(...)` and `set_state(...)`

## 5. AsyncTap Spec
AsyncTap is destination-aware and request-key aware.
A request key identifies in-flight/cached work for a destination parameter set.

Fetcher contract (implemented):
- `fetcher(params: AsyncTapParams) -> Awaitable[dict[Grip[Any], Any]]`
- `params.destination_params` provides resolved destination parameter values
- `params.home_params` provides resolved home parameter values
- fetcher does not receive context objects directly

## 5.1 AsyncTap Options (all optional)
- `request_key_of(params: AsyncTapParams) -> str | None`
- `latest_only: bool = True`
- `deadline_ms: int | None = None`
- `cache_ttl_ms: int = 0`
- `refresh_before_expiry_ms: int = 0`
- `cleanup_delay_ms: int = 1000`
- `keep_stale_data_on_transition: bool = False`
- `retry: RetryConfig | None = None` (implemented)
- `state_grip: Grip[AsyncRequestState] | None = None` (implemented)
- `controller_grip: Grip[AsyncTapController] | None = None` (implemented)

## 5.2 Concurrency Model
Must support multiple concurrent request keys.

Required behavior:
- requests are tracked per request key
- destinations sharing same key can share request work/state where safe
- destination detach does not immediately nuke shared state; cleanup delayed by `cleanup_delay_ms`
- when no destinations remain for key after delay, key state is cleaned

## 5.3 Cancellation / In-flight Retention
- if `latest_only=True`, a destination joining an existing in-flight request for the same key reuses it
- if `latest_only=False`, a new request for an already in-flight key cancels the prior in-flight key task
- detached keys retain in-flight/cache/retry state until `cleanup_delay_ms` elapses
- stale completion is ignored when destination key mapping has changed

## 5.4 Cache Semantics
- cache key = request key
- TTL controlled by `cache_ttl_ms`
- expired entries are not used as fresh
- optional stale-while-revalidate behavior when refreshing cached data

## 5.5 State Semantics (phase 3b)
`AsyncRequestState` tracks per-destination view of async lifecycle:
- idle
- loading
- success
- error
- stale-while-revalidate (reserved for follow-on refinement)
- stale-with-error (reserved for follow-on refinement)

State updates should be immutable snapshots so watchers can detect transitions cleanly.
Controller API:
- `retry(force_refetch: bool = False)`
- `refresh(force_refetch: bool = False)`
- `reset()`
- `cancel_retry()`
- `abort()`

## 6. Query Matcher and Partial Overrides
Implemented core matcher delta plumbing (`QueryEvaluator` + resolver `apply_producer_delta`):
- per-grip attribution deltas (`added`, `removed`) at a context
- ability to transfer a subset of grips from one tap to another
- preserving unaffected grips on existing taps
- deterministic conflict resolution via evaluator score/tie-break

Full query/matcher runtime orchestration remains a follow-on phase.

## 7. Test Specification (TDD)
All implementation work follows red/green/refactor.

## 7.1 Base Tap / Resolver / Graph Tests
Port and adapt from `grip-core`:
- destination lifecycle callbacks (added/removed/detach)
- overshadow safety on publish
- partial per-grip override at same and different contexts
- producer removal and cascading relink
- dynamic parent changes and re-resolution

## 7.2 FunctionTap Tests
- destination-param aware compute
- home-param fanout recompute
- single-destination recompute on destination param change
- optional state handle behavior (phase 2b)

## 7.3 AsyncTap Tests
Phase 3a:
- latest-only with out-of-order completion
- per-key concurrent requests
- cancellation/ignore stale result correctness
- cache TTL behavior
- cleanup delay behavior for dropped destinations

Phase 3b:
- async request state transitions
- listener tracking semantics
- controller actions: retry/refresh/reset/cancel/abort
- retry backoff behavior

## 7.4 Matcher Integration Tests
- attribution transfer of subset grips between taps
- score + binding-id tie-break determinism
- no regression for unaffected grips during transfer

## 8. Implementation Plan
## Phase 0: Freeze and Spec Lock
- finalize this tap spec and open issues list
- no further tap feature coding until test plan is agreed

Exit criteria:
- spec accepted

## Phase 1: Test Harness and Baseline Parity Skeleton
- create Python test modules mirroring `grip-core` categories:
  - `test_base_tap_behavior.py`
  - `test_function_tap_parity.py`
  - `test_async_tap_parity.py`
  - `test_tap_matcher_integration.py`
- mark not-yet-implemented tests with explicit xfail tags

Exit criteria:
- baseline failing tests clearly document missing features

## Phase 2: Base Tap + FunctionTap Core
- implement destination param subscriptions in BaseTap destination records
- implement per-grip overlap ownership in producer graph paths
- implement FunctionTap destination-aware recompute behavior

Exit criteria:
- Phase 2 test set green

## Phase 2b: FunctionTap State/Handle Parity
- add optional state grips and handle grip behavior

Exit criteria:
- state/handle tests green (completed)

## Phase 3a: AsyncTap Core
- implement request-key concurrency model
- add latest-only stale result protection
- add cancellation and cleanup-delay behavior
- add cache with TTL

Exit criteria:
- async core tests green

## Phase 3b: Async State + Control Plane
- add `AsyncRequestState` model and helper semantics
- add controller grip and retry/refresh/reset APIs
- add retry policy behavior

Exit criteria:
- async advanced/state tests green (completed)

## Phase 4: Matcher Delta Integration
- implement matcher/evaluator integration path in `grip-py`
- ensure partial-grip transfer semantics match expected parity

Exit criteria:
- matcher delta + resolver integration tests green (completed for core attribution path)

## Phase 5: Hardening
- run full suite and targeted stress tests
- document performance characteristics and defaults

Exit criteria:
- all tests green (completed)
- docs updated with final API examples (completed)
- async perf smoke harness in `grip-py/tests/core/test_async_tap_perf.py` (completed)

## 9. Defaults Chosen in This Spec
- static same-context overlap winner: latest producer assignment per grip
- async `latest_only` default: enabled
- async cache default: disabled (`cache_ttl_ms=0`)
- async cleanup delay default: 1000 ms
- stale-on-transition default: disabled (`keep_stale_data_on_transition=False`)

## 10. Out of Scope for This Document
- Drip-level semantics (already captured in `docs/GRIP_PY_DRIP_PROPOSAL.md`)
- Glial runtime/session architecture (covered by Glial docs)
