# FlowSpec: Formal Design Before AI Coding

This is a standalone product presentation. It is written so a developer can read it without already knowing TLA+, TLC, model checking, formal verification, or FlowSpec.

The target reader is a normal day-to-day engineer who uses AI heavily, ships business systems, and wants a better way to design and validate workflows before generating or writing production code.

---

## Slide 1: FlowSpec

# FlowSpec

## Formal design before AI coding

You already use AI to move faster.

FlowSpec helps you avoid moving faster in the wrong direction.

It gives you a practical way to design and check the business workflow before you ask AI, or a human, to build the implementation.

The short version:

```text
describe the workflow
state the rules
check the possible outcomes
fix the design early
then build with confidence
```

---

## Slide 2: Who This Is For

FlowSpec is for normal engineers building real business software.

You might not care about formal verification.

You might not know TLA+.

You might rely heavily on AI coding tools.

That is exactly the audience.

Examples:

```text
payments
refunds
orders
subscriptions
approvals
inventory reservations
loan applications
revenue recognition
account lifecycle
period close
```

You do not need to know TLA+ to understand the goal.

You only need to recognize this problem:

```text
the code works for the happy path
but breaks when events happen in a weird order
```

---

## Slide 3: The Promise

FlowSpec helps you answer questions before implementation:

```text
Can this workflow reach a bad state?
Can retry break it?
Can two workers process the same thing?
Can money move only halfway?
Can an object become "done" too early?
Did we define what "done" really means?
```

The pitch is simple:

```text
do not wait for production, QA, or random testing
to discover that the design was incomplete
```

---

## Slide 4: The AI Coding Problem

AI makes implementation very fast.

That is useful, but it changes the failure mode.

Before AI:

```text
slow code
slow feedback
manual implementation mistakes
```

With AI:

```text
fast code
fast iteration
same unclear design
more code built on top of weak assumptions
```

The problem is not that AI writes code.

The problem is that AI makes it easy to skip the design step.

---

## Slide 5: Why This Hurts Normal Developers

When AI generates a lot of code, the codebase starts looking real very quickly.

That creates a trap:

```text
the app has files
the tests pass
the UI works
the endpoint responds
so the design feels done
```

But the hard question is still unanswered:

```text
is this workflow actually correct?
```

FlowSpec exists for that gap.

---

## Slide 6: Prompt-And-Patch Is Not Design

A common AI workflow looks like this:

```text
describe feature
generate code
run it
find bug
prompt fix
run again
find another bug
prompt fix again
```

This can work for simple UI or CRUD work.

It is dangerous for workflows with:

```text
state
money
retries
concurrency
external callbacks
approval rules
business invariants
```

In those systems, the hardest bugs are often design bugs, not syntax bugs.

---

## Slide 7: The Real Failure

The dangerous failure is usually not:

```text
this line of code is wrong
```

The dangerous failure is:

```text
this sequence of events was possible
and nobody designed for it
```

Examples:

```text
payment callback arrives twice
refund races with settlement
approval races with cancellation
worker A and worker B process the same item
cash is received before revenue can be recognized
an order is shipped after it was cancelled
```

These bugs happen because the system can reach a bad state.

---

## Slide 8: The Better Workflow

Instead of:

```text
requirement
  -> AI prompt
  -> code
  -> patch bugs
```

FlowSpec pushes for:

```text
requirement
  -> workflow model
  -> properties
  -> model check
  -> implementation
```

The goal is not to write more paperwork.

The goal is to make the important behavior precise before code exists.

---

## Slide 9: What The Developer Gets

With FlowSpec, the developer gets:

```text
a readable workflow document
automatic TLA+ generation
model-checker feedback
counterexamples when the design is wrong
an editor workflow inside VS Code
a Dockerized checker setup
```

The value is not "learn math".

The value is:

```text
catch workflow bugs before they become application code
```

---

## Slide 10: The Core Question

Most implementation testing asks:

```text
Does this example work?
```

FlowSpec asks:

```text
What states can the system reach?
Which moves are allowed?
What must never happen?
What must always stay true?
What should eventually happen?
```

