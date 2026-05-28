# AGENTS

## Scope
This file defines workspace-level instructions for `grip-pyrolyze-dev` (parent checkout and its submodules).

## Paths in version control
- Do not store absolute filesystem paths (for example `/Users/...` or `C:\...`) in any committed file—docs, configs, examples, scripts, or tests.
- Prefer paths relative to the **root of the git repository that owns the file**. When this checkout nests submodules, truncate to that submodule root (e.g. `pyrolyze/examples/foo.py`), not a path through the parent workspace or a machine-specific prefix.

## Test coverage shape
- Prefer canonical fixture, golden, snapshot, or integration-style coverage for successful end-to-end behavior when a project already has that harness.
- Keep bespoke unit tests focused on narrow mechanics, recognition/parsing checks, edge-case failures, and diagnostics that the canonical harness cannot express cleanly.
- Avoid duplicating the same success-path assertions in both bespoke tests and canonical output tests; duplicated coverage increases maintenance cost without improving confidence.
