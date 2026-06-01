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

## Normal User Setup

The extension provides the editor UI. The FlowSpec Python package is the language engine.

For a normal folder such as:

```text
TEST-TLA/
  test.fspec
  test.cfg
```

the extension should automatically recognize `.fspec` files and use the active workspace as the working directory. If `python3` cannot import FlowSpec, configure only the Python executable:

```json
{
  "flowspec.pythonPath": "/path/to/.venv/bin/python"
}
```

Use `flowspec.projectRoot` only when you intentionally want commands to run from a different directory.

## Development

Open the `extension/` folder in VS Code and start an Extension Development Host.

For this repository layout, the extension auto-detects the FlowSpec source tree as the parent directory. If needed, set:

```json
{
  "flowspec.projectRoot": "/path/to/flowspec",
  "flowspec.pythonPath": "/path/to/flowspec/.venv/bin/python"
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

## Package A VSIX

Package locally:

```sh
mkdir -p dist
npx --yes @vscode/vsce package --out dist/flowspec-vscode-0.0.1.vsix
```

The repository workflow `Build VS Code Extension` packages the extension on GitHub Actions. Every run uploads the `.vsix` as an artifact. Tag pushes such as `v0.0.1` also attach the `.vsix` to the GitHub Release. This is for manual installation only; it does not publish to the VS Code Marketplace.

Install a downloaded VSIX:

```sh
code --install-extension flowspec-vscode-0.0.1.vsix
```
