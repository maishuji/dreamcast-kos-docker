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

Choose the script based on what you want to build:

| Script | Purpose | Output image | Default profile |
| --- | --- | --- | --- |
| [`build_dc_toolchain_image.py`](build_dc_toolchain_image.py) | Build the compiler toolchain to use as a base image. | `<username>/dc-chain:<profile>`, or `<username>/dc-chain-gdb:<profile>` with `--use-gdb` | `stable` |
| [`build_dc_kos_full_image.py`](build_dc_kos_full_image.py) | Build the development image with KOS, kos-ports, GLdc, and tools. | `<username>/dc-kos-image:<generated-tag>` | `15.2.1-dev` |

For a development environment, start with the **ready-to-use image** instructions below. Building the toolchain yourself is optional: the full-image script selects `maishuji/dc-chain:15.2.1-dev` by default. Direct Docker builds default to `maishuji/dc-chain:stable`.

### Prerequisites and Python Setup

- Install Python 3.11 or newer, [uv](https://docs.astral.sh/uv/getting-started/installation/), and Docker with a running daemon. `docker info` should succeed for your user. CI uses Python 3.11; CI and the Dockerfiles pin uv to `0.12.11`.
- Allow network access for Python dependencies, Docker images, packages, and source repositories. The full-image script also queries GitHub and GitLab for snapshot choices.
- To build the toolchain from fresh upstream sources (the default), install Git. Alternatively, provide existing sources with `--kos-path`.

Run these commands from the root of this repository:

```sh
uv sync --locked --no-dev
```

Alternatively, run `make create-env`. uv creates `.venv` and installs the build scripts' dependencies from `uv.lock`.

Run scripts with `uv run --locked --no-dev`; no environment activation is required. If you previously activated `venv`, run `deactivate` before using the new setup. The examples below use `yourname` as a placeholder for your Docker username or image namespace.

For development, install the dependencies and the pinned Pylint version, then run lint and tests:

```sh
make create-dev-env
make lint
make test
```

`make create-dev-env` runs `uv sync --locked`, which also installs the `dev` dependency group. `make lint` runs Pylint through `uv run --locked`. `make test` discovers and runs the unit tests in `tests/`; Docker calls are mocked, so no Docker daemon or KallistiOS checkout is needed. CI runs lint and tests as separate jobs on pull requests and pushes to `main`, using the same targets.

Dependencies are declared in `pyproject.toml`, and `uv.lock` pins their resolved versions, including transitive dependencies. Use `uv add <package>` or `uv add --dev <package>` to add dependencies, and commit both files together. The `--locked` flag makes setup fail if the lockfile needs updating; run `uv lock` after editing dependencies manually.

Both scripts create local images. They do not log in to a registry or push images.

### Build a Ready-to-Use Image

Run this script **from the root of this repository**, because it uses `./kos-ready/` as the Docker build context. A local KallistiOS checkout is not required; the Dockerfile clones the sources inside the image.

```sh
# Use the default toolchain profile, 15.2.1-dev.
uv run --locked --no-dev python ./build_dc_kos_full_image.py --username yourname

# Or select a toolchain image tag explicitly.
uv run --locked --no-dev python ./build_dc_kos_full_image.py -u yourname -p 15.2.1-dev

# Optionally select a kos-ports branch and skip its snapshot menu.
uv run --locked --no-dev python ./build_dc_kos_full_image.py -u yourname --kos-ports-branch feature/my-branch
```

| Option | Required | Meaning |
| --- | --- | --- |
| `-u`, `--username` | Yes | Namespace for the resulting `dc-kos-image` image. |
| `-p`, `--profile` | No | Base toolchain image tag; defaults to `15.2.1-dev`. |
| `-g`, `--gdb` | No | Use the `dc-chain-gdb` base image and add `gdb-` after the profile in the output tag. |
| `--kos-ports-branch` | No | kos-ports branch or tag to check out. When omitted, use the interactive snapshot menu. |
| `--help` | No | Display command-line help and exit. |

Enter the **number** beside each choice when prompted:

1. **KOS:** choose `2026`, `2025`, or `master`. Choosing a year fetches matching snapshot tags and prompts you to select one. Choosing `master` skips the snapshot selection.
2. **kos-ports:** choose a year and snapshot, or `master`, in the same way. This step is skipped when `--kos-ports-branch` is supplied.
3. **GLdc:** choose one of the fetched `release/` branches or `master`.
4. **Confirmation:** review the selected versions and the printed Docker command. Enter `1` for **Yes** to build or `2` for **No** to cancel. Cancellation exits with status 1.

The snapshot menus use the forks configured in the script: `maishuji/KallistiOS`, `maishuji/kos-ports`, and `quentin.cartier.dev/GLdc`. The KOS and kos-ports year menus currently list only 2026 and 2025. `master` selects the repository's moving branch, so later builds can use different source revisions.

The script remains interactive for KOS, GLdc, and confirmation. It prints the complete `docker build` command before confirmation; you can save that command to reuse the same selections without the menus.

`--kos-ports-branch` is passed unchanged to the existing Docker build argument `snapshot_kosports`. For a direct build, use `docker build --build-arg snapshot_kosports=feature/my-branch -t yourname/dc-kos-image:custom ./kos-ready/`. Omitting that build argument uses `master`.

**Selecting the base image:** `--profile` is passed as the Docker build argument `dc_chain_version`. The [`kos-ready/Dockerfile`](kos-ready/Dockerfile) uses `FROM maishuji/${base_image}:${dc_chain_version}`, with `base_image=dc-chain` normally or `base_image=dc-chain-gdb` when `--gdb` is supplied. The selected image tag must be available locally or from the registry. `--username` only names the output image; it does not change this base-image namespace.

### Build the Toolchain (Optional)

By default, the toolchain script makes a fresh shallow clone of `https://github.com/KallistiOS/KallistiOS.git` in a temporary directory. It uses the remote's default branch and builds with that checkout's `utils/kos-chain/docker/Dockerfile`, using the same checkout as the Docker build context. The temporary checkout is removed after the build, including on failure. Each invocation needs Git and network access; later invocations can use newer upstream sources.

To use a specific revision, a fork, or local changes, pass `--kos-path /path/to/KallistiOS`. The script uses that directory as-is: it does not fetch updates or modify the checkout. It prints whether it is using fresh or local sources, along with the source path, before building. Docker may still need network access to download images, packages, and compiler sources in either mode.

The selected sources must contain `utils/kos-chain/docker/Dockerfile` and the chosen profile under `utils/kos-chain/profiles`. See the upstream [KOS Toolchain Profiles](https://github.com/KallistiOS/KallistiOS/tree/master/utils/kos-chain/profiles), or the profiles in your local checkout when using `--kos-path`.

From this repository, run:

```sh
# Use the default profile: creates yourname/dc-chain:stable.
uv run --locked --no-dev python ./build_dc_toolchain_image.py --username yourname

# Choose a profile supported by upstream KallistiOS.
uv run --locked --no-dev python ./build_dc_toolchain_image.py -u yourname -p 15.2.1-dev

# Or build from an existing checkout, including any local changes.
uv run --locked --no-dev python ./build_dc_toolchain_image.py -u yourname -p stable --kos-path /opt/toolchains/dc/kos
```

| Option | Required | Meaning |
| --- | --- | --- |
| `-u`, `--username` | Yes | Namespace for the resulting `dc-chain` image. |
| `-p`, `--profile` | No | Toolchain build profile and output image tag; defaults to `stable`. |
| `-g`, `--use-gdb` | No | Include GDB using the upstream `include_gdb=1` build argument; output `<username>/dc-chain-gdb:<profile>`. |
| `--kos-path` | No | Use an existing local KallistiOS source directory instead of a fresh upstream checkout. No updates are fetched. |
| `--help` | No | Display command-line help and exit. |

This script starts the Docker build immediately, without a confirmation prompt. It passes the selected `profile` and a fixed `makejobs=4` to Docker. Without `--use-gdb`, it passes `include_gdb=0` and produces `<username>/dc-chain:<profile>`.

With `--use-gdb`, it passes `include_gdb=1` and builds the toolchain and GDB together in a single image, `<username>/dc-chain-gdb:<profile>`. To also create an image without GDB, run the script separately without the flag. GDB builds require a KallistiOS Dockerfile that declares `ARG include_gdb`; update your checkout if the script reports that this argument is unsupported.

```sh
uv run --locked --no-dev python ./build_dc_toolchain_image.py -u yourname -p stable --use-gdb
```

### Use Your Own Toolchain in the Full Image

To use the toolchain image you built, change the base-image line in [`kos-ready/Dockerfile`](kos-ready/Dockerfile) to your namespace:

```dockerfile
FROM yourname/${base_image}:${dc_chain_version}
```

Then run the full-image script with the same profile used for the toolchain build. For example, after building `yourname/dc-chain:stable`:

```sh
uv run --locked --no-dev python ./build_dc_kos_full_image.py -u yourname -p stable
```

If you also built `yourname/dc-chain-gdb:stable`, add `--gdb` to the full-image command to use it.

The scripts have different defaults, so pass `--profile` explicitly when connecting the two builds. The full-image Dockerfile uses Alpine's `apk` package manager and expects the KOS toolchain layout; a custom base image must remain compatible with those requirements.

### Generated Image Tags

The full-image script generates tags using these rules:

- Start with `<profile>-<kos-snapshot>`, lowercasing the KOS tag. If KOS is `master`, use `<profile>-latest`.
- With `--gdb`, insert `gdb-` immediately after `<profile>-`; for example, `stable-gdb-latest` when KOS is `master`.
- Append `-kp<kos-ports-ref>` in lowercase when kos-ports is not `master`. Characters outside `a-z`, `0-9`, `_`, `.`, and `-` are replaced with `-` in the image tag (for example, `feature/my-branch` becomes `kpfeature-my-branch`); the Git branch or tag itself is passed unchanged.
- Append `-gl<gldc-snapshot>` when GLdc is not `master`, using the last seven characters of the branch name in lowercase (for example, `release/01MAR25` becomes `gl01mar25`).

Examples below illustrate the naming rules; available snapshots depend on the configured repositories:

| Profile | KOS | kos-ports | GLdc | Generated tag |
| --- | --- | --- | --- | --- |
| `15.2.1-dev` | `master` | `master` | `master` | `15.2.1-dev-latest` |
| `15.2.1-dev` | `01MAR25` | `01MAR25` | `release/01MAR25` | `15.2.1-dev-01mar25-kp01mar25-gl01mar25` |
| `stable` | `01MAR25` | `master` | `master` | `stable-01mar25` |
| `15.2.1-dev` | `master` | `feature/my-branch` | `master` | `15.2.1-dev-latest-kpfeature-my-branch` |

### Run the Container

Find the image name and tag after the build:

```sh
docker image ls yourname/dc-kos-image
```

For example, after using profile `15.2.1-dev` and selecting `master` for all three components:

```sh
docker run --rm -it yourname/dc-kos-image:15.2.1-dev-latest bash -l
```

Use the tag from your own build. The login shell (`bash -l`) loads `/etc/profile`, where the Dockerfile sources `/opt/toolchains/dc/kos/environ.sh` to configure the development environment.

Both Dockerfiles include `uv` and `uvx`. The ready-to-use image installs `cpplint` with `uv tool install` for the default non-root user, using Alpine's Python. Run `cpplint --version` to check it.

### Troubleshooting

| Symptom | What to check |
| --- | --- |
| `ModuleNotFoundError` for `click` or `requests` | Run `make create-env` and invoke the script with `uv run --locked --no-dev python`. |
| `uv: command not found` | Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and ensure its installation directory is on `PATH`. |
| Docker is missing or cannot connect to its daemon | Check that Docker is installed, running, and accessible with `docker info`. |
| KallistiOS cloning fails | Check that Git is installed and GitHub is reachable, or supply an existing checkout with `--kos-path`. |
| The local KallistiOS path is invalid or its Dockerfile cannot be read | Check the directory passed to `--kos-path` and ensure it contains `utils/kos-chain/docker/Dockerfile`. Omit the option to clone fresh sources. |
| Docker cannot find the toolchain Dockerfile or profile | Check that your KallistiOS checkout contains the expected `utils/kos-chain/` files. |
| Docker cannot find `./kos-ready/` | Run the full-image script from this repository's root. |
| The base image cannot be found or pulled | Check the profile tag and the `FROM` namespace in `kos-ready/Dockerfile`, especially when using your own toolchain. |
| `apk` reports `DNS: transient error` followed by `openssl-dev (no such package)` | The Alpine package indexes could not be fetched. Package operations retry up to five times, waiting 5, 10, 15, and 20 seconds between attempts. If failures persist, check DNS and repository access from Docker containers, correct Docker's DNS/network configuration, and rerun the build. |
| The full-image script reports `Docker build failed` | Check Docker's output above the message for the failing step. The script exits with an error without a Python traceback. |
| Snapshot retrieval fails or a snapshot menu is empty | Check access to GitHub/GitLab and whether the selected year has tags. If the KOS or kos-ports menu has no choices, press `Ctrl+C` and rerun with a different year or `master`. |

For toolchain builds, check Docker's output and confirm the resulting image with `docker image inspect yourname/dc-chain:stable` (substitute your profile). If the Docker build fails, including while building GDB, the script reports the Docker exit code and exits with a nonzero status.

---

## Limitations

GDB can be included with the flags above. Configuring a debugging session is not covered by these build scripts.
