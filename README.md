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
# Use the default toolchain profile, 16.2.0.
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
| `--kos-ports-ref`, `--kos-ports-branch` | No | kos-ports branch or tag to check out. When omitted, use the interactive snapshot menu. |
| `--help` | No | Display command-line help and exit. |

Enter the **number** beside each choice when prompted:

1. **KOS:** choose `2026`, `2025`, or `master`. Choosing a year fetches matching snapshot tags and prompts you to select one. Choosing `master` skips the snapshot selection.
2. **kos-ports:** choose a year and snapshot, or `master`, in the same way. This step is skipped when `--kos-ports-branch` is supplied.
3. **GLdc:** choose one of the fetched `release/` branches or `master`.
4. **Confirmation:** review the selected versions and the printed Docker command. Enter `1` for **Yes** to build or `2` for **No** to cancel. Cancellation exits with status 1.

The snapshot menus use the forks configured in [`src/dcdocker/defaults.py`](src/dcdocker/defaults.py): `maishuji/KallistiOS`, `maishuji/kos-ports`, and `quentin.cartier.dev/GLdc`. The KOS and kos-ports year menus currently list only 2026 and 2025. `master` selects the repository's moving branch, so later builds can use different source revisions.

The full-image command remains interactive for KOS, GLdc, and confirmation. Explicit KOS/GLdc refs, noninteractive mode, dry-run, and a complete custom base-image option are planned for the next phase. The printed Docker command contains a temporary context path that is removed after this invocation; repeat builds through the CLI or use the direct-Docker recipe path below.

If discovery fails, the script reports the affected source and the connection, timeout, HTTP, or response-format problem and exits with status 1. A successful lookup with no matching choices also exits clearly; rerun with another selection or check the source repository. EOF or Ctrl-C aborts without starting a build when entered at a prompt. Missing build-context files or Docker produce an actionable error instead of a traceback.

`--kos-ports-branch` is passed unchanged to the existing Docker build argument `snapshot_kosports`. For a direct build, use `docker build --build-arg snapshot_kosports=feature/my-branch -t yourname/dc-kos-image:custom ./src/dcdocker/assets/kos-ready/`. Omitting that build argument uses `master`.

**Selecting the base image:** `--toolchain-tag` (or its legacy alias `--profile`) is passed as the Docker build argument `dc_chain_version`. The [`src/dcdocker/assets/kos-ready/Dockerfile`](src/dcdocker/assets/kos-ready/Dockerfile) uses `FROM maishuji/${base_image}:${dc_chain_version}`, with `base_image=dc-chain` normally or `base_image=dc-chain-gdb` when `--gdb` is supplied. The selected image tag must be available locally or from the registry. `--namespace` only names the output image; it does not change this base-image namespace.

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
| `--help` | No | Display command-line help and exit. |

This command starts the Docker build immediately, without a confirmation prompt. It passes the selected `profile` and a fixed `makejobs=4` to Docker. Without `--use-gdb`, it passes `include_gdb=0` and produces `<username>/dc-chain:<profile>`.

With `--use-gdb`, it passes `include_gdb=1` and builds the toolchain and GDB together in a single image, `<username>/dc-chain-gdb:<profile>`. To also create an image without GDB, run the command separately without the flag. GDB builds require a KallistiOS Dockerfile that declares `ARG include_gdb`; update your checkout if the script reports that this argument is unsupported.

```sh
uv run --locked --no-dev dcdocker build dc-chain -u yourname -p 16.2.0 --gdb
```

### Use Your Own Toolchain in the Full Image

To use the toolchain image you built, change the base-image line in [`src/dcdocker/assets/kos-ready/Dockerfile`](src/dcdocker/assets/kos-ready/Dockerfile) to your namespace:

```dockerfile
FROM yourname/${base_image}:${dc_chain_version}
```

Then run the full-image command with the same profile used for the toolchain build. For example, after building `yourname/dc-chain:16.2.0`:

```sh
uv run --locked --no-dev dcdocker build kos-image -u yourname --toolchain-tag 16.2.0
```

If you also built `yourname/dc-chain-gdb:16.2.0`, add `--gdb` to the full-image command to use it.

Both commands default to `16.2.0`. If you choose another profile, pass it as `--profile` to `build dc-chain` and `--toolchain-tag` to `build kos-image`. The full-image Dockerfile uses Alpine's `apk` package manager and expects the KOS toolchain layout; a custom base image must remain compatible with those requirements.

