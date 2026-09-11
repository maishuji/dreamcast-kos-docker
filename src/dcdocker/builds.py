"""Build inputs, pure plans, and source-to-Docker orchestration."""

from dataclasses import dataclass
from pathlib import Path
import re

from dcdocker import defaults, docker, sources


@dataclass(frozen=True)
class ToolchainBuild:
    """Selected compiler profile and output namespace."""

    namespace: str
    profile: str = defaults.DEFAULT_DC_CHAIN_PROFILE
    gdb: bool = False


@dataclass(frozen=True)
class FullImageBuild:
    """Resolved menu selections; source discovery happens before planning."""

    namespace: str
    profile: str = defaults.DEFAULT_DC_CHAIN_PROFILE
    kos_ref: str = "master"
    kos_ports_ref: str = "master"
    gldc_ref: str = "master"
    gdb: bool = False


@dataclass(frozen=True)
class BuildPlan:
    """Output image and immutable command arguments, with no active resources."""

    image: str
    command: tuple[str, ...]


def plan_toolchain(spec, source_path):
    """Calculate a toolchain command without checking out or inspecting sources."""
    repository = "dc-chain-gdb" if spec.gdb else "dc-chain"
    image = f"{spec.namespace}/{repository}:{spec.profile}"
    command = docker.build_command(
        image, source_path,
        (("profile", spec.profile), ("makejobs", 4), ("include_gdb", int(spec.gdb))),
        Path(source_path) / defaults.TOOLCHAIN_DOCKERFILE,
    )
    return BuildPlan(image, command)


def plan_full_image(spec, build_context):
    """Preserve legacy snapshot naming and build arguments without side effects."""
    tag = spec.profile + "-"
    if spec.gdb:
        tag += "gdb-"
    tag += "latest" if spec.kos_ref == "master" else spec.kos_ref.lower()
    if spec.kos_ports_ref != "master":
        ports_tag = re.sub(r"[^a-z0-9_.-]", "-", spec.kos_ports_ref.lower())
        tag += f"-kp{ports_tag}"
    if spec.gldc_ref != "master":
        tag += f"-gl{spec.gldc_ref[-7:].lower()}"
    image = f"{spec.namespace}/dc-kos-image:{tag}"
    command = docker.build_command(
        image, build_context,
        (("base_image", "dc-chain-gdb" if spec.gdb else "dc-chain"),
         ("dc_chain_version", spec.profile), ("snapshot_kos", spec.kos_ref),
         ("snapshot_kosports", spec.kos_ports_ref), ("snapshot_gldc", spec.gldc_ref)),
    )
    return BuildPlan(image, command)


def build_toolchain(spec, kos_path=None):
    """Keep owned sources alive throughout Docker execution and clean up on exit."""
    with sources.toolchain_checkout(kos_path) as source_path:
        sources.validate_toolchain(source_path, spec.gdb)
        plan = plan_toolchain(spec, source_path)
        print("Building Docker image... This may take a while. dc_chain_profile: ", spec.profile)
        print(f"Running command: {docker.display_command(plan.command)}")
        docker.execute_build(plan.command, "Toolchain Docker build")
        print(f"Successfully built Docker image: {plan.image}")
