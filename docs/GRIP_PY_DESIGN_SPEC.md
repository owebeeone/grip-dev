# GRIP_PY Design Spec
Date: 2026-03-07  
Status: Draft  
Scope: `grip-py` key model and key registry only

Related proposal:
- `docs/GRIP_PY_DRIP_PROPOSAL.md` defines the proposed Drip/use_grip API for the next runtime phase.

## 1. Purpose
This document defines the initial `grip-py` package structure and API for:
- `Grip[T]`
- `GripRegistry` with a single public key-definition method: `.add(...)`

This follows the direction in `docs/GRIPPY_SPEC.md` and mirrors `grip-core` where it makes sense.

## 2. Design Constraints
- Registry is for Grip keys only.
- Registry does not store taps, tap definitions, or tap scopes.
- Public key-definition API is only `registry.add(...)`.
- No user-facing key scope in v1.
- No `ref` namespace.
- No `lazy` namespace.

## 3. Alignment With `grip-core`
Reference: `grip-core/src/core/grip.ts`

`grip-core` concepts and `grip-py` equivalents:
- `Grip<T>` -> `Grip[T]`
- `GripRegistry.defineGrip(...)` -> `GripRegistry.add(...)`
- `scope + name -> key` -> simplified to `name` only in v1
- duplicate key registration throws -> same behavior

Not mirrored for now:
- `findOrDefineGrip(...)` is not in v1 registry API.

## 4. Planned File Structure
Target structure for the registry/key slice:

```text
grip-py/
  pyproject.toml
  README.md
  src/
    grip_py/
      __init__.py
      core/
        __init__.py
        errors.py
        grip.py
  tests/
    core/
      test_grip.py
      test_grip_registry.py
```

Notes:
- `src/grip_py/core/grip.py` is the `grip-core/src/core/grip.ts` analog.
- `src/grip_py/__init__.py` should re-export stable public symbols.

## 5. Public API (Registry + Keys)
```python
from typing import Any, Generic, Literal, TypeVar, overload

T = TypeVar("T")

class Grip(Generic[T]):
    name: str
    key: str            # same as name in v1
    default: T | None
    data_type: type[T] | None

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

Usage:
```python
registry = GripRegistry()
USER_NAME = registry.add("UserName", "")  # inferred Grip[str]
USER_AGE = registry.add("UserAge", 0)  # inferred Grip[int]
TEMP_C = registry.add("TempCelsius", value_type=float)  # inferred Grip[float|None]
ZAR = registry.add("Zar", 5, value_type=float)  # inferred Grip[float], converted default: 5.0
BAR = registry.add("Bar", 5, value_type=float, nullable=True)  # inferred Grip[float|None]
```

## 6. Behavior Rules
### 6.1 Key Construction
- `key` is the same value as `name` in v1.
- If `value_type` is provided, `data_type = value_type`.
- Else, `data_type = type(default)` for `add(name, default)`.
- `add(name, None)` without `value_type` is invalid.

### 6.2 `add(...)` Overload Semantics
- `add(name, default)`:
  - infer `T` from `default`
  - return `Grip[T]`
- `add(name, *, value_type=T)`:
  - return `Grip[T|None]` with `default=None`
- `add(name, None, value_type=T)`:
  - return `Grip[T|None]`
- `add(name, default, value_type=T, nullable=False)` with non-`None` default:
  - attempt conversion via `T(default)`
  - store converted default on the grip
  - return `Grip[T]`
- `add(name, default, value_type=T, nullable=True)` with non-`None` default:
  - attempt conversion via `T(default)`
  - store converted default on the grip
  - return `Grip[T|None]`
- For precise inference, `nullable` should be passed as a literal (`True`/`False`).

### 6.3 Duplicate Handling
- Adding a key when `name` already exists raises `DuplicateGrip`.
- This applies even if the same default/type is provided again.

### 6.4 Equality/Identity
- `Grip` instances are identity-based objects (no value-based equality semantics).
- Registry uniqueness is enforced by `name`.

## 7. Internal Model
Registry internal state:
- `_keys_by_name: dict[str, Grip[Any]]`

No tap-related fields in registry:
- no `_tap_definitions`
- no `_tapscopes`
- no runtime graph references

## 8. Public Exports
From `grip_py.__init__`:
- `Grip`
- `GripRegistry`
- `DuplicateGrip`

From `grip_py.core.__init__`:
- same symbols for explicit core imports.

## 9. Test Plan (Registry Slice)
`tests/core/test_grip.py`:
- key fields (`name`, `key`, `default`, `data_type`)
- key identity semantics

`tests/core/test_grip_registry.py`:
- add with default (type inferred)
- add with `value_type` and omitted default infers `Grip[T|None]`
- add with `default=None, value_type=T` infers `Grip[T|None]`
- add with `value_type` conversion (`5 -> 5.0` for `float`)
- add with `value_type` conversion and `nullable=True` infers `Grip[T|None]`
- add with failed conversion raises type/conversion error
- add with `default=None` and no `value_type` raises `TypeError`
- add duplicate raises `DuplicateGrip`

## 10. Out of Scope (This Spec)
- Grok runtime
- contexts, drips, taps
- query/matcher systems
- async taps/request state
- typed schema mode details (covered by broader `GRIPPY_SPEC.md`)
