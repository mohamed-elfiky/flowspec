# FlowSpec User Guide

FlowSpec lets you describe a business workflow as a state machine, then compile that design to TLA+ for model checking.

Use it before implementation. The goal is to catch invalid states, missing transitions, and broken assumptions before asking AI or humans to write application code.

This is especially useful for concurrency. TLC checks possible orderings of moves, so a spec can expose everyday race conditions: two workers posting the same payment, an approval arriving after cancellation, an inventory item being reserved twice, or a retry message being handled after the workflow already moved on.

## Small Example

```text
Machine: Payment

State:
  status is one of:
    PENDING
    POSTED
    REJECTED
  amount is nat
  sourceBalance is int
  destinationBalance is int

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

Bad state: Overdraft
  sourceBalance < 0
```

This says:

- the workflow is called `Payment`
- payment state starts as `PENDING`
- `Post` can run only when funds are available
- an overdraft is a bad state

This example is intentionally small. Real value comes when you add the uncomfortable cases that product code usually handles badly:

- the same command runs twice
- a retry arrives after the workflow already moved on
- an external provider returns an unknown result
- a cancellation races with approval
- a reversal arrives after a successful posting
- an audit or reconciliation event is missing

Those are design problems, not just test cases. FlowSpec gives you a place to write them before implementation.

## File Shape

Every FlowSpec file starts with a machine name:

```text
Machine: Account
```

Then add sections:

```text
Given:
State:
Initially:
Move:
Bad state:
Always:
Eventually:
Fairness:
```

Indent section contents with spaces.

## Given

Use `Given` for external sets or constants supplied by the model.

```text
Given:
  Account
```

Generated TLA+ treats these as constants.

## State

Use `State` for variables that change over time.

```text
State:
  status is one of:
    OPEN
    CLOSED
  balance per Account is nat
```

Common types:

```text
status is one of:
  PENDING
  POSTED

amount is nat
balance is int
owner is Account
balance per Account is int
status per Order is one of:
  DRAFT
  PAID
  SHIPPED
seenIds is a set of PaymentIds
```

Enum values are written as plain words in FlowSpec and generated as TLA+ strings.

For TLC runs, keep model domains finite. `nat` and `int` are useful for documenting intent, but TLC cannot enumerate all natural numbers or integers. Use a small explicit domain in runnable examples:

```text
amount is one of {10}
sourceBalance is one of {90, 100}
```

Use `per` when the business has one value for each entity:

```text
balance per Account is int
status per Order is one of:
  DRAFT
  PAID
  SHIPPED
limit per Customer is nat
```

This means "for each `Account`, there is one `balance`." In programming terms it is like a dictionary or map, but the DSL phrase keeps the focus on the business model.

## Initially

Use `Initially` for the starting state.

```text
Initially:
  status = PENDING
  balance = map account in Account -> 0
```

## Moves

Moves describe transitions.

```text
Move: Close
  if status = OPEN
  then status becomes CLOSED
  same balance
```

Move lines:

- `if ...` adds a guard.
- `then x becomes ...` changes state.
- `then x gains ...` adds an item to a set.
- `same x` documents that state should not change.
- unchanged state is emitted automatically for variables not changed by the move.

Quantified moves:

```text
Move: Debit
  for some account in Account
  if balance[account] >= amount
  then balance[account] becomes balance[account] - amount
```

Think of each `Move` as something that could happen next. TLC explores different orderings of enabled moves, which is how FlowSpec helps catch concurrency bugs before code exists.

## Messages

Use `Messages` for business events or commands.

```text
Messages:
  Prepared message has:
    type = Prepared
    rm in RM
```

Then use messages in moves:

```text
then msgs gains Prepared(rm)
```

This is useful for workflows that pass events between actors or services.

## Bad States

Bad states describe things that must never happen.

```text
Bad state: NegativeBalance
  some account in Accounts has balance[account] < 0
```

The compiler also emits a positive invariant name:

```text
NoNegativeBalance
```

Use that in TLC configs.

## Always

Use `Always` for invariants.

```text
Always: StatusIsKnown
  status is one of {PENDING, POSTED, REJECTED}
```

