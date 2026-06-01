# FlowSpec

FlowSpec is a small DSL for writing state-machine-first specifications and compiling them to TLA+.

The v0 target is practical business systems: banking workflows, account state, payment state, approvals, inventory, subscriptions, document lifecycles, and coordination flows that engineers commonly implement in application code. It is meant to catch workflow and concurrency bugs before implementation: duplicate commands, retries, delayed events, and racing state transitions.

The v0 target is not to replace TLA+ or model mathematically dense distributed algorithms. Research-style algorithms such as Paxos are useful pressure tests, but they are not part of the supported v0 surface.

The intended user is a day-to-day programmer, often working with AI coding tools, who wants to validate a design before asking AI to build the implementation. The spec should become the stable core that generated code and AI-authored application code build around.

## Pipeline

```text
Readable spec document
        -> parse
        -> generate TLA+
        -> run TLC, when a model config is provided
        -> find bad states and broken assumptions
```

## Supported V0 Shape

- `Given`
- `State`
- `Messages`
- `Initially`
- `Move`
- `Bad state`
- `Always`
- `Eventually`
- `Fairness`

Specs should feel like declarative specification sheets, not raw TLA+, general-purpose programming code, or YAML.

## Examples

Supported examples live in `examples/`:

- `transaction.fspec`: minimal state transition
- `account.fspec`: per-account state
- `payment.fspec`: payment posting and overdraft protection
- `wallet_topup.fspec`: wallet top-up, unknown provider result, polling, and reconciliation reversal
- `2pc.fspec`: coordination pressure test for messages and fairness

## Commands

Create a local environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Compile one example:

```sh
flowspec examples/account.fspec
```

Print the parse tree:

```sh
flowspec --tree examples/account.fspec
```

Write generated TLA+ files from a suite run:

```sh
flowspec-suite -o generated-tla examples/payment.fspec
```

Run the supported suite:

```sh
flowspec-suite
```

Run the larger capability benchmark:

```sh
flowspec-benchmark
flowspec-benchmark --tlc --tlc-image flowspec-tlc:local
flowspec-benchmark --tlc --tlc-logs --tlc-image flowspec-tlc:local
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

Stream TLC logs while debugging a Docker or host JVM run. Add `-o generated-tla` when you also want to inspect the generated `.tla` and copied `.cfg` files:

```sh
flowspec-suite --tlc --tlc-logs -o generated-tla examples/payment.fspec
flowspec-suite --tlc --tlc-backend host --tlc-jar /path/to/tla2tools.jar --tlc-logs -o generated-tla examples/payment.fspec
```

For releases, publish the committed Dockerfile through GitHub Actions to a registry image such as:

```text
ghcr.io/mohamed-elfiky/flowspec-tlc:0.0.1
```

Then users can point FlowSpec at the published image:

```sh
FLOWSPEC_TLC_IMAGE=ghcr.io/mohamed-elfiky/flowspec-tlc:0.0.1 flowspec-suite --tlc
```

Run TLC on the host only when explicitly needed:

```sh
FLOWSPEC_TLC_JAR=/path/to/tla2tools.jar flowspec-suite --tlc --tlc-backend host
```

## VS Code Extension

The local extension lives in [extension/](extension/). It adds `.fspec` highlighting, parser diagnostics, generated TLA+ preview, parse-tree preview, and commands to run the compile/TLC suite.

Launch it for development:

```sh
code extension
```

Then press `F5` and open a `.fspec` file in the Extension Development Host.

Check the extension:

```sh
npm run check --prefix extension
```

Package the extension as a VSIX locally:

```sh
(cd extension && mkdir -p dist && npx --yes @vscode/vsce package --out dist/flowspec-vscode-0.0.1.vsix)
```

The GitHub Actions workflow `Build VS Code Extension` also packages the extension and uploads the `.vsix` as a workflow artifact. Run it manually from the Actions tab, then download the artifact and install it locally:

```sh
code --install-extension flowspec-vscode-0.0.1.vsix
```

See [docs/user-guide.md](docs/user-guide.md) for the DSL guide, [docs/product-direction.md](docs/product-direction.md) for the v0 product boundary, and [docs/ai-authoring-guide.md](docs/ai-authoring-guide.md) for AI-assisted spec writing.
