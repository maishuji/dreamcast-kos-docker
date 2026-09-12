# CI validation decision

## Decision

Routine CI is intentionally cheap. Pull requests and pushes to `main` run
unit tests, lint, package checks, and Dockerfile parser checks only. They do
not build the KallistiOS toolchain or the multi-gigabyte development image.

Full Docker validation is separated into the manual
[`Docker Smoke Checks workflow`](../.github/workflows/docker-smoke.yml). It
validates one normal or GDB variant at a time and uses the published
toolchain base by default. Rebuilding the toolchain from upstream sources is
an explicit workflow input for release or investigation work.

## Rationale

Toolchain and ready-image builds are integration tests, not suitable per-PR
checks: they depend on several external Git repositories, Alpine packages,
Docker base images, and long compiler/library builds. Running both variants on
every change would multiply runner time and make ordinary CI sensitive to
upstream outages. The full-image workflow remains available when a recipe,
base image, source revision, or release needs end-to-end verification.

The Docker images created by the smoke workflow are test outputs on an
ephemeral runner and are deliberately discarded after the job. Uploading
multi-gigabyte image archives is not part of CI. The workflow retains only
build logs, image inspection JSON, source manifests, compiler/tool output,
and source revision evidence for seven days.

## Validation responsibilities

| Change or question | Routine CI | Manual Docker smoke |
| --- | --- | --- |
| Python behavior, CLI planning, discovery, provenance | Required | Not needed |
| Dockerfile instruction syntax | Required via `docker build --check` | Rechecked as part of the build |
| Current base/source/package availability | Not checked | Checked |
| Normal/GDB toolchain compilation | Not checked | Checked when requested |
| Ready-image tools and non-root runtime | Not checked | Checked |
| KOS compile/link smoke test | Not checked | `examples/dreamcast/hello` is built |

The manual workflow is evidence collection, not a release artifact publisher.
Fresh toolchain and full-image results must be recorded before claiming a
recipe or release is end-to-end validated.
