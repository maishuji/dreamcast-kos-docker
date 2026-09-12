"""Build inputs, pure plans, and source-to-Docker orchestration."""

from dataclasses import dataclass, field
from pathlib import Path
import re
import hashlib
import json

import click

from dcdocker import defaults, docker, provenance, sources, validation


@dataclass(frozen=True)
class ToolchainBuild:
    """Selected compiler profile and output namespace."""

    namespace: str
    profile: str = defaults.DEFAULT_DC_CHAIN_PROFILE
    gdb: bool = False
    image_tag: str | None = field(default=None, kw_only=True)


@dataclass(frozen=True)
# A flat immutable specification keeps CLI input explicit, including independent base/output tags.
# pylint: disable-next=too-many-instance-attributes
class FullImageBuild:
    """Resolved menu selections; source discovery happens before planning."""

    namespace: str
    profile: str = defaults.DEFAULT_DC_CHAIN_PROFILE
    kos_ref: str = "master"
    kos_ports_ref: str = "master"
    gldc_ref: str = "master"
    gdb: bool = False
    base_image: str | None = field(default=None, kw_only=True)
    image_tag: str | None = field(default=None, kw_only=True)


@dataclass(frozen=True)
class BuildPlan:
    """Output image and immutable command arguments, with no active resources."""

    image: str
    command: tuple[str, ...]


def plan_toolchain(spec, source_path, *, supported_args=None):
    """Calculate a toolchain command without checking out or inspecting sources."""
    validation.namespace(spec.namespace)
    validation.profile(spec.profile)
    tag = validation.image_tag(spec.profile if spec.image_tag is None else spec.image_tag)
    repository = "dc-chain-gdb" if spec.gdb else "dc-chain"
    image = f"{spec.namespace}/{repository}:{tag}"
    arguments = (("profile", spec.profile), ("makejobs", 4), ("include_gdb", int(spec.gdb)))
    if supported_args is not None:
        arguments = tuple(item for item in arguments if item[0] in supported_args)
    command = docker.build_command(
        image, source_path, arguments,
        Path(source_path) / defaults.TOOLCHAIN_DOCKERFILE,
    )
    return BuildPlan(image, command)


SNAPSHOT = re.compile(r"[0-9]{2}(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[0-9]{2}")


def full_image_base(spec):
    """Keep the output namespace independent of the authoritative base reference."""
    if spec.base_image is not None:
        validation.image_reference(spec.base_image)
        return spec.base_image
    validation.image_tag(spec.profile, "--toolchain-tag")
    return f"maishuji/dc-chain{'-gdb' if spec.gdb else ''}:{spec.profile}"


def full_image_tag(spec):
    """Keep snapshot names; distinguish arbitrary refs with a stable source discriminator."""
    if spec.image_tag is not None:
        return validation.image_tag(spec.image_tag)
    base = validation.image_reference(full_image_base(spec))
    if base["tag"] is None:
        raise click.BadParameter("required for an untagged or digest-only base image",
                                 param_hint="--image-tag")
    tag = base["tag"] + ("-gdb-" if spec.gdb else "-")
    def normalize(value):
        return re.sub(r"[^a-z0-9_.-]", "-", value.lower())
    tag += "latest" if spec.kos_ref == "master" else normalize(spec.kos_ref)
    if spec.kos_ports_ref != "master":
        tag += "-kp" + normalize(spec.kos_ports_ref)
    gldc_snapshot = spec.gldc_ref.removeprefix("release/")
    if spec.gldc_ref != "master":
        tag += "-gl" + normalize(gldc_snapshot)
    refs = (spec.kos_ref, spec.kos_ports_ref, spec.gldc_ref)
    legacy = (spec.kos_ref == "master" or SNAPSHOT.fullmatch(spec.kos_ref),
              spec.kos_ports_ref == "master" or SNAPSHOT.fullmatch(spec.kos_ports_ref),
              spec.gldc_ref == "master" or (spec.gldc_ref.startswith("release/")
                                          and SNAPSHOT.fullmatch(gldc_snapshot)))
    if not all(legacy):
        digest = hashlib.sha256(json.dumps(refs).encode("utf-8")).hexdigest()[:12]
        tag += "-r" + digest
    return validation.image_tag(tag, "generated image tag (override with --image-tag)")