## Eventually

Use `Eventually` for liveness expectations.

```text
Eventually: ClosedEventually
  status = CLOSED
```

## Fairness

Use `Fairness` when a move should eventually happen if it remains enabled.

```text
Fairness:
  weak Close
```

## Expressions

Common expression forms:

```text
status = OPEN
status is not CLOSED
status is one of {OPEN, CLOSED}
amount >= 0
sourceBalance < amount
account in Accounts
some account in Accounts has balance[account] < 0
every account in Accounts has balance[account] >= 0
no payment in Payments has payment.status = FAILED
```

Arithmetic and sets:

```text
balance - amount
balance + amount
seenIds plus {id}
Ballot except {0}
```

## System Design With Properties

FlowSpec is not just a nicer syntax for TLA+. The useful part is the design discipline it pushes: describe the business world, describe what can happen, then write properties that say what must never break.

Think in this order:

1. What exists in the business?
2. What state changes over time?
3. What actions, events, retries, timeouts, or reconciliation records can move the system forward?
4. What bad outcomes are unacceptable?
5. What facts should always remain true?
6. What progress should eventually happen, if the environment keeps cooperating?

The goal is not to model every line of future code. The goal is to model the business rules strongly enough that TLC can explore weird orderings, retries, and edge cases before implementation.

### State Space

The state space is the set of all possible states your workflow can be in.

For a payment system, state might include:

```text
State:
  status is one of:
    PENDING
    POSTED
    REJECTED
  sourceBalance is one of {0, 50, 100}
  destinationBalance is one of {0, 50, 100}
```

This does not say what happens. It only defines the shape of the world. TLC will later explore reachable combinations of these values.

Good state variables are business facts:

- payment status
- account balance
- approval state
- reserved quantity
- retry decision
- messages already received
- reconciliation events already processed

Avoid starting with implementation facts:

- database row locks
- HTTP route names
- queue topic names
- class names
- framework callbacks

Those may matter later, but v0 FlowSpec works best when the first model is the business workflow.

### Moves

Moves are the things that can happen next.

A move can represent a user command, provider callback, worker retry, timeout, reconciliation record, approval, cancellation, or internal business decision.

```text
Move: Post
  if status = PENDING
  if sourceBalance >= amount
  then status becomes POSTED
  then sourceBalance becomes sourceBalance - amount
  then destinationBalance becomes destinationBalance + amount
```

Do not assume moves run in the order they appear in the file. TLC treats enabled moves as possible next steps. That is what makes the model useful for concurrency: if two things could happen in either order in production, the model should allow TLC to try both orders.

A guard says when a move is legal:

```text
if status = PENDING
if sourceBalance >= amount
```

An effect says what changes:

```text
then status becomes POSTED
```

If a rule depends on ordering, encode that ordering in state and guards. Do not rely on document order.

### Hidden Outcomes

The bugs worth finding are usually not in the happy path. They live in the gaps between moves.

A normal implementation discussion might say:

```text
When payment is pending and funds are available, post it.
```

That is not enough for system design. Ask what else can happen around that move:

- Can `Post` run twice for the same payment?
- Can `Reject` run after `Post`?
- Can a retry use stale state?
- Can two workers both observe enough balance before either writes the new balance?
- Can a reversal happen before the original event is recorded?
- Can reconciliation say the provider disagrees with our local state?
- Can the system reach a terminal status with missing evidence?

In FlowSpec, each of those questions becomes either another move or another property.

For example, duplicate execution should be modeled as another possible move ordering, not hidden inside code:

```text
Move: Post
  if status = PENDING
  if sourceBalance >= amount
  then status becomes POSTED
  then sourceBalance becomes sourceBalance - amount

Move: RetryPost
  if status = POSTED
  then status becomes POSTED
  same sourceBalance
```

Then the property says what must remain true even if the retry happens:

```text
Bad state: PostedTwice
  postedCount > 1
```

If your current state does not have enough information to express `PostedTwice`, that is a design signal. You may need state like `postedCount`, `processedCommandIds`, `ledgerEntries`, or `reconEvents`. Properties often teach you what state the design actually needs.

