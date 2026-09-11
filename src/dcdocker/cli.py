"""Installed and legacy Click commands backed by the shared build implementation."""

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


def print_settings(settings):
    """Display the settings for the Docker build command.

    Args:
        settings (dict): Docker build settings.
    """
    # Build the Docker image with the selected options
    print("\n----------> Print settings <----------")
    print("Building Docker image with the following options:")
    print(f"Username:           \t\t {settings['username']}")
    print(f"Toolchain profile   \t\t {settings['profile']}")
    print(f"snapshot_kos:        \t\t {settings['snapshot_kos']}")
    print(f"snapshot_kos-ports:  \t\t {settings['snapshot_kosports']}")
    print(f"snapshot_gldc branch:\t\t {settings['snapshot_gldc']}")
    print("\nRunning docker command:\n\t", docker.display_command(settings["docker_build_command"]))
    print("--------------------------------------")


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
def toolchain_command(username, profile, use_gdb, kos_path):
    """Build a toolchain from a fresh upstream checkout by default.

    Use --kos-path to build from existing local sources without fetching updates.
    """
    builds.build_toolchain(builds.ToolchainBuild(username, profile, use_gdb), kos_path)


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
def full_image_command(username, profile, kos_ports_branch, gdb):
    """Build a KOS development image with interactive source selection."""

    with sources.ready_context() as build_context:
        spec = builds.FullImageBuild(
            namespace=username,
            profile=profile,
            kos_ref=choose_snapshot_kos(),
            kos_ports_ref=kos_ports_branch or choose_snapshot_kosports(),
            gldc_ref=choose_snapshot_gldc(),
            gdb=gdb,
        )
        plan = builds.plan_full_image(spec, build_context)
        print_settings({
            "username": spec.namespace, "profile": spec.profile,
            "snapshot_kos": spec.kos_ref, "snapshot_kosports": spec.kos_ports_ref,
            "snapshot_gldc": spec.gldc_ref, "docker_build_command": plan.command,
        })
        if prompt_choice("Do you want to continue ?", ["Yes", "No"]) == "Yes":
            print("Running ...")
            docker.execute_build(plan.command)
        else:
            print("Operation cancelled ... ")
            raise SystemExit(1)


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
