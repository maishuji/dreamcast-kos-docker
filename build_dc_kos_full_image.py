"""
This script is used to build a docker image with ready to use for Dreamcast development.
"""

from pathlib import Path
import re
import shlex
import subprocess
import sys

import click
import requests

REQUEST_TIMEOUT = 30


def fetch_ref_names(url, source, key, prefix=""):
    """Read a provider's ref list, distinguishing service errors from empty results."""
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
    except requests.Timeout as error:
        raise click.ClickException(
            f"Fetching {source} refs timed out. Try again later ({url})."
        ) from error
    except requests.RequestException as error:
        raise click.ClickException(
            f"Could not fetch {source} refs. Check your connection and try again ({url})."
        ) from error

    if response.status_code != 200:
        guidance = (
            "Check service access or rate limits and try again later."
            if response.status_code in (403, 429)
            else "Check the repository URL and service availability."
        )
        raise click.ClickException(
            f"Could not fetch {source} refs (HTTP {response.status_code}). {guidance} ({url})"
        )
    try:
        refs = response.json()
    except ValueError as error:
        raise click.ClickException(
            f"Invalid JSON while fetching {source} refs. Try again later ({url})."
        ) from error
    if not isinstance(refs, list) or any(
        not isinstance(ref, dict)
        or not isinstance(ref.get(key), str)
        or not ref[key].startswith(prefix)
        or not ref[key][len(prefix):]
        for ref in refs
    ):
        raise click.ClickException(
            f"Unexpected response while fetching {source} refs. "
            f"Expected a list of named refs ({url})."
        )
    return [ref[key][len(prefix):] for ref in refs]


# Function to filter tags that end with '24'
def filter_tags_by_year(tags, year):
    """Filter tags based on the last two digits of the year.
    This function filters a list of tags to include only those that end with
    the last two digits of the specified year.

    Args:
        tags (<str>[]) The array of tags to filter.
        year (str): the year to filter the tags by.
    Returns:
        str[]: The tags that end with the last two digits of the specified year.
    """
    year_pattern = year[
        -2:
    ]  # Extract the last two digits of the year (e.g., '24' from '13JAN24')
    filtered_tags = [tag for tag in tags if tag.endswith(year_pattern)]
    print(filtered_tags)
    return filtered_tags


# Function to fetch tags from the GitHub repository for KallistiOS, and include master
def fetch_snapshot_kos_tags(year):
    """Fetch tags from the KallistiOS GitHub repository.

    Args:
        year (str): The year to filter the tags by.

    Returns:
        <str>[]: List of tags that end with the last two digits of the specified year.
    """
    url = "https://api.github.com/repos/maishuji/KallistiOS/git/refs/tags"
    tags = fetch_ref_names(url, "KallistiOS", "ref", "refs/tags/")
    return filter_tags_by_year(tags, year)


# Function to fetch tags from the GitHub repository for KallistiOS, and include master
def fetch_snapshot_kosports_tags(year):
    """Fetch tags from the kos-ports GitHub repository.

    Args:
        year (str): The year to filter the tags by.

    Returns:
        <str>[]: The list of tags that end with the last two digits of the specified year.
    """
    url = "https://api.github.com/repos/maishuji/kos-ports/git/refs/tags"
    tags = fetch_ref_names(url, "kos-ports", "ref", "refs/tags/")
    return filter_tags_by_year(tags, year)


# Function to fetch branches from the GitLab repository
def fetch_release_branches_gldc():
    """Fetch release branches from the GLdc GitLab repository.

    Returns:
        <str>[]: List of release branches or master branch.
    """
    url = "https://gitlab.com/api/v4/projects/quentin.cartier.dev%2FGLdc/repository/branches"
    branches = fetch_ref_names(url, "GLdc", "name")
    return [branch for branch in branches
            if branch.startswith("release/") or branch == "master"]


