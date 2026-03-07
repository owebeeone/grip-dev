# GRIP_PY Drip Proposal
Date: 2026-03-07
Status: Proposed
Scope: `Drip` API and Python `useGrip`-equivalent consumer API

## 1. Decision Summary
`grippy` should define `Drip` semantics first, then pick streaming internals.

`grip_stream.py` in the legacy `grip` repo demonstrates useful async batching ideas, but it should not be adopted as the public Drip API as-is.

Primary direction:
- Align with `grip-core` Drip contract (`get`, `next`, subscribe variants, first/zero subscriber lifecycle).
- Provide a Python consumer API equivalent to React `useGrip` without requiring React.
- Keep transport internals replaceable.

## 2. Why Start With `useGrip` Semantics
In TypeScript React:
- `useGrip(grip, ctx?)` effectively does `drip = grok.query(grip, ctx)`
- reads `drip.get()`
- subscribes through `drip.subscribe(...)`

So the stable contract is Drip, not UI framework integration.

For Python, we should first define:
- snapshot read API (value now)
- subscription API (push updates)
- async streaming API (`async for`)

Then implement internals that satisfy these guarantees.

## 3. Proposed Python API

### 3.1 Core Drip API
```python
from collections.abc import Callable
from typing import Generic, Literal, TypeVar

T = TypeVar("T")
Unsubscribe = Callable[[], None]
ErrorPolicy = Literal["log", "raise", "collect"]
ElidePolicy = Literal["ts", "equality", "none"]

class Drip(Generic[T]):
    def __init__(
        self,
        initial: T | None = None,
        *,
        error_policy: ErrorPolicy = "log",
        elide_policy: ElidePolicy = "ts",
        callback_error_handler: Callable[[Exception], None] | None = None,
    ) -> None: ...

    def get(self) -> T | None: ...
    def next(self, value: T | None) -> None: ...
    def next_threadsafe(self, value: T | None) -> None: ...

    def subscribe(self, fn: Callable[[T | None], None]) -> Unsubscribe: ...
    def subscribe_priority(self, fn: Callable[[T | None], None]) -> Unsubscribe: ...

    def has_subscribers(self) -> bool: ...
    def add_on_first_subscriber(self, fn: Callable[[], None]) -> None: ...
    def add_on_zero_subscribers(self, fn: Callable[[], None]) -> None: ...
    def unsubscribe_all(self) -> None: ...
    def get_callback_errors(self) -> tuple[Exception, ...]: ...
```

Behavioral rules:
- `subscribe` and `subscribe_priority` emit the current value immediately on subscribe.
- `next(v)` elides unchanged values by default using TS-like policy (`elide_policy="ts"`).
- `elide_policy` is configurable (`"ts"` default, `"equality"`, `"none"`).
- `subscribe_priority` callbacks run synchronously in `next`.
- `subscribe` callbacks are queued/coalesced on the event loop.
- first-subscriber callbacks fire on transition `0 -> 1`.
- zero-subscriber callbacks fire on transition `1 -> 0` (deferred one loop tick to tolerate transient resubscribe).
- callback exception handling is configurable; default is `error_policy="log"` (log-and-continue).
- `error_policy` semantics:
  - `"log"`: report via handler/logger and continue.
  - `"raise"`: propagate exception to caller.
  - `"collect"`: store exception for later inspection via `get_callback_errors()` and continue.
- `elide_policy="ts"` semantics:
  - scalar values (`None`, `bool`, `int`, `float`, `str`, `bytes`) compare by value (`==`).
  - non-scalars compare by identity (`is`), approximating TS reference semantics.
- loop ownership is lazy-bound on first async operation/use; no running loop required at construction.
- `next_threadsafe` is included in v1, using `loop.call_soon_threadsafe`.

### 3.2 Python `useGrip`-Equivalent API
```python
from typing import AsyncIterator, Literal, TypeVar

T = TypeVar("T")


def use_grip(grok: "Grok", grip: "Grip[T]", ctx: "GripContextLike | None" = None) -> T | None:
    """Snapshot read equivalent of React useGrip."""


def watch_drip(
    drip: "Drip[T]",
    *,
    emit_initial: bool = True,
    priority: bool = False,
    queue_size: int = 1,
    overflow: Literal["drop_oldest", "drop_newest"] = "drop_oldest",
) -> AsyncIterator[T | None]:
    """Async stream of drip values for asyncio consumers."""
```

Notes:
- `watch_drip` is the v1 async integration helper.
- `use_grip` remains the target shape for later Grok integration.
- `queue_size=1` gives latest-value coalescing semantics by default (similar to UI rendering needs).
- `overflow` defaults to `drop_oldest`.

## 4. Assessment Of Legacy `grip_stream.py`

### 4.1 What Is Useful
- async-safe send path (`await stream.send(...)`)
- batching and coalescing (`latest_only`)
- duplicate suppression (`skip_duplicates`)
- explicit activation/deactivation lifecycle

### 4.2 Gaps Versus Drip Requirements
- No `get()/next()` value-holder semantics at Drip level.
- No multiple-subscriber API on a value stream.
- No first/zero-subscriber lifecycle hooks.
- Stream object is tied to one processor callback, not many subscribers.
- API shape centers on message routing, not `(context, grip) -> shared drip` identity.