### Concurrency Violations

TLC does not run threads like a production runtime. It does something more useful at the design level: it explores possible next moves from each state. If your model says two moves are both possible, TLC can try both orders.

That catches violations like:

- double debit: two postings reduce the same balance twice
- lost update: one move overwrites evidence written by another move
- stale decision: an approval uses state that was valid before cancellation
- invalid terminal transition: a workflow leaves `POSTED` and returns to `PENDING`
- missing compensation: a reversal changes money but does not record the reverse event
- impossible recovery: an `UNKNOWN` result has no move that can resolve it

For business workflows, these are the failures that matter. They are hard to catch with example-based unit tests because the bug is in the ordering, not in one function call.

### Properties

A property is an executable design claim. It turns a vague requirement into something TLC can check.

Bad properties are usually vague:

```text
The payment system should be correct.
```

Good properties are concrete:

```text
Bad state: Overdraft
  sourceBalance < 0
```

When TLC finds a violation, it gives a path of moves that reaches the bad state. That path is often more useful than a normal unit test because it shows a design-level failure, not just a function-level failure.

### Safety Properties

Safety means "something bad never happens."

In FlowSpec, use `Bad state` for the bad thing directly:

```text
Bad state: NegativeBalance
  some account in Account has balance[account] < 0
```

The compiler also emits the positive invariant name:

```text
NoNegativeBalance
```

Use that positive name in the TLC config.

Good safety properties for business systems:

- no balance becomes negative
- a closed account cannot receive a debit
- a posted payment is never posted twice
- inventory is never reserved below zero
- a rejected request never later becomes approved
- a reverse event is never processed before the original event exists
- a terminal workflow never returns to a non-terminal state

Safety properties are the first properties to write. They catch the highest-value bugs early.

### Invariants

An invariant is a fact that must be true in every reachable state.

Use `Always` when you want to name a positive rule:

```text
Always: StatusIsKnown
  status is one of {PENDING, POSTED, REJECTED}
```

Use invariants for rules like:

- every status is from the allowed business vocabulary
- completed work has the required audit record
- every reserved item belongs to a known order
- every reversal has a matching original transaction
- a terminal state has enough evidence to explain how it got there

For example:

```text
Always: ReversalHasOriginal
  every request in Request has topupStatus[request] = REVERSED => Topup(request) is in reconEvents
```

The difference between `Bad state` and `Always` is mostly how you think about the rule:

- use `Bad state` when the easiest wording is "this must never happen"
- use `Always` when the easiest wording is "this must always be true"

Both are safety checks when used as TLC invariants.

### Liveness Properties

Liveness means "something good eventually happens."

Use `Eventually` for progress expectations:

```text
Eventually: PaymentFinishes
  status is one of {POSTED, REJECTED}
```

Be careful with liveness. A model checker is allowed to choose any valid next move. If a move stays enabled forever but TLC is allowed to ignore it forever, an eventual property may fail even though the business rule sounds reasonable.

That is where fairness matters.

### Fairness

Fairness tells TLC that a move should not be ignored forever when it remains available.

```text
Fairness:
  weak Post
```

Use fairness when a move represents a reliable worker, scheduler, or system process that should eventually run if it keeps being enabled.

Do not add fairness just to silence a failing liveness check. First ask whether the business really guarantees that progress. For example:

- A local worker that always retries may justify fairness.
- A third-party provider callback may not justify fairness.
- A human approval step usually should not be fair unless the business assumes approval eventually happens.

Fairness is a modeling assumption. Treat it like a product decision.

### Property Types At A Glance

| FlowSpec form | Design meaning | Typical question |
| --- | --- | --- |
| `TypeOK` | generated type invariant | Are states inside their declared domains? |
| `Bad state` | forbidden state | Can this unacceptable outcome happen? |
| `Always` | invariant | Is this rule true after every move? |
| `Eventually` | liveness | Does the workflow eventually reach a good condition? |
| `Fairness` | scheduling assumption | If this action stays possible, must it eventually run? |

### Designing A Workflow