That is the design mindset behind formal verification.

---

## Slide 11: What Is A State Machine?

A state machine is a system described by:

```text
current state
allowed moves
next state after each move
```

A payment is already a state machine:

```text
PENDING -> POSTED
PENDING -> REJECTED
POSTED  -> REFUNDED
```

An order is already a state machine:

```text
DRAFT -> CONFIRMED -> SHIPPED -> DELIVERED
```

FlowSpec makes these state machines explicit and checkable.

---

## Slide 12: What A Model Is

A model is a simplified version of the system that keeps the important rules.

For a payment, the model might keep:

```text
payment status
source balance
destination balance
processed events
```

The model does not need:

```text
HTTP routes
database migrations
UI screens
framework code
logging
deployment details
```

The model captures the workflow core.

---

## Slide 13: What Formal Verification Means

Formal verification means checking a precise model against precise properties.

The model says:

```text
what state exists
where the system starts
which moves are allowed
how moves change state
```

The properties say:

```text
what must never happen
what must always remain true
what should eventually happen
```

If both are precise, a checker can explore many possible states and event orderings.

---

## Slide 14: Core Terms

State:

```text
the current facts about the system
```

Move:

```text
one allowed transition from one state to the next
```

Bad state:

```text
something that must never be reachable
```

Invariant:

```text
a rule that must hold in every reachable state
```

Liveness:

```text
something that should eventually happen
```

---

## Slide 15: Example Terms In A Payment

State:

```text
status = PENDING
sourceBalance = 100
destinationBalance = 0
amount = 10
```

Move:

```text
Post payment
```

Bad state:

```text
sourceBalance < 0
```

Invariant:

```text
if status is POSTED, then money moved consistently
```

Liveness:

```text
a pending payment eventually becomes posted or rejected
```

---

## Slide 16: Existing Formal Tools

FlowSpec is not inventing formal verification.

There are serious tools already:

```text
TLA+      formal specification language
TLC       model checker for TLA+
Alloy     relational modeling
Coq/Lean  theorem proving
Ivy       protocol verification
PlusCal   algorithm notation that translates to TLA+
```

FlowSpec builds on TLA+ and TLC.

It provides a business-workflow front door.

---

## Slide 17: What Is TLA+?

TLA+ is a formal language for describing systems as states and transitions.

A TLA+ transition can say:

```tla
Post ==
  /\ status = "PENDING"
  /\ sourceBalance >= amount
  /\ status' = "POSTED"
  /\ sourceBalance' = sourceBalance - amount
  /\ destinationBalance' = destinationBalance + amount
```

Meaning:

```text
if current status is PENDING
and source balance is enough
then next status is POSTED
and the balances change
```

The apostrophe means "next value".

---

## Slide 18: Why TLA+ Is Powerful

TLA+ is powerful because it does not describe one execution path.

It describes what transitions are possible.

That lets a checker explore different paths:

```text
Post then Settle
Settle blocked before Post
Cancel before Post
Retry Post twice
Callback arrives late
Two workers attempt same move
```

This is why TLA+ is useful for concurrency, workflows, protocols, and state-heavy systems.

---

## Slide 19: What Is TLC?

TLC is the model checker for TLA+.

It takes:

```text
TLA+ model
TLC configuration
properties to check
```

Then it explores the reachable state graph.

It is not a normal unit test runner.

It does not check one hand-written happy path.

It checks every reachable state inside the finite model you configured.

---

## Slide 20: What "Finite Model" Means

TLC needs finite domains so it can finish.

This is not checkable:

```text
balance is any integer
```

This is checkable:

```text
balance is one of {-10, 0, 10, 90, 100}
```

That does not mean TLC checks only one example.

It means TLC checks every reachable state inside the boundaries you gave it.

---

## Slide 21: Why The `.cfg` File Exists

TLC needs a `.cfg` file to know what to check.

The `.cfg` says things like:

```tla
SPECIFICATION Spec
INVARIANT NoOverdraft
```

It can also define finite constants:

```tla
CONSTANTS
  Account = {a1, a2}
```

