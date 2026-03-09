# glial-local-ts

Local-first Glial session model and persistence interfaces for TypeScript runtimes.

This package owns:

- canonical session and snapshot types
- normalized persisted change records
- sync checkpoints
- in-memory persistence reference implementations

It intentionally does not depend on Grip runtime object classes or Glial transport code.
