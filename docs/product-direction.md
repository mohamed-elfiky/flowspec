# Product Direction

FlowSpec v0 is for complex business workflows, not research distributed systems.

The target user is an application programmer who needs to design and validate behavior before implementation. They may rely heavily on AI to write code, but they still need a precise source of truth for the system's allowed states, transitions, invariants, and bad states.

Concurrency is a core reason this exists. Business systems fail when valid actions arrive in surprising orders: retries, duplicate commands, delayed events, two workers processing the same entity, or approval and cancellation racing each other. FlowSpec should help programmers model those interleavings without forcing them to learn raw TLA+ first.

## Product Thesis

FlowSpec's job is not only to simplify TLA+ syntax.

The hard part is learning to think abstractly about the system:

```text
not code order, but possible states
not function calls, but enabled moves
not happy paths, but all behaviors
not patching edge cases, but writing properties that rule them out
```

FlowSpec should help everyday developers practice that design discipline without making them start from raw mathematical notation. The product should make abstract system thinking feel approachable while keeping the generated model precise enough for TLC.

## Core Workflow

```text
Write business workflow spec
        -> generate TLA+
        -> run TLC
        -> fix design mistakes
        -> generate application-core code
        -> let AI build services, APIs, UI, and integrations around that core
```

## V0 Fits

- Banking account lifecycle
- Transfers and payment posting
- Loan approval
- KYC and compliance review
- Subscription state
- Order fulfillment
- Inventory reservation
- Refunds and chargebacks
- Document approval
- Multi-party business coordination
- Concurrent command handling
- Retries, timeouts, and duplicate messages

## V0 Does Not Fit

- Paxos, Raft, consensus protocols
- Low-level distributed systems research
- Arbitrary theorem proving
- Replacing hand-written TLA+
- General-purpose programming

## Design Rules

- Specs should read like declarative business design sheets.
- The language should stay close to how engineers describe workflows: `if`, `then`, `same`, `becomes`, `bad state`, `always`.
- Use business phrases like `balance per Account is int` for entity-indexed state instead of exposing map/table syntax as the primary interface.
- Concurrency support should focus on business interleavings, not low-level distributed algorithms.
- The compiler must prefer valid, checkable output over accepting vague prose.
- Unsupported concepts should be explicit boundaries, not silently guessed.
- Generated application code should eventually become the domain core, with AI-generated code built around it.
