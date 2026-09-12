"""Build inputs, pure plans, and source-to-Docker orchestration."""

from dataclasses import dataclass, field
from pathlib import Path
import re
import hashlib
import json

import click

from dcdocker import defaults, docker, sources, validation


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


def build_toolchain(spec, kos_path=None):
    """Keep owned sources alive throughout Docker execution and clean up on exit."""
    with sources.toolchain_checkout(kos_path) as source_path:
        arguments = sources.validate_toolchain(source_path, spec.gdb, spec.profile)
        plan = plan_toolchain(spec, source_path, supported_args=arguments)
        if "makejobs" not in arguments:
            print("Dockerfile does not declare makejobs; using upstream concurrency defaults.")
        print("Building Docker image... This may take a while. dc_chain_profile: ", spec.profile)
        print(f"Running command: {docker.display_command(plan.command)}")
        docker.execute_build(plan.command, "Toolchain Docker build")
        print(f"Successfully built Docker image: {plan.image}")
