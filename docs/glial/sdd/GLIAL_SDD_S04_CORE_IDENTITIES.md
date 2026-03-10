# Glial SDD Section 04: Core Identities

## Browser Session Identity

`browser_session_id` is a browser-local durable selector that survives page reload.

Rules:

- `browser_session_id` is local to one browser storage domain
- it is not used for Glial routing
- it points to the currently loaded logical Glial session and browser storage policy
- reloading the page should preserve the same `browser_session_id`

The browser session record maps:

- `browser_session_id -> glial_session_id`
- storage mode such as local, remote, or both
- whether the current browser instance should attach to Glial routing

## Glial Session Identity

`glial_session_id` is the top-level logical session identity for persistence, backup, routing, and sharing.

Rules:

- a local-only session may exist with one runtime replica and no Glial attachment
- all cooperating replicas in a shared session use the same `glial_session_id`
- local backup and remote backup both key their logical session data by `glial_session_id`
- when attached to Glial, one session is owned by exactly one shard at a time
- all authoritative clocks, leases, snapshots, and replay streams in Glial are scoped by `glial_session_id`

## Replica Identity

`replica_id` identifies one concrete participant inside a Glial session.

Rules:

- every connected participant has its own `replica_id`
- `replica_id` is stable for the lifetime of that participant’s Glial connection
- all authoritative clocks include `replica_id` in their comparison tuple

## Context Identity

Contexts use canonical string paths.

Rules:

- root path is `/`
- path separator is `/`
- path segments are stable structural names
- segment names must not contain `/`
- sibling names must be unique under the same parent

Examples:

- `/`
- `/weather-column-0`
- `/table/row-slot-3`

Context identity is structural. Current bound data is represented separately via drips or binding-designated drips.

## Grip Identity

Grip IDs are canonical runtime-neutral strings.

For JavaScript/TypeScript and Python, the canonical form is:

`<scope>:<name>`

Examples:

- `app:theme`
- `weather:temperature`
- `table:row-id`

## Tap Identity

Tap identity is derived from graph structure rather than runtime object identity.

V1 basis:

- home context path
- tap type
- lowest lexical provided grip

Recommended canonical form:

`<home_context_path>@<tap_type>:<lowest_provided_grip>`

Examples:

- `/weather-column-0@AsyncWeatherTap:weather:temperature`
- `/table/row-slot-1@FunctionTap:table:row-data`

Associated metadata must also carry:

- full provided grips
- home parameter grips
- destination parameter grips

## Delta Identity

Every synchronized delta has a `delta_id`.

Rules:

- `delta_id` must be globally unique within the session
- replicas use `delta_id` for deduplication
- replay and live streams use the same `delta_id` values

`delta_id` is opaque in v1. UUIDv7 or ULID-style identifiers are acceptable.

## Lease Identity

Every negotiated primary lease has a `lease_id`.

Rules:

- one active negotiated lease exists per negotiated-primary tap at a time
- lease messages refer to the same `lease_id` across grant, renew, revoke, and release

## Message Identity

Every control-plane message has a `message_id`.

Rules:

- `message_id` is used for tracing and idempotence handling where needed
- `message_id` is not the same as `delta_id`
- control messages and graph deltas are distinct identity domains