# Function to prompt user for selection from a list of options
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
    years = ["2026", "2025", "master"]
    kos_year = prompt_choice(
        "\nPlease choose the year for the snapshot for Kos (or choose master for lastest):",
        years,
    )
    if kos_year == "master":
        return kos_year
    # Fetch the avail release tags for the selected year
    snapshot_kos_choices = fetch_snapshot_kos_tags(kos_year)
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
    years = ["2026", "2025", "master"]
    kosports_year = prompt_choice(
        "\nPlease choose the year for the snapshot for kos-ports (or choose master for lastest):",
        years,
    )
    if kosports_year == "master":
        return kosports_year
    snapshot_kosports_choices = fetch_snapshot_kosports_tags(kosports_year)
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
        fetch_release_branches_gldc(),
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
    print("\nRunning docker command:\n\t", shlex.join(settings["docker_build_command"]))
    print("--------------------------------------")


@click.command()
@click.option("-u", "--username", required=True, type=str, help="Docker username")
@click.option(
    "-p",
    "--profile",
    required=False,
    type=str,
    default="16.2.0",
    show_default=True,
    help="Base toolchain image tag (must be available locally or in the registry)",
)
@click.option(
    "--kos-ports-branch",
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
def main(username, profile, kos_ports_branch, gdb):
    """Main function to parse command line arguments and call the build function."""

    build_context = Path(__file__).resolve().parent / "kos-ready"
    for filename in ("Dockerfile", "apk-retry.sh"):
        if not (build_context / filename).is_file():
            raise click.ClickException(
                f"Missing build context file: {build_context / filename}. "
                "Restore the complete kos-ready directory beside this script."
            )

    snapshot_kos = choose_snapshot_kos()
    snapshot_kosports = kos_ports_branch or choose_snapshot_kosports()
    snapshot_gldc = choose_snapshot_gldc()

    tag = profile + "-"

    # Add gdb suffix if building with GDB support
    if gdb:
        tag += "gdb-"

    if snapshot_kos == "master":
        tag += "latest"
    else:
        tag += f"{snapshot_kos.lower()}"

    # Include a specific kos-ports ref, replacing characters Docker tags cannot use.
    if snapshot_kosports != "master":
        kosports_tag = re.sub(r"[^a-z0-9_.-]", "-", snapshot_kosports.lower())
        tag += f"-kp{kosports_tag}"
    if snapshot_gldc != "master":
        # Only extract the ddmmyy part (as it is a branch,
        # it sould be initially release/ddmmyy. E.g release/10JAN24)
        tag += f"-gl{snapshot_gldc[-7:].lower()}"

    # Use dc-chain-gdb image if gdb flag is set, otherwise use dc-chain
    base_image = "dc-chain-gdb" if gdb else "dc-chain"

    docker_build_command = [
        "docker",
        "build",
        "--build-arg",
        f"base_image={base_image}",
        "--build-arg",
        f"dc_chain_version={profile}",
        "--build-arg",
        f"snapshot_kos={snapshot_kos}",
        "--build-arg",
        f"snapshot_kosports={snapshot_kosports}",
        "--build-arg",
        f"snapshot_gldc={snapshot_gldc}",
        "-t",
        f"{username}/dc-kos-image:{tag}",
        str(build_context),
    ]

    print_settings(
        {
            "username": username,
            "profile": profile,
            "snapshot_kos": snapshot_kos,
            "snapshot_kosports": snapshot_kosports,
            "snapshot_gldc": snapshot_gldc,
            "docker_build_command": docker_build_command,
        }
    )

    confirm_choices = ["Yes", "No"]
    if prompt_choice("Do you want to continue ?", confirm_choices) == "Yes":
        print("Running ...")
        # Execute the Docker build command
        try:
            subprocess.run(docker_build_command, check=True, shell=False)
        except subprocess.CalledProcessError as process_error:
            raise click.ClickException(
                f"Docker build failed (exit code {process_error.returncode}). "
                "See the Docker output above for details."
            ) from process_error
        except FileNotFoundError as process_error:
            raise click.ClickException(
                "Docker is required to build the image. Install Docker and try again."
            ) from process_error
    else:
        print("Operation cancelled ... ")
        sys.exit(1)


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()
