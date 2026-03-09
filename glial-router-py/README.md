# glial-router-py

FastAPI-based Glial coordination service for local testing and early integration.

This package currently provides:

- attach or seed session endpoint
- snapshot fetch endpoint
- change submit endpoint with authoritative session clocks
- replay endpoint for missed changes

The implementation is intentionally in-memory for the first integration phase.