def plan_full_image(spec, build_context):
    """Build an offline plan with a complete base reference and validated output tag."""
    validation.namespace(spec.namespace)
    for value, option in ((spec.kos_ref, "--kos-ref"),
                          (spec.kos_ports_ref, "--kos-ports-ref"), (spec.gldc_ref, "--gldc-ref")):
        validation.source_ref(value, option)
    base = full_image_base(spec)
    image = f"{spec.namespace}/dc-kos-image:{full_image_tag(spec)}"
    command = docker.build_command(
        image, build_context,
        (("base_image", base), ("snapshot_kos", spec.kos_ref),
         ("snapshot_kosports", spec.kos_ports_ref), ("snapshot_gldc", spec.gldc_ref)),
    )
    return BuildPlan(image, command)


def build_toolchain(spec, kos_path=None, *, kos_ref=None, metadata_file=None):
    """Keep owned sources alive throughout Docker execution and clean up on exit."""
    report = provenance.new_report("dc-chain", spec, plan_toolchain(spec, "<fresh-kos>"))
    report["sources"]["kos"] = {
        "repository": defaults.KOS_REPOSITORY if kos_path is None else None,
        "requested_ref": kos_ref, "path": str(kos_path) if kos_path is not None else None,
        "commit": None, "dirty": None, "state": "unknown",
        "selection": "local" if kos_path is not None else "remote",
    }
    with provenance.reporting(metadata_file, report):
        with sources.toolchain_checkout(kos_path, kos_ref) as source_path:
            arguments = sources.validate_toolchain(source_path, spec.gdb, spec.profile)
            plan = plan_toolchain(spec, source_path, supported_args=arguments)
            source = provenance.inspect_source(source_path, kos_ref)
            source["selection"] = "local" if kos_path is not None else "remote"
            if kos_path is None:
                source["repository"] = defaults.KOS_REPOSITORY
            report["sources"]["kos"] = source
            report["dockerfile"] = provenance.file_identity(
                source_path / defaults.TOOLCHAIN_DOCKERFILE)
            provenance.show_source("KOS", source)
            if "makejobs" not in arguments:
                print("Dockerfile does not declare makejobs; using upstream concurrency defaults.")
            print("Building Docker image... This may take a while. "
                  f"dc_chain_profile: {spec.profile}")
            print(f"Running command: {docker.display_command(plan.command)}")
            if metadata_file is None:
                docker.execute_build(plan.command, "Toolchain Docker build")
            else:
                docker.recorded_build(plan.command, report, description="Toolchain Docker build")
    print(f"Successfully built Docker image: {plan.image}")


def build_full_image(spec, plan, metadata_file=None):
    """Read source evidence from the output image only when a report was requested."""
    if metadata_file is None:
        docker.execute_build(plan.command)
        return
    report = provenance.new_report("kos-image", spec, plan)
    report["profile"] = None  # An image tag does not prove the compiler profile in that image.
    report["toolchain_tag"] = spec.profile if spec.base_image is None else None
    base = full_image_base(spec)
    report["base"] = {"reference": base, "digest": validation.image_reference(base)["digest"],
                      "evidence": "digest-qualified build input" if "@" in base else
                      "unknown: mutable base tag was not resolved independently"}
    report["sources"] = {
        name: {"requested_ref": ref, "commit": None, "dirty": None, "state": "unknown"}
        for name, ref in (("kos", spec.kos_ref), ("kos_ports", spec.kos_ports_ref),
                          ("gldc", spec.gldc_ref))
    }

    def collect(image_id, directory):
        manifest = directory / "sources.json"
        docker.copy_image_file(image_id, "/usr/local/share/dcdocker/sources.json", manifest)
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data["schema_version"] != 1 or set(data["sources"]) != set(report["sources"]):
                raise ValueError("Unexpected source manifest schema")
            for name, expected in report["sources"].items():
                observed = data["sources"][name]
                if (observed["requested_ref"] != expected["requested_ref"]
                        or not provenance.COMMIT.fullmatch(observed["commit"])
                        or not isinstance(observed["dirty"], bool)
                        or observed["state"] != ("dirty" if observed["dirty"] else "clean")):
                    raise ValueError(f"Invalid build evidence for {name}")
                if (provenance.COMMIT.fullmatch(expected["requested_ref"].lower())
                        and observed["commit"] != expected["requested_ref"].lower()):
                    raise ValueError(f"Pinned commit mismatch for {name}")
            report["sources"] = data["sources"]
            for name, observed in report["sources"].items():
                provenance.show_source(name, observed)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
            raise click.ClickException(f"Cannot verify image source metadata: {error}") from error

    with provenance.reporting(metadata_file, report):
        report["dockerfile"] = provenance.file_identity(Path(plan.command[-1]) / "Dockerfile")
        docker.recorded_build(plan.command, report, collect=collect)
