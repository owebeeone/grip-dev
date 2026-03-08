# GRIPPY Specification
Date: 2026-03-07  
Status: Proposed  
Target package: `grippy` (new package, clean break from current `grip` WIP)

## 1. Decision Summary
We will abandon the current mixed/incomplete `grip` WIP implementation and build a new Python package (`grippy`) around the simpler `grip-core` TypeScript runtime model.

Key constraints:
- Use a single key registration API on the registry: `registry.add(...)`.
- Align key-definition flow with the TypeScript core model (`defineGrip`/`GripOf` style).
- Do not provide `ref` or `lazy` namespaces in the new API.
- Do not expose key scopes in v1 (key uniqueness is by name only).
- Implement only `grip-core` level runtime (no React/compiler layer).
- Add strong type annotations so IDEs/static checkers can infer key and drip value types directly.

## 2. Scope
### In scope (v1)
- Typed `Grip[T]` and key registry.
- `Grok` runtime core.
- Context DAG (`GripContext`) with parent precedence and cycle prevention.
- `Drip[T]` subscription/value model.
- Tap interfaces and base classes.
- Basic taps:
  - Atom value tap
  - Function tap
- Minimal graph inspection/debug API.

### Out of scope (v1)
- React bindings/compiler-specific behavior (`grip-react` layer).
- UI graph visualizer components.
- Legacy `TapScope` fluent builder as primary API.
- Porting every existing WIP module (`grip_stream`, `grip_dgraph`, old graph internals, etc.).

## 3. Public API (Proposed)
## 3.1 Keys and Registry
```python
from typing import Generic, TypeVar, Protocol, Any

T = TypeVar("T")

class Grip(Generic[T]):
    name: str
    key: str          # same as name in v1
    data_type: type[T] | None
    default: T | None
```

```python
from typing import Any, Literal, overload

class GripRegistry:
    @overload
    def add(self, name: str, default: T) -> Grip[T]: ...
    @overload
    def add(self, name: str, *, value_type: type[T]) -> Grip[T | None]: ...
    @overload
    def add(self, name: str, default: None, *, value_type: type[T], nullable: Literal[True] = True) -> Grip[T | None]: ...
    @overload
    def add(self, name: str, default: Any, *, value_type: type[T], nullable: Literal[False] = False) -> Grip[T]: ...
    @overload
    def add(self, name: str, default: Any, *, value_type: type[T], nullable: Literal[True]) -> Grip[T | None]: ...
    def add(
        self,
        name: str,
        default: Any = ...,
        *,
        value_type: type[Any] | None = None,
        nullable: bool = False,
    ) -> Grip[Any]: ...
```

Usage pattern:
- `USER_NAME = registry.add("UserName", "")`  # inferred `Grip[str]`
- `USER_AGE = registry.add("UserAge", 0)`  # inferred `Grip[int]`
- `TEMP_C = registry.add("TempCelsius", value_type=float)`  # inferred `Grip[float|None]`
- `ZAR = registry.add("Zar", 5, value_type=float)`  # inferred `Grip[float]`, stored default is `5.0`
- `BAR = registry.add("Bar", 5, value_type=float, nullable=True)`  # inferred `Grip[float|None]`

Error behavior:
- Duplicate defined key raises `DuplicateGrip`.
- Re-adding an existing `name` raises `DuplicateGrip`.
- `value_type` conversion failure raises `TypeError`/`ValueError`.
- `add(name, None)` without `value_type` raises `TypeError`.

Add semantics:
- `add(name, default)` infers `Grip[T]` from `default`.
- `add(name, *, value_type=T)` returns `Grip[T|None]` with `default=None`.
- `add(name, None, value_type=T)` returns `Grip[T|None]`.
- `add(name, default, value_type=T, nullable=False)` with non-`None` default converts via `T(default)`, stores converted default, and returns `Grip[T]`.
- `add(name, default, value_type=T, nullable=True)` with non-`None` default converts via `T(default)`, stores converted default, and returns `Grip[T|None]`.
- `nullable` should be passed as a literal (`True`/`False`) for precise IDE inference.

## 3.2 Type-Safe Key Schema (New Requirement)
Dynamic attribute access alone cannot guarantee strong IDE inference for named keys.  
So `grippy` will support a typed schema mode as the recommended production path.

```python
from grippy import GripRegistry, GripSchema, grip_key, Grip

class AppKeys(GripSchema):
    UserId: Grip[int] = grip_key(int)
    UserName: Grip[str] = grip_key(str, default="")
    IsAdmin: Grip[bool] = grip_key(bool, default=False)

registry: GripRegistry[AppKeys] = GripRegistry.from_schema(AppKeys)
keys: AppKeys = registry.keys

uid_key = keys.UserId          # Grip[int]
name_key = keys.UserName       # Grip[str]
```

Notes:
- Keep `registry.add(...)` as the only registry key-definition entry point.
- Promote schema-based access (`registry.keys`) when direct type inference is required.

## 3.3 Runtime Core
```python
class Grok:
    root_context: GripContext
    main_home_context: GripContext
    main_presentation_context: GripContext

    def create_context(self, parent: GripContext | None = None, priority: int = 0, id: str | None = None) -> GripContext: ...
    def unregister_tap(self, tap: Tap) -> None: ...
    def query(self, grip: Grip[T], consumer_ctx: GripContextLike) -> Drip[T]: ...
    def flush(self) -> None: ...
    def get_graph(self) -> GraphSnapshot: ...
```

