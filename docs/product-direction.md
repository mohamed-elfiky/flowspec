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

## V1 Manifesto: Functional Core, Imperative Shell

FlowSpec v1 code generation should not generate whole applications.

FlowSpec should generate the verified functional core of a workflow:

```text
pure state shapes
workflow enums
command/move types
guard checks
transition functions
invariant helpers
small transition errors
```

The generated core should be pure and composable:

```text
state + command -> new state or transition error
```

It should not own the imperative shell:

```text
HTTP handlers
database transactions
message queues
provider calls
auth
logging
metrics
UI
retry scheduling
```

Developers and AI tools should build that shell around the generated core. This keeps adoption practical: teams can keep their framework, database, and deployment model while using FlowSpec for the most important part, the checked business transition logic.

The v1 codegen responsibility is intentionally limited:

```text
generate correct functional workflow logic
not a full application platform
not a database schema system
not an API framework
not a rich domain type language
```

Enums and workflow states are the first high-value codegen target. They reduce drift between the checked spec and application code without forcing FlowSpec to become a general type system. Numeric finite domains can remain model-checking domains first; generated application code can use practical primitive types where that is more useful.

The product message is:

```text
FlowSpec does not generate your application.
FlowSpec generates the verified functional core of your workflow.
Your application remains the imperative shell around that core.
```

## Capability Benchmark

FlowSpec needs one larger real-world fixture that acts as a capability, correctness, and performance signal for v0. The current fixture is:

```text
examples/capability/progress_billing.fspec
```

It models a progress-billing workflow for a project-based business:

```text
contract signed
advance invoice issued
advance cash received and treated as liability
40% progress assessed
40% revenue recognized
75% progress assessed
75% revenue recognized
midpoint invoice issued
acceptance recorded
final revenue recognized
midpoint cash cleared
final invoice issued
final cash cleared
period closed
```

This fixture is intentionally more realistic than the small tutorial examples. It checks that FlowSpec can keep separate business concepts separate:

```text
contract amount != recognized revenue
invoice amount != cash receipt
advance cash != earned revenue
acceptance != billing
collection != period close
```

Correctness is measured by compiling it to TLA+ and running TLC against its `.cfg` invariants. Performance is measured separately so the default suite stays fast:

```sh
flowspec-benchmark
flowspec-benchmark --tlc --tlc-image flowspec-tlc:local
flowspec-benchmark --tlc --tlc-logs --tlc-image flowspec-tlc:local
```

This benchmark should grow carefully. It should represent hard business workflows, not research distributed systems. If a new DSL feature cannot make this fixture clearer, safer, or easier to validate, it is probably not a v0 priority.

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
