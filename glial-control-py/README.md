# glial-control-py

Command-driven Python control client for Glial shared sessions.

Current scope:

- list remote shared sessions
- load a shared session
- list shared contexts
- list shared taps
- request or release primary lease for a tap
- set a shared drip value by canonical `path` and `grip_id`

This package is intentionally application-agnostic. It operates on canonical IDs and JSON-compatible values rather than application-specific typed grips.
