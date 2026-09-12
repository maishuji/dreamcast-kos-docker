# Image variant decision

## Decision

The packaged `kos-ready` recipe is the supported full development image and
the only full-image variant exposed by `dcdocker build kos-image`.

`kos-alpine/Dockerfile` is retained as a legacy direct-Docker recipe for
existing users. It is not an equivalent alternate implementation of the
ready image, and it is not covered by the installed CLI. It remains in the
source distribution until a later release establishes a removal or migration
path.

## Inventory

| Area | `src/dcdocker/assets/kos-ready` | `kos-alpine` |
| --- | --- | --- |
| Intended use | Supported KOS development image | Legacy direct-build image |
| Base selection | Complete `base_image` reference, including custom registries and digests | `dc_chain_version` tag under the fixed `maishuji` namespace |
| KOS | Requested branch, tag, or full commit, fetched once | Fixed `01FEB25` branch |
| kos-ports | Requested branch, tag, or full commit, with recursive submodules; direct Docker builds temporarily default to `fix/make-build-all-succeed` while its upstream PR is under review | Repository default branch |
| GLdc | Requested branch, tag, or full commit, verified after installation | Makefile rewritten to a fixed `release/07DEC24` branch |
| Ports build | Builds `libGL`, then the configured `build-all.sh` set; removes known broken ports | Builds `libGL` and `libdcplib`; leaves the broad build commented out |
| Additional tools | `mkdcdisc`, SOIL, `dcload-ip`, graphics dependencies, `cpplint`, and source metadata | `mkdcdisc` and the older prerequisite set |
| Environment | Sources KOS environment from `/etc/profile`; exposes user-local `uv` tools | Sources KOS environment from `/etc/profile` only |
| User | Creates and selects `non-root` by default | Creates and selects `non-root` by default |
| Traceability | Embeds source commits and dirty state for metadata collection | No embedded source manifest |
| Resilience | Retries Alpine package installation and validates source checkout refs | No package retry helper or ref validation |

## Expectations and validation path

Consumers needing the current CLI, source pins, metadata, custom bases, or the
documented tool set must use `kos-ready`. Direct users of `kos-alpine` should
expect its fixed snapshots, narrower port set, and lack of provenance. The
legacy recipe must continue to parse and remain buildable enough for a
compatibility release before removal is considered.

Recipe changes after this decision are split into two checks:

1. `kos-ready` receives the normal recipe repairs and real-build checks for
   the supported CLI path.
2. `kos-alpine` receives only compatibility-focused fixes until a migration
   or removal release is approved.

Neither recipe is considered release-validated by unit tests alone. The
release gate requires normal and GDB toolchain builds, a supported full-image
build, and a small KOS compile/link smoke test; Alpine-specific changes also
require a direct Docker build check.
