# glial-control-py instructions

- Follow the same Python package structure and testing discipline as `grip-py`.
- Prefer small command functions with direct integration tests against the local FastAPI router.
- Keep the client application-agnostic: operate on canonical IDs and JSON-compatible values.
