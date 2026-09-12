# Dreamcast KOS Docker Image

## Introduction

This repository provides tools for creating a ready-to-use Docker image for Dreamcast programming. The image can be used to set up a development container with VS Code ([Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers)) and simplifies the configuration of the development environment.

## Components

The Docker image includes several key components:

- **dc-chain**: The toolchain. A Dockerfile exists in the KOS repository to build a Docker image.
  - [KallistiOS dc-chain Dockerfile](https://github.com/KallistiOS/KallistiOS/blob/master/utils/kos-chain/docker/Dockerfile)
- **KallistiOS (KOS)**: The Dreamcast SDK.
  - [KallistiOS GitHub](https://github.com/KallistiOS)
- **kos-ports**: Libraries ported for KOS on the Sega Dreamcast.
  - [kos-ports GitHub](https://github.com/KallistiOS/kos-ports)
- **mkdcdisc**: A tool to create a CDI image.
  - [mkdcdisc GitLab](https://gitlab.com/simulant/mkdcdisc)

*Note:* The repositories used in the Dockerfiles are forks of the original repositories listed above, as release tags are required to select specific snapshots.

---

## How to Use

Use `dcdocker build` to choose what to build:

| Command | Purpose | Output image | Default profile/tag |
| --- | --- | --- | --- |
| `dcdocker build dc-chain` | Build the compiler toolchain. | `<namespace>/dc-chain:<profile>`, or `<namespace>/dc-chain-gdb:<profile>` with `--gdb` | `16.2.0` |
| `dcdocker build kos-image` | Build the development image with KOS, kos-ports, GLdc, and tools. | `<namespace>/dc-kos-image:<generated-tag>` | `16.2.0` |

For a development environment, start with the **ready-to-use image** instructions below. Building the toolchain yourself is optional: the full-image build uses `maishuji/dc-chain:16.2.0` (or `maishuji/dc-chain-gdb:16.2.0` with `--gdb`).

### Prerequisites and Python Setup

- Install Python 3.11 or newer, [uv](https://docs.astral.sh/uv/getting-started/installation/), and Docker with a running daemon. `docker info` should succeed for your user. CI runs unit/lint checks on Python 3.11 and package checks on Python 3.11 and 3.13; CI and the Dockerfiles pin uv to `0.12.11`.
- Allow network access for Python dependencies, Docker images, packages, and source repositories. The full-image command also queries GitHub and GitLab for snapshot choices.
- To build the toolchain from fresh upstream sources (the default), install Git. Alternatively, provide existing sources with `--kos-path`.

Run these commands from the root of this repository:

```sh
uv sync --locked --no-dev
```

Alternatively, run `make create-env`. uv creates `.venv`, installs dependencies from `uv.lock`, and installs the project in editable mode. Run this setup again after upgrading from the standalone scripts.

From the checkout, run the installed command through uv:

```sh
uv run --locked --no-dev dcdocker --help
uv run --locked --no-dev dcdocker build --help
uv run --locked --no-dev dcdocker build dc-chain --help
uv run --locked --no-dev dcdocker build kos-image --help
```

For a separate local tool installation, run `uv tool install .` from this repository. Ensure uv's tool binary directory is on `PATH` (use `uv tool update-shell` if needed), then run `dcdocker` from any directory. This installation includes the Docker context and does not require a source checkout at runtime. Reinstall with `uv tool install --reinstall .` after changing the local source or recipe. `python -m dcdocker` also works in an environment where the package is installed.

The examples below use `uv run --locked --no-dev dcdocker` from the checkout. With a tool installation, use `dcdocker` directly with the same arguments. `yourname` is a placeholder for your Docker image namespace.

For development, install the dependencies and the pinned Pylint version, then run lint and tests:

```sh
make create-dev-env
make lint
make test
make test-package
```

`make create-dev-env` runs `uv sync --locked`, which also installs the `dev` dependency group. `make lint` runs Pylint over `src/dcdocker`, both compatibility scripts, and `tests` through `uv run --locked`. `make test` discovers and runs the unit tests in `tests/`; Docker calls are mocked, so no Docker daemon or KallistiOS checkout is needed. CI runs lint and tests as separate jobs on pull requests and pushes to `main`, using the same targets.

`make test-package` builds a wheel and source archive, rebuilds a wheel from that archive, installs both into isolated environments, and checks the installed executable outside the checkout. Provisioning may require package-index access; runtime checks use fake Git/Docker commands and controlled discovery responses. CI runs these package checks on Python 3.11 and 3.13. The ordinary `make test` suite skips the opt-in package test.

The package separates CLI prompts (`cli.py`), build specifications and planning (`builds.py`), source discovery and checkout ownership (`sources.py`), Docker commands (`docker.py`), and Python defaults (`defaults.py`). The canonical ready-image recipe and helper live in [`src/dcdocker/assets/kos-ready/`](src/dcdocker/assets/kos-ready/). They are included in the package and copied to a temporary context for each full-image invocation. That context stays available during Docker execution and is removed after success, failure, cancellation, or interruption.

Dependencies are declared in `pyproject.toml`, and `uv.lock` pins their resolved versions, including transitive dependencies. Use `uv add <package>` or `uv add --dev <package>` to add dependencies, and commit both files together. The `--locked` flag makes setup fail if the lockfile needs updating; run `uv lock` after editing dependencies manually.

Both build commands create local images. They do not log in to a registry or push images.

### Build a Ready-to-Use Image

The command uses its packaged Docker context from any working directory. A local KallistiOS checkout is not required; the Dockerfile clones the sources inside the image.

```sh
# Interactive source selection in a terminal; default toolchain tag 16.2.0.
uv run --locked --no-dev dcdocker build kos-image --namespace yourname

# Or select a toolchain image tag explicitly.
uv run --locked --no-dev dcdocker build kos-image -u yourname --toolchain-tag 16.2.0

# Optionally select a kos-ports branch and skip its snapshot menu.
uv run --locked --no-dev dcdocker build kos-image -u yourname --kos-ports-ref feature/my-branch
```

| Option | Required | Meaning |
| --- | --- | --- |
| `-u`, `--namespace`, `--username` | Yes | Namespace for the resulting `dc-kos-image` image. |
| `--toolchain-tag`, `-p`, `--profile` | No | Base toolchain image tag; defaults to `16.2.0`. |
| `-g`, `--gdb` | No | Use the `dc-chain-gdb` base image and add `gdb-` after the profile in the output tag. |
| `--kos-ref` | For automation | KOS branch or tag; skips its source menu and discovery request. |
| `--kos-ports-ref`, `--kos-ports-branch` | For automation | kos-ports branch or tag; skips its source menu and discovery request. |
| `--gldc-ref` | For automation | GLdc branch or tag; skips its source menu and discovery request. |
| `--base-image` | No | Complete base reference, including registry/port, tag or digest. Conflicts with an explicitly supplied `--toolchain-tag`, `--profile`, or `-p`. |
| `--image-tag` | For untagged/digest-only custom bases | Output tag override; independent of the base tag. |
| `--non-interactive` | No | Require all three refs and execute without reading stdin or confirming. |
| `--yes` | No | Skip final confirmation only; missing refs still require terminal menus. |
| `--dry-run` | No | Offline preview requiring all three refs; no prompts, HTTP, Git, Docker, or temporary context. |
| `--help` | No | Display command-line help and exit. |

For a fully specified build from a terminal or CI:

```sh
uv run --locked --no-dev dcdocker build kos-image --namespace yourname \
  --kos-ref master --kos-ports-ref master --gldc-ref master --non-interactive

# Preview the same build without contacting GitHub, GitLab or Docker.
uv run --locked --no-dev dcdocker build kos-image --namespace yourname \
  --kos-ref master --kos-ports-ref master --gldc-ref master --dry-run
```

Explicit refs bypass their discovery requests. Execution may still need network access for Git clones inside Docker, packages, and base images. Refs initially support branches/tags containing ASCII letters, digits, dots, underscores, slashes and hyphens. They must start with a letter, digit or underscore and cannot contain empty/dot-prefixed components, `..`, a trailing dot, or `.lock` component suffixes. Arbitrary commit checkout is not implemented: a commit hash is not an immutable-source guarantee with the current branch/tag recipe.

Enter the **number** beside each choice when prompted:

1. **KOS:** the command fetches available tags, then offers their snapshot years (newest first) and `master (branch)`. Choose a year and snapshot tag, or explicitly select the moving `master` branch.
2. **kos-ports:** choose a discovered year and snapshot tag, or `master (branch)`, in the same way. This step is skipped when `--kos-ports-branch` is supplied.
3. **GLdc:** choose one of the fetched `release/` branches or `master`.
4. **Confirmation:** review the selected versions and the printed Docker command. Enter `1` for **Yes** to build or `2` for **No** to cancel. Cancellation exits with status 1.

The snapshot menus use the forks configured in [`src/dcdocker/defaults.py`](src/dcdocker/defaults.py): `maishuji/KallistiOS`, `maishuji/kos-ports`, and `quentin.cartier.dev/GLdc`. Years come from uppercase `DDMONYY` tags, interpreting `YY` as 2000–2099; unrelated tag names do not create year choices. An empty tag catalog offers only the explicit `master (branch)` choice. GLdc lists only discovered `release/` and `master` branches. `master` selects the repository's moving branch, so later builds can use different source revisions.

On a terminal, only omitted refs are prompted for. Without a terminal, all three refs are required, plus `--non-interactive` or `--yes` to execute. `--yes` skips confirmation but does not choose missing refs. Dry-run always requires explicit refs and performs no source discovery or external execution, even on a terminal.

The printed Docker command uses an owned context that is removed after execution. Dry-run displays `<packaged-context>` or `<fresh-kos>` placeholders instead of creating directories. It reports unresolved commits and unverified base/source availability; it cannot prove that a build will succeed. Repeat builds through the CLI or use the direct-Docker recipe path below.

If discovery fails, the script reports the affected source and the connection, timeout, HTTP, or response-format problem and exits with status 1. A GLdc lookup with no matching branches also exits clearly. Discovery never silently selects `master` after a failure. Each catalog is fetched once per selection, with pages of up to 100 refs and a limit of 20 pages. GitHub Link and GitLab pagination headers are supported; full pages without headers trigger another page request. Duplicate refs are deduplicated, while repeated pages, invalid pagination and exhausted limits fail instead of offering incomplete results. Requests use a 30-second timeout; rate-limit responses (403/429) fail immediately without automatic retries or sleeps. Supply explicit refs to bypass discovery. EOF or Ctrl-C aborts without starting a build when entered at a prompt. Missing build-context files or Docker produce an actionable error instead of a traceback.

`--kos-ports-branch` is passed unchanged to the existing Docker build argument `snapshot_kosports`. For a direct build, use `docker build --build-arg snapshot_kosports=feature/my-branch -t yourname/dc-kos-image:custom ./src/dcdocker/assets/kos-ready/`. Omitting that build argument uses `master`.

**Selecting the base image:** the CLI resolves the default to `maishuji/dc-chain:<toolchain-tag>` or `maishuji/dc-chain-gdb:<toolchain-tag>` and passes that complete reference as Docker's `base_image` argument. The [Dockerfile](src/dcdocker/assets/kos-ready/Dockerfile) now uses `ARG base_image=maishuji/dc-chain:16.2.0` and `FROM ${base_image}`. Its old `dc_chain_version` argument has been removed. `--namespace` names only the output image.

For direct Docker builds, use a complete base reference:

```sh
docker build --build-arg base_image=yourname/dc-chain:16.2.0 \
  --build-arg snapshot_kos=master --build-arg snapshot_kosports=master \
  --build-arg snapshot_gldc=master -t yourname/dc-kos-image:custom \
  ./src/dcdocker/assets/kos-ready/
```

### Build the Toolchain (Optional)

By default, the toolchain command makes a fresh shallow clone of `https://github.com/KallistiOS/KallistiOS.git` in a temporary directory. It uses the remote's default branch and builds with that checkout's `utils/kos-chain/docker/Dockerfile`, using the same checkout as the Docker build context. The temporary checkout is removed after the build, including on failure. Each invocation needs Git and network access; later invocations can use newer upstream sources.

To use a specific revision, a fork, or local changes, pass `--kos-path /path/to/KallistiOS`. The command uses that directory as-is: it does not fetch updates or modify the checkout. It prints whether it is using fresh or local sources, along with the source path, before building. Docker may still need network access to download images, packages, and compiler sources in either mode.

The selected sources must contain `utils/kos-chain/docker/Dockerfile` and the chosen profile under `utils/kos-chain/profiles/dreamcast`. See the upstream [KOS Toolchain Profiles](https://github.com/KallistiOS/KallistiOS/tree/master/utils/kos-chain/profiles/dreamcast), or the profiles in your local checkout when using `--kos-path`.

`--profile` has two related roles: the toolchain command selects a source profile (the `.mk` filename without its extension) and uses that name as the output tag; the full-image command selects an already-built Docker image tag. A profile existing upstream does not guarantee that a matching image is published. The default `16.2.0` is available as an upstream profile and as the published `maishuji/dc-chain:16.2.0` image.

The upstream `stable` profile is also valid, but its compiler selection can change over time; build and provide an image tagged `stable` before using it in the full-image command. For GDB builds, provide the matching `dc-chain-gdb:<profile>` image locally or in the registry. If it is unavailable, build it with `--use-gdb` and follow **Use Your Own Toolchain in the Full Image** below.

From this repository, run:

```sh
# Use the default profile: creates yourname/dc-chain:16.2.0.
uv run --locked --no-dev dcdocker build dc-chain --namespace yourname

# Choose a profile supported by upstream KallistiOS.
uv run --locked --no-dev dcdocker build dc-chain -u yourname -p 16.2.0

# Or build from an existing checkout, including any local changes.
uv run --locked --no-dev dcdocker build dc-chain -u yourname -p 16.2.0 --kos-path /opt/toolchains/dc/kos
```

| Option | Required | Meaning |
| --- | --- | --- |
| `-u`, `--namespace`, `--username` | Yes | Namespace for the resulting `dc-chain` image. |
| `-p`, `--profile` | No | Toolchain build profile and output image tag; defaults to `16.2.0`. |
| `-g`, `--gdb`, `--use-gdb` | No | Include GDB using the upstream `include_gdb=1` build argument; output `<username>/dc-chain-gdb:<profile>`. |
| `--kos-path` | No | Use an existing local KallistiOS source directory instead of a fresh upstream checkout. No updates are fetched. |
| `--image-tag` | No | Override the output tag while keeping the selected source profile. |
| `--non-interactive` | No | Explicitly request execution without stdin (toolchain builds already have no menus). |
| `--dry-run` | No | Print inputs and planned clone/build commands without executing them. |
| `--help` | No | Display command-line help and exit. |

Unless `--dry-run` is supplied, this command starts the Docker build immediately, without a confirmation prompt. Before Docker runs, it checks that the selected `profiles/dreamcast/<profile>.mk` is readable and the Dockerfile declares `ARG profile`. Custom local profiles are supported. It passes `makejobs=4` only when the Dockerfile declares that argument; otherwise it reports that upstream concurrency defaults apply. Without `--use-gdb`, it passes `include_gdb=0` only when declared and produces `<username>/dc-chain:<profile>`.

With `--use-gdb`, it passes `include_gdb=1` and builds the toolchain and GDB together in a single image, `<username>/dc-chain-gdb:<profile>`. To also create an image without GDB, run the command separately without the flag. GDB builds require a KallistiOS Dockerfile that declares `ARG include_gdb`; update your checkout if the command reports that this argument is unsupported. Declaration checks support instruction case, whitespace, quoted defaults and line continuations, and ignore comments and shell heredoc contents. These checks establish the declared interface, not whether the recipe correctly uses each argument. Dry-run does not read the checkout and shows optional arguments as conditional on these checks.

```sh
uv run --locked --no-dev dcdocker build dc-chain -u yourname -p 16.2.0 --gdb

# Offline preview; output tag differs from the selected profile.
uv run --locked --no-dev dcdocker build dc-chain -u yourname -p 16.2.0 \
  --image-tag my-toolchain --dry-run
```

### Use Your Own Toolchain in the Full Image

Use `--base-image` with the complete reference; no Dockerfile edit is needed:

```sh
uv run --locked --no-dev dcdocker build kos-image --namespace yourname \
  --base-image yourname/dc-chain:16.2.0 \
  --kos-ref master --kos-ports-ref master --gldc-ref master --non-interactive

uv run --locked --no-dev dcdocker build kos-image --namespace yourname \
  --base-image registry.example:5000/team/dc-chain-gdb:16.2.0 --gdb \
  --image-tag my-development-image \
  --kos-ref master --kos-ports-ref master --gldc-ref master --non-interactive
```

Custom bases may use a registry port, tag, or complete SHA-256/SHA-384/SHA-512 digest. An untagged or digest-only reference requires `--image-tag`. A custom reference containing a tag can supply the generated output tag prefix. Do not combine `--base-image` with an explicit `--toolchain-tag` or its legacy aliases; the implicit default is not a conflict.

`--base-image` is authoritative. Adding `--gdb` affects generated output naming but does not rewrite the custom base or verify its contents. The full-image recipe still requires an Alpine-compatible base and the KOS toolchain layout.

The alternative [`kos-alpine/Dockerfile`](kos-alpine/Dockerfile) also defaults to `dc_chain_version=16.2.0`; override it with `--build-arg dc_chain_version=<tag>` when building that Dockerfile directly.

### Generated Image Tags

The full-image command keeps the existing names for `master`, uppercase `DDMONYY` snapshots, and GLdc `release/DDMONYY` branches. It starts with the selected base tag, adds `gdb-` when requested, and uses `latest` for KOS `master`. Non-master ports and GLdc refs add `-kp` and `-gl` components.

For other branch/tag combinations, refs are lowercased and unsupported tag characters such as `/` become `-`. A final `-r<12-hex>` SHA-256 discriminator derived from the three original refs distinguishes case changes and normalization collisions. This deliberately changes generated names for arbitrary branches; date snapshots and all-master names stay unchanged. The discriminator identifies requested names, not resolved commits.

| Base tag | KOS | kos-ports | GLdc | Generated output tag |
| --- | --- | --- | --- | --- |
| `16.2.0` | `master` | `master` | `master` | `16.2.0-latest` |
| `16.2.0` | `01MAR25` | `01MAR25` | `release/01MAR25` | `16.2.0-01mar25-kp01mar25-gl01mar25` |
| `16.2.0` | `master` | `feature/my-branch` | `master` | `16.2.0-latest-kpfeature-my-branch-rc8a522861d62` |

`--image-tag` replaces the entire generated tag. Tags use 1–128 ASCII letters, digits, underscores, dots or hyphens and must begin with a letter, digit or underscore. Oversized generated tags fail with guidance to set `--image-tag`; refs are never truncated for checkout. See [Docker image reference documentation](https://docs.docker.com/reference/cli/docker/image/tag/) for registry and repository naming.

### Run the Container

Find the image name and tag after the build:

```sh
docker image ls yourname/dc-kos-image
```

For example, after using profile `16.2.0` and selecting `master` for all three components:

```sh
docker run --rm -it yourname/dc-kos-image:16.2.0-latest bash -l
```

Use the tag from your own build. The login shell (`bash -l`) loads `/etc/profile`, where the Dockerfile sources `/opt/toolchains/dc/kos/environ.sh` to configure the development environment.

Both Dockerfiles include `uv` and `uvx`. The ready-to-use image installs `cpplint` with `uv tool install` for the default non-root user, using Alpine's Python. Run `cpplint --version` to check it.

### Troubleshooting

| Symptom | What to check |
| --- | --- |
| `ModuleNotFoundError` for `dcdocker`, `click`, or `requests` | Run `make create-env` and use `uv run --locked --no-dev dcdocker`, or reinstall the local tool. |
| `dcdocker: command not found` | Run `uv sync --locked` in the checkout or `uv tool install .`; ensure the chosen installation’s binary directory is on `PATH`. |
| `uv: command not found` | Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and ensure its installation directory is on `PATH`. |
| Docker is missing or cannot connect to its daemon | Check that Docker is installed, running, and accessible with `docker info`. |
| KallistiOS cloning fails | Check that Git is installed and GitHub is reachable, or supply an existing checkout with `--kos-path`. |
| The local KallistiOS path is invalid or its Dockerfile cannot be read | Check the directory passed to `--kos-path` and ensure it contains `utils/kos-chain/docker/Dockerfile`. Omit the option to clone fresh sources. |
| The selected profile is missing or `ARG profile` is unsupported | Check `utils/kos-chain/profiles/dreamcast/<profile>.mk` and the Dockerfile in the selected checkout. Use a compatible checkout or choose one of its profiles. |
| Packaged build assets cannot be prepared | Reinstall the package and check temporary-directory access. For direct Docker builds, use `src/dcdocker/assets/kos-ready/` from the checkout root. |
| The base image cannot be found or pulled | Check `--toolchain-tag` or the complete `--base-image` reference and registry access. |
| `Explicit source refs required` | Supply all three refs for non-terminal builds and dry-run. Use `--non-interactive` or `--yes` to authorize execution without confirmation. |
| `apk` reports `DNS: transient error` followed by `openssl-dev (no such package)` | The Alpine package indexes could not be fetched. Package operations retry up to five times, waiting 5, 10, 15, and 20 seconds between attempts. If failures persist, check DNS and repository access from Docker containers, correct Docker's DNS/network configuration, and rerun the build. |
| The full-image command reports `Docker build failed` | Check Docker's output above the message for the failing step. The script exits with an error without a Python traceback. |
| Snapshot retrieval fails or reaches its pagination limit | Check GitHub/GitLab access and rate limits, or supply all three source refs explicitly. Discovery errors never select `master` automatically. |

For toolchain builds, check Docker's output and confirm the resulting image with `docker image inspect yourname/dc-chain:16.2.0` (substitute your profile). If the Docker build fails, including while building GDB, the script reports the Docker exit code and exits with a nonzero status.

### Migrating from the Python scripts

Both script filenames remain available as compatibility entry points and print one migration notice to stderr when executed. Their original option spellings remain accepted through the same implementation. Interactive menus require a terminal; piped/CI invocations must now provide explicit refs and confirmation controls. They will remain for at least one release with the new CLI; a removal release has not yet been selected.

| Previous invocation or option | Preferred equivalent |
| --- | --- |
| `python build_dc_toolchain_image.py` | `dcdocker build dc-chain` |
| `python build_dc_kos_full_image.py` | `dcdocker build kos-image` |
| `--username` / `-u` | `--namespace` / `-u` |
| Toolchain `--use-gdb` | `--gdb` |
| Full-image `--profile` / `-p` | `--toolchain-tag` |
| `--kos-ports-branch` | `--kos-ports-ref` |
| Direct Docker context `./kos-ready/` | `./src/dcdocker/assets/kos-ready/` |
| Docker arguments `base_image=dc-chain`, `dc_chain_version=16.2.0` | `base_image=maishuji/dc-chain:16.2.0` |

Old option spellings also work with the installed commands. The default base remains under `maishuji`; use `--base-image` to override it. The output namespace does not change the base. To customize the recipe, edit the canonical asset in a source checkout and use the editable installation or rebuild the tool installation. The old top-level `kos-ready/` directory has been removed.

---

## Limitations

GDB can be included with the flags above. Configuring a debugging session is not covered by these build scripts.
