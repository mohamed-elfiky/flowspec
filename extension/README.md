# FlowSpec VS Code Extension

This extension provides editor support for `.fspec` files.

## Features

- Syntax highlighting for FlowSpec sections, moves, keywords, enums, numbers, and operators
- Completion snippets for sections, moves, bad states, invariants, messages, and `per` state
- Inline parser and semantic diagnostics for `.fspec` files
- Status bar marker: `FlowSpec` appears when a `.fspec` file is active
- Command: `FlowSpec: Validate Current File`
- Command: `FlowSpec: Compile Current File`
- Command: `FlowSpec: Preview Generated TLA+`
- Command: `FlowSpec: Show Parse Tree`
- Command: `FlowSpec: Run Compile Suite`
- Command: `FlowSpec: Run TLC Current File`
- Command: `FlowSpec: Run TLC Suite`

## Development

Open the `extension/` folder in VS Code and start an Extension Development Host.

For this repository layout, the extension auto-detects the FlowSpec project root as the parent directory. If you install or move the extension elsewhere, set:

```json
{
  "flowspec.projectRoot": "/path/to/flowspec"
}
```

Run a quick extension syntax check:

```sh
npm run check --prefix extension
```

## TLC

The TLC commands run the `flowspec.suite` Python module.

When you run `FlowSpec: Run TLC Current File`, the extension executes:

```text
python -m flowspec.suite --tlc --tlc-backend <backend> <active-file.fspec>
```

When you run `FlowSpec: Run TLC Suite`, the extension executes:

```text
python -m flowspec.suite --tlc --tlc-backend <backend>
```

Docker is the default TLC backend. TLC runs inside a container using generated `.tla` and `.cfg` files in a temporary directory. The container is started with no network, a read-only root filesystem, a read-only mounted work directory, and a writable `/tmp`.

Validation uses:

```text
python -m flowspec.compiler --diagnostics-json <active-file.fspec>
```

That means AI-written specs get the same semantic checks in VS Code that the CLI uses.

Build the TLC image first:

```sh
docker build \
  -f docker/tlc/Dockerfile \
  -t flowspec-tlc:local \
  .
```

Then run `FlowSpec: Run TLC Current File` or `FlowSpec: Run TLC Suite` from the command palette.

Relevant settings:

```json
{
  "flowspec.tlcBackend": "docker",
  "flowspec.tlcImage": "ghcr.io/mohamed-elfiky/flowspec-tlc:0.0.1",
  "flowspec.tlcJar": "",
  "flowspec.pythonPath": "",
  "flowspec.projectRoot": "",
  "flowspec.validateOnChange": true
}
```

For released installs, set `flowspec.tlcImage` to the published registry image:

```json
{
  "flowspec.tlcImage": "ghcr.io/mohamed-elfiky/flowspec-tlc:0.0.1"
}
```

Use host Java only when explicitly needed:

```json
{
  "flowspec.tlcBackend": "host",
  "flowspec.tlcJar": "/path/to/tla2tools.jar"
}
```
