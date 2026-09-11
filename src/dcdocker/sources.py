"""Discovery, checkout ownership, and source-layout validation."""

from contextlib import contextmanager
from importlib import resources
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import click
import requests

from dcdocker import defaults


def fetch_ref_names(url, source, key, prefix=""):
    """Read a provider's ref list, distinguishing service errors from empty results."""
    try:
        response = requests.get(url, timeout=defaults.REQUEST_TIMEOUT)
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
    url = defaults.KOS_TAGS_URL
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
    url = defaults.KOS_PORTS_TAGS_URL
    tags = fetch_ref_names(url, "kos-ports", "ref", "refs/tags/")
    return filter_tags_by_year(tags, year)


# Function to fetch branches from the GitLab repository
def fetch_release_branches_gldc():
    """Fetch release branches from the GLdc GitLab repository.

    Returns:
        <str>[]: List of release branches or master branch.
    """
    url = defaults.GLDC_BRANCHES_URL
    branches = fetch_ref_names(url, "GLdc", "name")
    return [branch for branch in branches
            if branch.startswith("release/") or branch == "master"]


@contextmanager
def toolchain_checkout(kos_path=None):
    """Yield local sources unchanged or a fresh checkout owned by this invocation."""
    if kos_path is not None:
        source_path = Path(kos_path).expanduser().resolve()
        print(f"Using local KallistiOS sources: {source_path} (no updates fetched)")
        yield source_path
        return

    with TemporaryDirectory(prefix="dc-chain-kos-") as temporary_directory:
        source_path = Path(temporary_directory) / "kos"
        print(f"Cloning fresh KallistiOS sources from {defaults.KOS_REPOSITORY}")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", defaults.KOS_REPOSITORY, str(source_path)],
                check=True,
            )
        except subprocess.CalledProcessError as process_error:
            raise click.ClickException(
                f"KallistiOS clone failed (exit code {process_error.returncode}). "
                "Check the Git output above, or use --kos-path for a local checkout."
            ) from process_error
        except FileNotFoundError as process_error:
            raise click.ClickException(
                "Git is required for a fresh checkout. Install Git or use --kos-path."
            ) from process_error
        print(f"Using fresh KallistiOS sources: {source_path}")
        yield source_path


def validate_toolchain(source_path, use_gdb):
    """Check the selected Dockerfile's existing GDB compatibility contract."""
    dockerfile_path = source_path / defaults.TOOLCHAIN_DOCKERFILE
    try:
        dockerfile = dockerfile_path.read_text(encoding="utf-8")
    except OSError as file_error:
        raise click.ClickException(
            f"Cannot read KallistiOS Dockerfile at {dockerfile_path}: {file_error}"
        ) from file_error

    if use_gdb and not any(
        line.strip().split("=", 1)[0] == "ARG include_gdb"
        for line in dockerfile.splitlines()
    ):
        raise click.ClickException(
            "The KallistiOS Dockerfile does not support include_gdb. "
            f"Update your checkout at {source_path} before using --use-gdb."
        )


def validate_ready_context(build_context):
    """Validate the caller-supplied context before menus or Docker execution."""
    for filename in defaults.READY_CONTEXT_FILES:
        if not (build_context / filename).is_file():
            raise click.ClickException(
                f"Missing build context file: {build_context / filename}. "
                "Reinstall dreamcast-kos-docker to restore its packaged build assets."
            )


def copy_resources(source, destination):
    """Copy a resource tree using Traversable operations supported by Python 3.11."""
    destination.mkdir()
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            copy_resources(entry, target)
        else:
            target.write_bytes(entry.read_bytes())


@contextmanager
def ready_context():
    """Keep a complete, owned Docker context alive until the build exits."""
    with TemporaryDirectory(prefix="dcdocker-kos-ready-") as directory:
        context = Path(directory) / "kos-ready"
        try:
            source = resources.files("dcdocker").joinpath("assets", "kos-ready")
            copy_resources(source, context)
        except OSError as error:
            raise click.ClickException(
                f"Cannot prepare packaged build assets: {error}. "
                "Reinstall dreamcast-kos-docker and check temporary-directory access."
            ) from error
        validate_ready_context(context)
        yield context
