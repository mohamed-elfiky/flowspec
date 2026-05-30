# AI Authoring Guide

Use this guide when an AI assistant writes or edits FlowSpec specs.

The goal is not to produce code first. The goal is to produce a business workflow model that can be checked before code is generated or implemented.

## Start From Business Questions

Ask or infer:

- What are the business entities?
- What state can each entity be in?
- What moves are allowed?
- What moves must be impossible?
- What bad states should never happen?
- What race conditions matter?
- What retries, duplicate commands, or delayed events can happen?

## Preferred Shape

```text
Machine: Payment

State:
  status is one of:
    PENDING
    POSTED
    REJECTED
  balance per Account is int

Initially:
  status = PENDING

Move: Post
  if status = PENDING
  then status becomes POSTED

Bad state: PostedAndRejected
  status = POSTED and status = REJECTED
```

## Use `per` For Business-Owned Values

Use:

```text
balance per Account is int
status per Order is one of:
  DRAFT
  PAID
  SHIPPED
```

Avoid making users write:

```text
balance is Account -> int
balance is a table from Account to int
```

Those forms may exist for compatibility, but they are not the preferred business-design language.

## Model Concurrency As Interleavings

Do not introduce threads, locks, queues, handlers, or implementation details first.

Instead, write moves that can happen in different orders:

```text
Move: Approve
  if status = PENDING
  then status becomes APPROVED

Move: Cancel
  if status = PENDING
  then status becomes CANCELED

Bad state: ApprovedAndCanceled
  status = APPROVED and status = CANCELED
```

For retries and duplicate commands, model the repeated command as another enabled move or track processed IDs.

## Avoid Out-Of-Scope Models

Do not push v0 toward:

- Paxos
- Raft
- consensus
- low-level network protocols
- arbitrary mathematical proof assistants
- raw TLA+ syntax

If a workflow requires advanced math, prefer a named external predicate in `Given` only when there is a clear business reason.

## Validate After Every Edit

Run:

```sh
flowspec --diagnostics-json <file.fspec>
flowspec-suite
```

Fix semantic diagnostics before proposing implementation code.

## Good Output From AI

A good AI-written spec:

- has a clear `Machine` name
- declares all state
- initializes all state
- uses business vocabulary
- includes at least one meaningful `Bad state`
- models retries/concurrency when relevant
- compiles with no semantic errors

A weak AI-written spec:

- only mirrors database fields
- has no bad states
- uses vague prose the compiler cannot check
- skips concurrency or duplicate command behavior
- jumps straight to application code
