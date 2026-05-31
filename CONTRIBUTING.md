# Contributing

FlowSpec v0 is focused on complex business workflows, not research distributed systems.

Good contributions improve:

- readable business-state syntax
- semantic diagnostics
- generated TLA+ quality
- TLC runner ergonomics
- VS Code extension workflow
- examples for practical business domains

Before opening a PR, run:

```sh
flowspec-suite
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m py_compile flowspec/compiler.py flowspec/cli.py flowspec/suite.py
npm run check --prefix extension
```

If your change touches the grammar, update:

- `grammar.lark`
- `docs/user-guide.md`
- at least one example under `examples/`

Avoid adding language features for Paxos/Raft/consensus unless the change also clearly improves everyday business workflow modeling.
