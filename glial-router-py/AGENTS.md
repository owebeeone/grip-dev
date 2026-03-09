# AGENTS

## Scope
This file defines repository-specific coding instructions for `glial-router-py`.

## Design Rules
- Prefer `@dataclass` for classes that primarily hold state.
- Keep FastAPI route handlers thin; move coordination logic into separate classes.
- Keep type annotations complete and precise so IDE inference remains strong.

## Development Process (TDD)
Use a strict red/green/refactor workflow for all behavior changes.

1. Red: Add or update tests first to express the expected behavior, then run the smallest relevant test target and confirm it fails.
2. Green: Implement the minimal code change required to make the failing test pass.
3. Refactor: Improve structure and readability while preserving behavior.
4. Verify targeted scope: Re-run the focused test subset.
5. Verify full regression: Run the full test suite before finalizing.

## Test Commands
- Focused tests: `uv run --with pytest --with pytest-cov pytest <test-path> -q`
- Full suite: `uv run --with pytest --with pytest-cov pytest -q`
