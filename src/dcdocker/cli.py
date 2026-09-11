"""Installed and legacy Click commands backed by the shared build implementation."""

from dataclasses import replace
from pathlib import Path

import click

from dcdocker import builds, defaults, docker, sources


def prompt_choice(prompt, choices):
    """Util function to prompt user for selection from a list of options.

    Args:
        prompt (str): Message to display to the user.
        choices (<str>[]): List of choices to present to the user.

    Returns:
        str: Selected choice from the list.
    """
    if not choices:
        raise click.ClickException(
            f"No matching choices available: {prompt.strip()} "
            "Try another selection or check the source repository."
        )
    print(prompt)
    for i, choice in enumerate(choices, 1):
        print(f"{i}. {choice}")

    while True:
        try:
            selection = int(input(f"Select an option (1-{len(choices)}): "))
            if 1 <= selection <= len(choices):
                return choices[selection - 1]
            print("Invalid selection. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")


def choose_snapshot_kos():
    """Choose a snapshot for targeting kos repository
    This function prompts the user to select a snapshot for the kos repository.

    Returns:
        str: The selected snapshot_kos tag.
    """
    years = defaults.SNAPSHOT_YEARS
    kos_year = prompt_choice(
        "\nPlease choose the year for the snapshot for Kos (or choose master for lastest):",
        years,
    )
    if kos_year == "master":
        return kos_year
    # Fetch the avail release tags for the selected year
    snapshot_kos_choices = sources.fetch_snapshot_kos_tags(kos_year)
    # Prompt user to select snapshot_kos
    snapshot_kos = prompt_choice(
        "\nPlease choose a snapshot_kos:", snapshot_kos_choices
    )
    return snapshot_kos


def choose_snapshot_kosports():
    """Choose a snapshop for targeting kos-ports repository

    Returns:
        str: The selected snapshot_kosports tag.
    """
    years = defaults.SNAPSHOT_YEARS
    kosports_year = prompt_choice(
        "\nPlease choose the year for the snapshot for kos-ports (or choose master for lastest):",
        years,
    )
    if kosports_year == "master":
        return kosports_year
    snapshot_kosports_choices = sources.fetch_snapshot_kosports_tags(kosports_year)
    snapshot_kosports = prompt_choice(
        "\nChoose a kos-ports snapshot :", snapshot_kosports_choices
    )
    return snapshot_kosports


def choose_snapshot_gldc():
    """
    Choose which release branch to use for GLdc
    """
    return prompt_choice(
        "\nChoose a release branch for GLdc (master for latest):",
        sources.fetch_release_branches_gldc(),
    )


@click.command()
@click.option("-u", "--namespace", "--username", "username",
              required=True, type=str, help="Namespace for the output image")
@click.option(
    "-p",
    "--profile",
    required=False,
    default=defaults.DEFAULT_DC_CHAIN_PROFILE,
    show_default=True,
    type=str,
    help="Dreamcast toolchain profile from the selected KallistiOS sources",
)
@click.option(
    "-g",
    "--gdb",
    "--use-gdb",
    "use_gdb",
    is_flag=True,
    default=False,
    help="Include GDB in the toolchain image",
)
@click.option(
    "--kos-path",
    type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path),
    help="Use this local KallistiOS checkout as-is instead of cloning fresh upstream sources.",
)
@click.option("--image-tag", help="Override the output image tag")
@click.option("--non-interactive", is_flag=True, help="Never read stdin")
@click.option("--dry-run", is_flag=True, help="Preview without Git, Docker or network access")
def toolchain_command(**options):
    """Build a toolchain from a fresh upstream checkout by default.

    Use --kos-path to build from existing local sources without fetching updates.
    """
    spec = builds.ToolchainBuild(options["username"], options["profile"], options["use_gdb"],
                                 image_tag=options["image_tag"])
    source = options["kos_path"] or Path("<fresh-kos>")
    plan = builds.plan_toolchain(spec, source)
    if options["dry_run"]:
        print(f"Output image: {plan.image}")
        print(f"Profile: {spec.profile}; GDB requested: {spec.gdb}")
        if options["kos_path"] is None:
            print("Source: fresh upstream checkout; commit unresolved; "
                  "<fresh-kos> is a placeholder.")
            print(docker.display_command(
                ("git", "clone", "--depth", "1", defaults.KOS_REPOSITORY, str(source))
            ))
        else:
            print(f"Source: {source} (used as-is; revision not resolved)")
        print("Preview only; source capabilities and image availability have not been verified.")
        print(docker.display_command(plan.command))
    else:
        builds.build_toolchain(spec, options["kos_path"])


@click.command()
@click.option("-u", "--namespace", "--username", "username",
              required=True, type=str, help="Namespace for the output image")