For a realistic workflow, start from the failure modes.

Example: wallet top-up.

Business questions:

- Can the merchant wallet go negative?
- Can the user wallet go negative after reversal?
- Can a top-up be completed without a reconciliation record?
- Can a reverse record exist without the original top-up record?
- What happens if the provider result is unknown?
- Can polling complete after a local timeout already marked the request failed?
- Can the same provider event be processed twice?
- Can a retry create a second top-up instead of observing the first result?
- Is polling guaranteed, or merely possible?

That turns into FlowSpec concepts:

```text
State:
  topupStatus per Request is one of:
    NOT_STARTED
    PENDING
    COMPLETED
    FAILED
    UNKNOWN
    REVERSED
  walletBalance per Wallet is one of {0, 50, 100}
  reconEvents is a set of Messages
```

Then model the uncertain parts explicitly:

```text
Move: TopupResultUnknown
  for some request in Request
  if topupStatus[request] = PENDING
  then topupStatus[request] becomes UNKNOWN

Move: PollDetailsCompleted
  for some request in Request
  if topupStatus[request] = UNKNOWN
  then topupStatus[request] becomes COMPLETED
```

Then write the properties:

```text
Bad state: WalletOverdrawn
  some wallet in Wallet has walletBalance[wallet] < 0

Bad state: ReverseWithoutTopup
  some request in Request has TopupReverse(request) is in reconEvents and not Topup(request) is in reconEvents
```

This is system design: not drawing boxes, not naming services, and not choosing a framework. It is making the rules precise enough that invalid behavior can be explored before code exists.

### Design Checklist

Before calling a spec useful, ask:

- Did we model every business state that affects correctness?
- Did we include retries, delayed events, duplicate events, and reversals where relevant?
- Did we include hidden outcomes where two valid moves happen in a surprising order?
- Did we write the bad outcomes explicitly?
- Did we write positive invariants for facts that must always hold?
- Did we avoid assuming move order unless a guard enforces it?
- Did we keep TLC domains small and finite?
- Did we avoid adding fairness unless the system really guarantees progress?
- Did every counterexample teach us something about the design?

A good FlowSpec model should make implementation conversations sharper. After the model passes, engineers and AI tools have a clearer core to build around.

## Compile

Compile a FlowSpec file to TLA+:

```sh
flowspec examples/payment.fspec
```

Write output to a file:

```sh
flowspec examples/payment.fspec -o Payment.tla
```

Print the parse tree when debugging grammar issues:

```sh
flowspec --tree examples/payment.fspec
```

## Run The Suite

Compile all supported examples:

```sh
flowspec-suite
```

Build the isolated TLC image:

```sh
docker build \
  -f docker/tlc/Dockerfile \
  -t flowspec-tlc:local \
  .
```

Run TLC inside Docker:

```sh
flowspec-suite --tlc
```

Released versions can use a published image instead of a local build:

```sh
FLOWSPEC_TLC_IMAGE=ghcr.io/mohamed-elfiky/flowspec-tlc:0.0.1 flowspec-suite --tlc
```

## Realistic Example Fixtures

The supported examples are intentionally business-shaped:

- `examples/payment.fspec` models posting a payment without overdrawing the source balance.
- `examples/wallet_topup.fspec` models a wallet top-up flow: submit, completed, failed, unknown provider result, polling for details, and reconciliation reversal.
- `examples/account.fspec` models per-account state.

The provider-inspired fixture is useful because it looks like real integration work: a provider can return an unknown result, the system must poll before deciding, and reconciliation can later report a reverse event. That is the kind of workflow ambiguity FlowSpec should make explicit before implementation.

## What To Model First

Start with the business states and the bad outcomes.

Good v0 candidates:

- payment posting
- account closure
- refunds
- approvals
- subscription lifecycle
- order fulfillment
- inventory reservation
- compliance review
- duplicate payment handling
- retry and timeout handling
- concurrent approval and cancellation

Avoid modeling implementation details first. Do not start with database tables, queues, HTTP handlers, or framework code. Model the workflow rules first, validate them, then generate or write code around the validated core.
