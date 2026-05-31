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

This means “for each `Account`, there is one `balance`.” In programming terms it is like a dictionary or map, but the DSL phrase keeps the focus on the business model.

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