@click.option(
    "-p",
    "--toolchain-tag",
    "--profile",
    "profile",
    required=False,
    type=str,
    default=defaults.DEFAULT_DC_CHAIN_PROFILE,
    show_default=True,
    help="Base toolchain image tag (must be available locally or in the registry)",
)
@click.option(
    "--kos-ports-ref",
    "--kos-ports-branch",
    "kos_ports_branch",
    type=str,
    default=None,
    help="kos-ports branch or tag to use instead of the interactive snapshot selection.",
)
@click.option(
    "-g",
    "--gdb",
    is_flag=True,
    default=False,
    help="Build with GDB support",
)
@click.option("--kos-ref", help="KOS branch/tag; skip its discovery menu")
@click.option("--gldc-ref", help="GLdc branch/tag; skip its discovery menu")
@click.option("--base-image", help="Complete base reference, overriding the default base selection")
@click.option("--image-tag", help="Override the output image tag")
@click.option("--non-interactive", is_flag=True, help="Require all refs and build without stdin")
@click.option("--yes", is_flag=True, help="Skip final confirmation only")
@click.option("--dry-run", is_flag=True, help="Offline preview; requires all three source refs")
@click.pass_context
def full_image_command(ctx, **options):
    """Build a KOS development image with explicit refs or interactive selection."""
    if (options["base_image"] is not None
            and ctx.get_parameter_source("profile") != click.core.ParameterSource.DEFAULT):
        raise click.UsageError("--base-image conflicts with --toolchain-tag / --profile / -p")
    spec = select_full_image(options)
    if options["dry_run"]:
        plan = builds.plan_full_image(spec, Path("<packaged-context>"))
        show_full_image(spec, plan)
        print("Preview only; <packaged-context> is a placeholder. Source commits are unresolved;")
        print("base availability, source existence and GDB contents have not been verified.")
        return
    with sources.ready_context() as build_context:
        plan = builds.plan_full_image(spec, build_context)
        show_full_image(spec, plan)
        if (options["non_interactive"] or options["yes"]
                or prompt_choice("Do you want to continue ?", ["Yes", "No"]) == "Yes"):
            print("Running ...")
            docker.execute_build(plan.command)
        else:
            print("Operation cancelled ... ")
            raise SystemExit(1)


def is_interactive():
    """Keep source/confirmation prompts out of non-terminal sessions."""
    return click.get_text_stream("stdin").isatty()


def select_full_image(options):
    """Validate explicit inputs and prompt only for unresolved source selections."""
    refs = {"kos_ref": options["kos_ref"], "kos_ports_ref": options["kos_ports_branch"],
            "gldc_ref": options["gldc_ref"]}
    missing = [name for name, value in refs.items() if value is None]
    spec = builds.FullImageBuild(
        namespace=options["username"], profile=options["profile"], gdb=options["gdb"],
        base_image=options["base_image"], image_tag=options["image_tag"],
        **{name: "master" if value is None else value for name, value in refs.items()},
    )
    # Validate all explicit data before menus, HTTP, resource extraction or Docker.
    builds.plan_full_image(spec, Path("<packaged-context>"))
    if missing and (options["non_interactive"] or options["dry_run"] or not is_interactive()):
        flags = ", ".join("--" + name.replace("_", "-") for name in missing)
        raise click.UsageError(f"Explicit source refs required: {flags}")
    if (not options["dry_run"] and not options["non_interactive"] and not options["yes"]
            and not is_interactive()):
        raise click.UsageError("Use --non-interactive or --yes to build without confirmation")
    choosers = {"kos_ref": choose_snapshot_kos, "kos_ports_ref": choose_snapshot_kosports,
                "gldc_ref": choose_snapshot_gldc}
    spec = replace(spec, **{name: choosers[name]() for name in missing})
    builds.plan_full_image(spec, Path("<packaged-context>"))
    return spec


def show_full_image(spec, plan):
    """Report the authoritative base separately from the output namespace and tag."""
    print(f"Output image: {plan.image}")
    print(f"Base image: {builds.full_image_base(spec)}")
    print(f"KOS: {spec.kos_ref}; kos-ports: {spec.kos_ports_ref}; GLdc: {spec.gldc_ref}")
    print(f"GDB requested: {spec.gdb}")
    if spec.base_image is not None and spec.gdb:
        print("Custom base is used unchanged; its GDB contents have not been verified.")
    print(docker.display_command(plan.command))


@click.group()
def main():
    """Build Docker images for Dreamcast development."""


@main.group()
def build():
    """Build the compiler toolchain or a complete KOS development image."""


build.add_command(toolchain_command, "dc-chain")
build.add_command(full_image_command, "kos-image")


def legacy_notice(command):
    """Emit one migration notice when a legacy script is executed."""
    click.echo(
        f"This script is a compatibility entry point; use `dcdocker build {command}`.", err=True
    )