### 4.3 Current Reliability Concerns (Observed)
Using:
```bash
cd /Users/owebeeone/limbo/grippy/grip
PYTHONPATH=src uv run --with pytest --with pytest-asyncio --with datatrees pytest -q tests/test_grip_stream.py
```
Observed: `3 failed, 6 passed`.

Notable failures:
- `test_single_sender_single_stream_sync_processor`: awaits a sync function (`TypeError`).
- `test_stream_latest_only`: expected behavior does not match implementation (`[3, 4]` observed vs `[4]` expected).
- `test_stream_scope_drain`: timeout with pending count not fully drained.

Conclusion: this module can inform internals, but should not be copied as the public Drip contract.

## 5. Pre-existing Systems Review

### 5.1 Local Existing Candidate: `dripfeeder.py`
File:
- `/Users/owebeeone/limbo/grippy/grip/src/grip/dripfeeder.py`

Strengths:
- Has value snapshot semantics (`snapshot()`), push updates, async wait (`on_change()`), and async iteration.
- Uses weak references for feeder-to-drip tracking.
- Existing tests currently pass:
  - `PYTHONPATH=src uv run --with pytest --with pytest-asyncio --with datatrees pytest -q tests/test_dripfeeder.py`
  - observed: `4 passed`.

Gaps for `grip-core`-style Drip:
- No callback subscription API matching `subscribe` / `subscribe_priority`.
- No first-subscriber / zero-subscriber lifecycle callbacks.
- Different semantics (`snapshot/on_change`) than target `get/next/subscribe`.
- Depends on `datatrees`; not ideal for a minimal core runtime.

Verdict:
- Good reference implementation for async change waiting.
- Not a direct drop-in for target Drip API.

### 5.2 Ecosystem Candidates
- Python stdlib `asyncio` primitives (`Event`, `Queue`, `call_soon`): suitable building blocks, no extra dependency.
- `anyio` memory object streams: robust async streams, but each sent item is consumed by a single recipient (not broadcast fan-out), which conflicts with Drip subscriber semantics.
- `reactivex` (`BehaviorSubject`): close to value-stream behavior and multicasting, but introduces a larger reactive abstraction and scheduler model mismatch with desired lightweight core.
- `janus`: useful for thread <-> asyncio queue bridging only; not a Drip abstraction.

Verdict:
- Best fit for v1 is a small custom Drip built on stdlib `asyncio`, borrowing ideas from local `dripfeeder.py` and TS `Drip`.
- Keep third-party adapters optional (future).

## 6. Recommended Architecture

### 6.1 Public Surface
- `Drip[T]` in `grip_py.core.drip`.
- `watch_drip(...)` in `grip_py.core.use_grip` for v1 async consumption.
- `use_grip(...)`/`watch_grip(...)` remain deferred wrappers pending Grok integration.
- `Grok.query(grip, ctx) -> Drip[T]` remains the canonical constructor/access path.

### 6.2 Internal Scheduling Model
- Default scheduler: event-loop microtask style (`loop.call_soon`) for regular subscribers.
- Priority subscribers run inline in `next`.
- No hard dependency on `GripStream` internals.
- Optional later internal adapter to queue fan-out if profiling requires it.

### 6.3 Thread Interaction
- `next_threadsafe` is included in v1 via `loop.call_soon_threadsafe`.
- Drip loop reference is lazy-bound on first async usage and then reused.

## 7. File Structure Proposal
```text
grip-py/src/grip_py/core/
  drip.py
  use_grip.py
```

Tests:
```text
grip-py/tests/core/
  test_drip.py
  test_watch_drip.py
```

## 8. Test Plan
`test_drip.py`:
- `get` returns initial/default value
- `next` notifies only on value change
- `subscribe` and `subscribe_priority` emit current value immediately
- `subscribe_priority` is synchronous
- `subscribe` is deferred/coalesced
- `add_on_first_subscriber` fires once on first subscribe
- `add_on_zero_subscribers` fires on last unsubscribe (deferred)
- `unsubscribe_all` clears subscribers and runs zero callbacks
- `error_policy="log"` logs and continues after callback exceptions
- `error_policy="raise"` propagates callback exceptions
- `next_threadsafe` updates values from non-loop thread

`test_watch_drip.py`:
- `watch_drip(..., emit_initial=True)` yields initial value first
- updates arrive in order for priority path
- coalescing behavior for default queue_size=1
- overflow policy `drop_oldest` behavior is verified

## 9. Transition Plan (No Grok Dependency Yet)
1. Implement `Drip[T]` + tests (no `grip_stream` dependency).
2. Implement `watch_drip(drip, ...)` helper APIs against Drip directly.
3. Keep `use_grip(grok, grip, ctx)` as a specified target API, but defer concrete Grok integration.
4. Revisit whether any `grip_stream` internals are worth adapting for high-throughput cases.

## 10. Resolved Defaults
- Helper name is `watch_drip` for v1.
- Subscriptions emit current value immediately.
- Callback errors are configurable; default is log-and-continue.
- Value-elision policy is configurable; default is TS-like (`elide_policy="ts"`).
- Overflow policy default is `drop_oldest`.
- Thread-safe updates are included in v1 (`next_threadsafe`).
- Event loop binding is lazy on first use.
