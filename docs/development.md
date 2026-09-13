# Development guide

This document contains repository-maintainer instructions. Normal users only
need the [README Quick Start](../README.md#quick-start).

## Development environment

Install Python 3.11 or newer, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and the repository dependencies:

```sh
make create-dev-env
```

This runs `uv sync --locked` and installs the pinned development tools.

## Checks

Run the ordinary local checks with:

```sh
make lint
make test
```

`make lint` runs Ruff's focused correctness checks and Pylint over
`src/dcdocker`, both compatibility scripts, and `tests`. Run `make ruff` for
Ruff alone. `make test` discovers the unit tests; Docker calls are mocked, so
these checks do not need Docker or a KallistiOS checkout.

The opt-in package check builds wheel and source archives, installs them into
isolated environments, and invokes the installed executable outside the
checkout:

```sh
make test-package
```

Provisioning this check may require package-index access. Its runtime checks
use fake Git/Docker commands and controlled discovery responses.

## CI

Pull requests run the same lint and unit-test targets. They also run cheap
Dockerfile parser checks for both image recipes. The [Docker Smoke Checks
workflow](../.github/workflows/docker-smoke.yml) is manual-only: choose one normal or GDB variant,
and optionally rebuild its toolchain from upstream sources. It uses the
published base by default, verifies the expected compiler/tools, compiles the
KOS `examples/dreamcast/hello` target, and uploads only inspection data and
logs. See the [CI validation decision](ci-validation.md) for the rationale.

The smoke workflow is intentionally separate from pull-request checks because
full image builds can take a long time and require substantial network and
Docker storage.

## Project structure

The package separates CLI prompts (`src/dcdocker/cli.py`), build specifications
and planning (`builds.py`), source discovery and checkout ownership
(`sources.py`), Docker commands (`docker.py`), source observations and metadata
(`provenance.py`), and Python defaults (`defaults.py`).

The canonical ready-image recipe and helpers live in
[`src/dcdocker/assets/kos-ready/`](../src/dcdocker/assets/kos-ready/). They are
included in the package and copied to a temporary context for each full-image
invocation. That context remains available during Docker execution and is
removed after success, failure, cancellation, or interruption.

Dependencies are declared in `pyproject.toml`, and `uv.lock` pins their
resolved versions. Use `uv add <package>` or `uv add --dev <package>` to add
dependencies, and commit both files together. The `--locked` flag makes setup
fail if the lockfile needs updating.
