# Glial SDD Section 11: Auth Integration Boundary

## Overview

Authentication is outside Glial.

Glial consumes an already-authenticated identity or claims envelope supplied by the host environment. Glial is responsible for using that information consistently. It is not responsible for authenticating the user itself.

## Required Integration Contract

The host environment must provide Glial with an authenticated principal for each connection.

Minimum required information:

- stable user identity
- authenticated claims envelope
- session identifier to join

Examples:

- JWT claims validated by FastAPI before Glial sees the request
- equivalent authenticated claims from another framework

## Session Claim Consistency

All replicas participating in the same session must present the same claims envelope for Glial-controlled behavior.

This prevents:

- accidental privilege changes during ownership transfer
- a backend replica silently acquiring more authority than the user session it serves
- function or tool execution changing effective authorization context

## What Glial Checks

Glial is responsible for:

- rejecting connections whose supplied session claims do not match the established session claims envelope
- ensuring ownership transfers do not cross claims boundaries
- using the claims envelope consistently for lease and mutation policy checks

## What Glial Does Not Do

Glial does not:

- validate passwords or OAuth flows
- issue JWTs
- manage external identity providers
- define application-specific authorization policy beyond its own coordination needs

## Recommended Host Integration

Recommended v1 deployment:

- application framework authenticates the request
- authenticated principal is forwarded to Glial gateway/router
- gateway/router passes an integrity-protected claims representation to the owning shard

FastAPI is a good example host environment, but the model is framework-neutral.