```python
class GripContext:
    id: str
    def add_parent(self, parent: GripContextLike, priority: int = 0) -> "GripContext": ...
    def unlink_parent(self, parent: GripContext) -> "GripContext": ...
    def create_child(self, *, priority: int = 0) -> "GripContext": ...
    def register_tap(self, tap: Tap | TapFactory) -> None: ...
    def unregister_tap(self, tap: Tap) -> None: ...
    def get_or_create_consumer(self, grip: Grip[T]) -> Drip[T]: ...
```

```python
class Drip(Generic[T]):
    def get(self) -> T | None: ...
    def next(self, value: T | None) -> None: ...
    def subscribe(self, fn: Callable[[T | None], None]) -> Callable[[], None]: ...
    def subscribe_priority(self, fn: Callable[[T | None], None]) -> Callable[[], None]: ...
    def has_subscribers(self) -> bool: ...
```

## 3.4 Tap API
```python
class Tap(Protocol):
    provides: tuple[Grip[Any], ...]
    destination_param_keys: tuple[Grip[Any], ...] | None
    home_param_keys: tuple[Grip[Any], ...] | None
    def on_attach(self, home: GripContextLike) -> None: ...
    def on_detach(self) -> None: ...
    def on_connect(self, dest: GripContext, grip: Grip[Any]) -> None: ...
    def on_disconnect(self, dest: GripContext, grip: Grip[Any]) -> None: ...
    def produce(self, *, dest_context: GripContext | None = None) -> None: ...
```

Base + factories to include:
- `BaseTap`
- `BaseTapNoParams`
- `AtomValueTap`, `create_atom_value_tap`
- `FunctionTap`, `create_function_tap`

Async taps:
- Included only after core stability (`BaseAsyncTap`, `create_async_value_tap`) as phase-2 work.

## 4. Compatibility and API Mapping
| Current `grip` WIP | Action | `grippy` replacement |
|---|---|---|
| `GripRegistryImpl` in `grip_core/grip_key` | Replace | `grippy.GripRegistry` |
| Split main/pro key identity model in old design | Simplify | single typed `Grip[T]` |
| `add/ref/lazy` key ergonomics | Simplify | only `registry.add(...)` |
| `TapScope` fluent builder | De-emphasize | explicit tap objects/factories |
| Legacy graph/dgraph modules | Drop from v1 | runtime graph internal to `Grok` |
| React/compiler coupling | Not ported | out of scope for Python |

## 5. Transition Plan
### Phase 0: Freeze and Baseline
- Freeze feature work in old `grip` package.
- Keep a concise baseline test list for required carryover behavior.
- Treat old `add/ref/lazy` tests as historical reference, not target API.

### Phase 1: New Package Scaffold
- Create new package layout (`src/grippy`).
- Add packaging and tooling (`pyproject.toml`, pytest, pyright/mypy config).
- Add CI checks for tests + static typing.

### Phase 2: Key Layer First
- Implement `Grip[T]`, `GripRegistry`, and errors.
- Implement `registry.add(...)` behavior parity with the TypeScript-like key definition flow.
- Implement typed schema mode (`GripSchema` + `from_schema`) for IDE inference.
- Add focused tests for both dynamic and schema-typed access.

### Phase 3: Core Runtime
- Implement `Drip`, `GripContext`, context DAG parenting, and cycle checks.
- Implement `Grok.query`, tap registration/unregistration, and resolution to nearest provider.
- Add engine behavior tests modeled after `grip-core` engine tests.

### Phase 4: Basic Tap Set
- Implement atom taps and function taps.
- Add end-to-end tests for:
  - default fallback
  - parent vs child provider precedence
  - dynamic updates flowing through drips

### Phase 5: Optional Async Layer
- Port async taps only after Phase 4 is stable.
- Keep API similar to `grip-core`, but in Python async idioms (`asyncio`).
- Mark async APIs as beta initially.

### Phase 6: Migration Adapter + Cutover
- Provide a thin compatibility adapter for the old import surface where practical.
- Emit deprecation warnings from old modules.
- Migrate new project code to `grippy` imports.
- Stop adding features to old `grip`; keep only minimal compatibility fixes.

## 6. Typing and IDE Guarantees
Required guarantees for `grippy`:
- `Grip[T]` is generic and preserved through query/drip chain:
  - `query(Grip[int], ctx) -> Drip[int]`
- Taps preserve key/value typing at interfaces.
- `registry.keys` schema mode provides concrete attribute typing for IDE autocomplete and inference.
- Static type CI must include at least one strict checker (`pyright --strict` recommended).

## 7. Acceptance Criteria
- `GripRegistry` exposes a single public key-definition API: `add(...)`.
- V1 registry API has no user-facing scope argument.
- `add(name, default, value_type=T)` converts default to `T` when possible.
- IDE/type checker inference from `registry.add(...)` produces `Grip[T]`/`Grip[T|None]` without requiring explicit variable annotations in normal usage.
- `add(name, ..., value_type=T, nullable=True)` infers `Grip[T|None]` via overload resolution.
- New typed schema path gives direct IDE type inference for declared keys.
- Core runtime supports registry/context/tap/drip lifecycle without React/compiler dependencies.
- New project can depend only on `grippy` (not old `grip`) for v1 functionality.
