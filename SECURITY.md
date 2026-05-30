# Security

FlowSpec executes local tools when compiling specs and running TLC.

Default TLC execution uses Docker with:

- no network
- read-only root filesystem
- read-only mounted generated specs
- writable `/tmp`

Do not run untrusted `.fspec` specs with host TLC unless you understand the local environment and model configuration.

Report security issues privately once a public maintainer contact exists. Until then, do not disclose exploitable issues in public issue trackers.