Mental model:

```text
.fspec = human workflow design
.tla   = generated formal model
.cfg   = TLC run configuration
```

No `.cfg` means there is no complete TLC run.

---

## Slide 22: Why FlowSpec Exists

TLA+ is precise, but many business developers do not naturally think in this style:

```tla
/\ status = "PENDING"
/\ status' = "POSTED"
/\ UNCHANGED <<amount>>
```

They think like this:

```text
if payment is pending
and source balance is enough
then payment becomes posted
and balances change
```

FlowSpec keeps the business-language shape while still generating TLA+.

---

## Slide 23: FlowSpec Pipeline

FlowSpec is a bridge:

```text
Readable workflow spec
        |
        v
parse into FlowSpec IR
        |
        v
generate TLA+
        |
        v
run TLC
        |
        v
find broken states
```

The user writes a business-readable design.

The toolchain handles the formal backend.

---

## Slide 24: FlowSpec Example

```text
Machine: Payment

State:
  status is one of:
    PENDING
    POSTED
    REJECTED
  amount is one of {10}
  sourceBalance is one of {90, 100}
  destinationBalance is one of {0, 10}

Initially:
  status = PENDING
  amount = 10
  sourceBalance = 100
  destinationBalance = 0

Move: Post
  if status = PENDING
  if sourceBalance >= amount
  then status becomes POSTED
  then sourceBalance becomes sourceBalance - amount
  then destinationBalance becomes destinationBalance + amount
```

This reads like a workflow sheet, not raw TLA+.

---

## Slide 25: Add Safety Properties

FlowSpec can describe bad states:

```text
Bad state: Overdraft
  sourceBalance < 0
```

And invariants:

```text
Always: PostedMeansMoneyMoved
  status = POSTED => sourceBalance = 90 and destinationBalance = 10
```

These are the business promises the workflow must keep.

The checker tries to prove those promises over all reachable states in the finite model.

---

## Slide 26: The Deceptive Example

This looks reasonable:

```text
Move: Post
  if status = PENDING
  if sourceBalance >= amount
  then status becomes POSTED
  then sourceBalance becomes sourceBalance - amount
```

Many developers would say:

```text
we checked the balance
we posted the payment
we deducted the source balance
this is probably safe
```

But the destination balance never changed.

The status says "posted", but the money did not fully move.

---

## Slide 27: Why The Example Is Dangerous

The bug is not obvious if the only test checks:

```text
status became POSTED
source balance decreased
```

But the real business meaning of "posted" is stronger:

```text
the payment is complete
the debit happened
the credit happened
the balances are consistent
```

That meaning must be written as a property.

Otherwise the code can pass a shallow test while violating the real business rule.

---

## Slide 28: Let TLC Challenge The Design

Add the property:

```text
Always: PostedMeansMoneyMoved
  status = POSTED => sourceBalance = 90 and destinationBalance = 10
```

Now TLC can find the bad reachable state:

```text
status = POSTED
sourceBalance = 90
destinationBalance = 0
```

That state violates the business meaning of "posted".

The design is wrong before implementation starts.

That is exactly what we want to discover early.

---

## Slide 29: The Fix

The move must update both balances:

```text
Move: Post
  if status = PENDING
  if sourceBalance >= amount
  then status becomes POSTED
  then sourceBalance becomes sourceBalance - amount
  then destinationBalance becomes destinationBalance + amount
```

Now the design matches the property:

```text
posted means money moved consistently
```

This is the loop:

```text
write model
write property
run checker
learn from failure
fix design
```

---

## Slide 30: What FlowSpec Is Not

FlowSpec v0 is not trying to replace TLA+.

It is not trying to model every distributed algorithm.

It is not trying to become a general programming language.

It is not raw YAML.

The v0 focus is practical business workflows:

```text
money movement
approvals
inventory state
account lifecycle
subscription lifecycle
settlement workflows
period close workflows
```

---

## Slide 31: What FlowSpec Provides Today

Current v0 toolchain:

```text
Python compiler package
FlowSpec IR
TLA+ backend
TLC runner
Dockerized TLC image
VS Code extension
VSIX release workflow
realistic capability benchmark
internal onboarding docs
```

The important product idea:

```text
the user writes FlowSpec
FlowSpec generates TLA+
TLC checks the model
FlowSpec narrates failures in workflow language
the developer fixes the design before writing application code
```

---

## Slide 32: What A Failed Check Looks Like

The product should not make normal developers read raw model-checker traces first.

When TLC finds a broken workflow, FlowSpec narrates the failure in domain terms:

```text
violated property
FlowSpec move path
domain binding for each move
state changes at each step
source location for the move or property
```

Example shape:

```text
Invariant NoOverdraft failed.

Move path:
  1. WorkerReadsPending(worker=w1)
  2. WorkerReadsPending(worker=w2)
  3. WorkerPostsFromAttempt(worker=w1)
  4. WorkerPostsFromAttempt(worker=w2)

Step changes:
  3. WorkerPostsFromAttempt(worker=w1)
     sourceBalance: 100 -> 40
     destinationBalance: 0 -> 60
     status: PENDING -> POSTED

  4. WorkerPostsFromAttempt(worker=w2)
     sourceBalance: 40 -> -20
     destinationBalance: 60 -> 120
```

The point is not only that TLC found a bad state.

The point is that the developer can understand the bad state as a workflow story.

---

## Slide 33: CLI Workflow

Generate TLA+:

```sh
flowspec examples/payment.fspec
```

Run the suite with TLC and keep generated files:

```sh
flowspec-suite --tlc --tlc-logs -o generated-tla examples/payment.fspec
```

Run the larger capability benchmark:

```sh
flowspec-benchmark
```

The CLI is useful for:

```text
development
CI
debugging generated TLA+
running larger examples
```

---

## Slide 34: VS Code Extension

The extension is the main user surface.

It provides:

```text
.fspec syntax highlighting
autocomplete snippets
diagnostics
generated TLA+ preview
parse tree preview
run TLC current file
run suite
TLC failure diagnostics with related source locations
```

User workflow:

```text
install VSIX
open .fspec
configure python path if needed
run validation or TLC from the command palette
```

The extension calls the Python engine.

The Python engine generates TLA+ and runs TLC.

---

## Slide 35: Dockerized TLC

TLC normally requires Java and `tla2tools.jar`.

FlowSpec uses a Docker image:

```text
ghcr.io/mohamed-elfiky/flowspec-tlc:0.0.1
```

This keeps the checker isolated.

The user does not need to manually manage the TLC jar.

The goal is:

```text
less environment setup
more workflow checking
```

---

## Slide 36: Capability Benchmark

Toy examples are useful for learning, but they are not enough.

FlowSpec includes a larger business fixture:

```text
examples/capability/progress_billing.fspec
examples/capability/ProgressBilling.cfg
```

It models a more realistic workflow:

```text
contract approval
advance invoice
cash receipt
advance liability
progress assessment
revenue recognition
midpoint invoice
acceptance
acceptance rejection
final invoice
cash clearing
advance refund
cancellation cleanup
period close
```

The important point is not just that the workflow has many statuses.

The important point is that it separates business concepts that are often confused in real systems:

```text
contract amount
billed amount
cash received
recognized revenue
accounts receivable
advance liability
closed state
event history
rejection state
cancellation state
```

That separation is where the business correctness lives.

---

## Slide 37: What The Billing Example Proves

The billing benchmark checks a real accounting idea:

```text
cash received is not automatically revenue earned
```

For example:

```text
advance invoice issued
advance cash received
advance liability recorded
progress assessed
revenue recognized only after performance
liability cleared when revenue is earned
acceptance can be rejected
rejected acceptance must be resolved
cancelled work must not keep open revenue, receivable, or liability
```

That is a domain rule, not a programming trick.

FlowSpec lets that rule become executable and checkable.

---

## Slide 38: The Strong Properties

The strongest part of the billing example is the properties.

It checks rules like:

```text
advance cash must not create revenue
final revenue requires acceptance
midpoint cash requires midpoint invoice
final cash requires final invoice
closed means fully recognized
closed means fully collected
rejection blocks final revenue
cancelled work cannot remain half-accounted
```

These are cross-cutting business invariants.

They define what "correct" means across the whole lifecycle.

---

## Slide 39: What This Benchmark Does Not Claim

The billing benchmark is mostly a sequential lifecycle model.

It proves:

```text
the staged accounting workflow is internally consistent
bad accounting states are unreachable
the event-ordering rules hold
closed has a precise business meaning
```

It does not, by itself, prove every concurrency story.

For concurrency demos, the model needs competing moves:

```text
duplicate callbacks
two workers processing the same item
correction racing with recognition
cancel racing with approval
retry racing with settlement
```

This is an important product boundary: FlowSpec can model those cases, but the benchmark must include them to prove them.

---

## Slide 40: Why This Matters For AI

AI is good at producing code.

But AI should not invent the core workflow rules while coding.

FlowSpec gives AI a better boundary:

```text
verified workflow core
clear state transitions
explicit invariants
generated formal model
checked behavior
```

Then AI can help build around it:

```text
API layer
database integration
UI
queue workers
logging
deployment
tests
```

---

## Slide 41: V1 Direction

The v1 direction is code generation.

FlowSpec should generate the functional core:

```text
state types
workflow enums
commands
guard checks
transition functions
invariant helpers
```

The application remains the imperative shell:

```text
HTTP
database
queues
auth
provider calls
observability
UI
```

This matches the pattern:

```text
functional core
imperative shell
```

---

## Slide 42: Functional Core, Imperative Shell

Generated core:

```text
state + command -> new state or transition error
```

Application shell:

```text
receive request
load state
call generated transition
save state
publish event
render response
```

This is useful with AI because it gives the model a hard boundary.

AI can write the shell.

FlowSpec owns the checked workflow rules.

---

## Slide 43: Why FlowSpec Is Better Than Plain Docs

Plain design docs are readable, but they are not executable.

They cannot answer:

```text
can this bad state happen?
did we miss a transition?
does retry break the workflow?
does cancellation race with approval?
does posted really mean money moved?
```

FlowSpec keeps the document readable, but makes it checkable.

That is the product value:

```text
design document
plus executable model
plus model checker
```

---

## Slide 44: Why FlowSpec Is Not Just Testing

Tests usually check examples you remembered to write.

Model checking explores reachable states inside a finite model.

A unit test might say:

```text
when I post this payment, status becomes POSTED
```

TLC can ask:

```text
across all allowed moves and orderings,
can this invariant ever break?
```

That is a different level of confidence.

---

## Slide 45: Current Status

FlowSpec currently has:

```text
DSL examples
Python CLI
TLA+ generation
TLC Docker runner
VS Code extension
VSIX release workflow
capability benchmark
internal onboarding docs
```

It is early, but usable.

The next major improvements are:

```text
better diagnostics
clearer config generation
state-space reporting
stronger extension workflow
more realistic business fixtures
eventual code generation
```

---

## Slide 46: Try It

Repository:

```text
https://github.com/mohamed-elfiky/flowspec
```

Generate TLA+:

```sh
flowspec examples/payment.fspec
```

Run TLC:

```sh
flowspec-suite --tlc --tlc-logs examples/payment.fspec
```

Install the VS Code extension:

```text
GitHub Releases -> Assets -> flowspec-vscode-*.vsix
```

---

## Slide 47: What Feedback We Need

The useful feedback is practical:

```text
Is the notation natural?
Can a normal developer read it?
Can it model real workflows?
Which diagnostics are missing?
Where does the DSL feel too technical?
Where does it hide too much?
Which examples would make adoption easier?
```

The goal is not to impress formal-methods experts.

The goal is to help normal engineers design better systems before AI or humans write the implementation.

---

## Slide 48: Closing

The future of AI coding should not be:

```text
generate code until it seems to work
```

It should be:

```text
design the system
define the properties
verify the workflow
generate the core
build around it
```

FlowSpec exists to make that workflow practical for business software.
