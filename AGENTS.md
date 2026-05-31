# FlowSpec Agent Guide

This repository builds FlowSpec, a DSL for business workflow design and validation.

When helping in this repo, keep the product boundary clear:

- FlowSpec v0 is for complex business workflows.
- It is not for Paxos, Raft, consensus protocols, or research distributed systems.
- The target user is a day-to-day application programmer using AI coding tools.
- The spec should become a validated domain core that code generation and AI-authored application code build around.

## DSL Style

Prefer declarative business language:

```text
Move: Post
  if status = PENDING
  if sourceBalance >= amount
  then status becomes POSTED
```

Prefer `per` for entity-indexed state:

```text
balance per Account is int
status per Order is one of:
  DRAFT
  PAID
  SHIPPED
```

Avoid exposing map/table syntax in user-facing examples unless compatibility is being discussed.

## Good V0 Models

- payment posting
- account closure
- refunds
- order fulfillment
- inventory reservation
- approval workflows
- retries, duplicate commands, delayed events
- concurrent business transitions

## Commands

Run the supported compile suite:

```sh
flowspec-suite
```

Validate one file semantically:

```sh
flowspec --diagnostics-json examples/payment.fspec
```

Preview generated TLA+:

```sh
flowspec examples/payment.fspec
```

Run TLC through the isolated Docker backend:

```sh
flowspec-suite --tlc
```

Check the VS Code extension:

```sh
npm run check --prefix extension
```

## Implementation Rules

- Keep syntax and docs aligned with `grammar.lark`.
- Prefer adding semantic diagnostics before adding broader syntax.
- Do not silently accept vague prose; produce clear errors or require named predicates/constants.
- Keep generated TLA+ valid and inspectable.
- Keep Docker as the default TLC isolation backend.
