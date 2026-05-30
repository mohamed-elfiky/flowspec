# TLC Docker Image

This image packages `tla2tools.jar` so TLC runs isolated from the host.

The image definition is committed in this repo. The image layers themselves should not be committed to git; publish them to a registry with a version tag.

## Local Build

Build the local development image:

```sh
docker build \
  -f docker/tlc/Dockerfile \
  -t flowspec-tlc:local \
  .
```

Then run the supported FlowSpec suite with TLC inside Docker:

```sh
flowspec-suite --tlc
```

The suite runs containers with:

- no network
- read-only filesystem
- read-only mounted generated `.tla` and `.cfg` files
- temporary writable `/tmp`

Host Java remains available only as an explicit fallback:

```sh
FLOWSPEC_TLC_JAR=/path/to/tla2tools.jar flowspec-suite --tlc --tlc-backend host
```

## Published Image

The publish workflow lives at `.github/workflows/publish-tlc-image.yml`.

When the repo is on GitHub, publish the image by pushing a version tag:

```sh
git tag v0.0.1
git push origin v0.0.1
```

The workflow publishes:

```text
ghcr.io/mohamed-elfiky/flowspec-tlc:0.0.1
ghcr.io/mohamed-elfiky/flowspec-tlc:sha-<commit>
ghcr.io/mohamed-elfiky/flowspec-tlc:latest
```

Users can run the suite with a published image:

```sh
FLOWSPEC_TLC_IMAGE=ghcr.io/mohamed-elfiky/flowspec-tlc:0.0.1 flowspec-suite --tlc
```

The image version is tracked in `docker/tlc/VERSION`.
