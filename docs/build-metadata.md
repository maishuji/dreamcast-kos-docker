# Build metadata version 1

Both build commands accept `--metadata-file PATH`. The JSON document describes one invocation. It is an observation record, not a reproducible-build guarantee or a signature. Treat image contents and metadata from untrusted images as untrusted data.

The parent directory must exist. The command reserves a new file before checkout/build execution and refuses an existing file. Local toolchain reports must be outside the selected source directory. Updates replace the reserved report atomically with a complete JSON document. Dry-run prints the destination without reserving or writing it. Input rejection, discovery errors and declined confirmation happen before report creation.

## Document fields

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | `1`; consumers must reject unsupported major versions and tolerate additional fields. |
| `build_kind` | string | `dc-chain` or `kos-image`. |
| `status` | string | `running`, `success`, `failed`, or `cancelled`. |
| `started_at`, `finished_at` | string / null | UTC ISO 8601 timestamps; finish is null until finalization. |
| `image.name` | string | Requested output image name and tag. |
| `image.id` | string / null | Docker's `sha256:…` output ID, read from this build's `--iidfile` after Docker succeeds. Never resolved through the mutable output tag. |
| `profile` | string / null | Requested toolchain source profile. Null for full images; a base image tag does not establish its compiler profile. |
| `toolchain_tag` | string / absent | Full-image default base selection, or null with a custom base; absent for toolchain builds. |
| `gdb_requested` | boolean | User request, not verification that GDB is present or works. |
| `base` | object / null | Full-image `reference`, nullable `digest`, and `evidence`; null for upstream toolchain recipes whose base is not resolved here. |
| `dockerfile` | object / null | SHA-256 of recipe bytes observed before Docker, with an `evidence` description. Null if recipe inspection did not complete. |
| `sources` | object | `kos` for toolchains; `kos`, `kos_ports`, and `gldc` for full images. |
| `error` | string / null | Failure description or interruption name. Null on success. |

Each source has `requested_ref` (string or null), `commit` (full lowercase 40-character ID or null), `dirty` (boolean or null), and `state` (`clean`, `dirty`, `non-git`, or `unknown`). Available observations also include `repository`, `path`, and `evidence`. Toolchain entries include `selection` (`local` or `remote`). Null requested toolchain refs mean the remote default branch or the existing local checkout; they do not imply `master` was requested.

Unknown values are null, never empty strings or invented commits. On early failures some observation fields are absent. Consumers must use `status` before relying on the results: a failed metadata extraction can leave an output image ID because Docker already succeeded. A killed process, disk failure, or failed final write can leave `running`; this must never be treated as success. Metadata failures return a nonzero CLI exit code.

## Evidence and limits

Toolchain observations use read-only Git commands against the selected root before Docker starts. Status includes tracked changes and untracked files, but excludes ignored files. Valid non-Git directories remain supported. Missing Git, an unborn HEAD, or inspection failures produce unknown values. Local origin HTTP user information, query strings and fragments are stripped. User source files and Git's index are not updated by inspection. Concurrent external edits are not prevented, and the record is not a complete snapshot of local file contents. Temporary remote checkout paths no longer exist after the invocation.

Full-image observations are collected inside the Docker build. KOS and kos-ports are observed after their build stages. GLdc is observed in the unpacked checkout after `make install`, before kos-ports cleanup can delete it. The recipe verifies that its commit matches the seeded, pinned distribution checkout. Recipe modifications can make these source trees dirty; that does not mean the requested Git revision was ignored. The embedded manifest has its own `schema_version: 1` and `sources` object.

After a successful Docker build, the CLI uses the image ID to create a stopped container with pulling disabled, copies `/usr/local/share/dcdocker/sources.json`, and removes only that owned container and its anonymous volumes. It validates manifest version, requested refs, commit shapes, pinned commit equality, and dirty/state consistency. It does not execute an image entry point or resolve revisions through a separate HTTP lookup.

A digest-qualified base reference records that input digest with its evidence. A mutable base tag has a null digest: inspecting the tag before or after a build would not prove which base Docker used. Base digests can identify multi-platform indexes; no separate platform manifest/config identity is inferred.

These records do not cover every source used by a full image: other ports, compiler archives, mkdcdisc, SOIL, dcload-ip, package indexes and tool downloads remain outside this schema. Pinning the three selected repositories does not pin those dependencies, Docker cache behavior, or the upstream toolchain recipe's downloads. A successful report establishes command completion and recorded source observations, not a KOS compile or runtime smoke-test result.