The alternative [`kos-alpine/Dockerfile`](kos-alpine/Dockerfile) also defaults to `dc_chain_version=16.2.0`; override it with `--build-arg dc_chain_version=<tag>` when building that Dockerfile directly.

### Generated Image Tags

The full-image command generates tags using these rules:

- Start with `<profile>-<kos-snapshot>`, lowercasing the KOS tag. If KOS is `master`, use `<profile>-latest`.
- With `--gdb`, insert `gdb-` immediately after `<profile>-`; for example, `16.2.0-gdb-latest` when KOS is `master`.
- Append `-kp<kos-ports-ref>` in lowercase when kos-ports is not `master`. Characters outside `a-z`, `0-9`, `_`, `.`, and `-` are replaced with `-` in the image tag (for example, `feature/my-branch` becomes `kpfeature-my-branch`); the Git branch or tag itself is passed unchanged.
- Append `-gl<gldc-snapshot>` when GLdc is not `master`, using the last seven characters of the branch name in lowercase (for example, `release/01MAR25` becomes `gl01mar25`).

Examples below illustrate the naming rules; available snapshots depend on the configured repositories:

| Profile | KOS | kos-ports | GLdc | Generated tag |
| --- | --- | --- | --- | --- |
| `16.2.0` | `master` | `master` | `master` | `16.2.0-latest` |
| `16.2.0` | `01MAR25` | `01MAR25` | `release/01MAR25` | `16.2.0-01mar25-kp01mar25-gl01mar25` |
| `16.2.0` | `01MAR25` | `master` | `master` | `16.2.0-01mar25` |
| `16.2.0` | `master` | `feature/my-branch` | `master` | `16.2.0-latest-kpfeature-my-branch` |

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
| Docker cannot find the toolchain Dockerfile or profile | Check that your KallistiOS checkout contains the expected `utils/kos-chain/` files. |
| Packaged build assets cannot be prepared | Reinstall the package and check temporary-directory access. For direct Docker builds, use `src/dcdocker/assets/kos-ready/` from the checkout root. |
| The base image cannot be found or pulled | Check the profile tag and the `FROM` namespace in `src/dcdocker/assets/kos-ready/Dockerfile`, especially when using your own toolchain. |
| `apk` reports `DNS: transient error` followed by `openssl-dev (no such package)` | The Alpine package indexes could not be fetched. Package operations retry up to five times, waiting 5, 10, 15, and 20 seconds between attempts. If failures persist, check DNS and repository access from Docker containers, correct Docker's DNS/network configuration, and rerun the build. |
| The full-image command reports `Docker build failed` | Check Docker's output above the message for the failing step. The script exits with an error without a Python traceback. |
| Snapshot retrieval fails or a snapshot menu is empty | Check access to GitHub/GitLab and whether the selected year has tags. Empty menus exit automatically; rerun with a different year or `master`. |

For toolchain builds, check Docker's output and confirm the resulting image with `docker image inspect yourname/dc-chain:16.2.0` (substitute your profile). If the Docker build fails, including while building GDB, the script reports the Docker exit code and exits with a nonzero status.

### Migrating from the Python scripts

Both script filenames remain available as compatibility entry points and print one migration notice to stderr when executed. Their original options and interactive behavior are preserved through the same command implementation. They will remain for at least one release with the new CLI; a removal release has not yet been selected.

| Previous invocation or option | Preferred equivalent |
| --- | --- |
| `python build_dc_toolchain_image.py` | `dcdocker build dc-chain` |
| `python build_dc_kos_full_image.py` | `dcdocker build kos-image` |
| `--username` / `-u` | `--namespace` / `-u` |
| Toolchain `--use-gdb` | `--gdb` |
| Full-image `--profile` / `-p` | `--toolchain-tag` |
| `--kos-ports-branch` | `--kos-ports-ref` |
| Direct Docker context `./kos-ready/` | `./src/dcdocker/assets/kos-ready/` |

Old option spellings also work with the installed commands. The full-image base remains under the `maishuji` namespace; the output namespace does not change it. To customize the recipe, edit the canonical asset in a source checkout and use the editable installation or rebuild the tool installation. The old top-level `kos-ready/` directory has been removed.

---

## Limitations

GDB can be included with the flags above. Configuring a debugging session is not covered by these build scripts.
