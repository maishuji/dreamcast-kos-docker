"""Discovery, checkout ownership, and source-layout validation."""

from contextlib import contextmanager
from importlib import resources
from pathlib import Path
import re
import shlex
from urllib.parse import parse_qs, urlsplit
import subprocess
from tempfile import TemporaryDirectory

import click
import requests

from dcdocker import defaults


def fetch_ref_page(url, source, page):
    """Fetch one bounded page; service errors never become empty discoveries."""
    try:
        response = requests.get(url, params={"per_page": defaults.REF_PAGE_SIZE, "page": page},
                                timeout=defaults.REQUEST_TIMEOUT)
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
    return response, refs


def next_ref_page(response, url, page, count):
    """Honor provider pagination without following URLs outside the requested endpoint."""
    next_link = response.links.get("next", {}).get("url")
    if next_link:
        try:
            original, target = urlsplit(url), urlsplit(next_link)
        except ValueError as error:
            raise click.ClickException(f"Invalid pagination URL while fetching refs ({url}).") \
                from error
        if (target.scheme, target.netloc, target.path) != (
                original.scheme, original.netloc, original.path):
            raise click.ClickException(
                f"Unexpected pagination endpoint while fetching refs ({url})."
            )
        candidates = parse_qs(target.query).get("page", [])
        value = candidates[0] if len(candidates) == 1 else "invalid"
    elif "X-Next-Page" in response.headers:
        value = response.headers["X-Next-Page"]
    elif "Link" in response.headers or count < defaults.REF_PAGE_SIZE:
        return None
    else:
        return page + 1
    if value == "":
        return None
    if value != str(page + 1):
        raise click.ClickException(f"Invalid or repeated pagination while fetching refs ({url}).")
    return page + 1


def fetch_ref_names(url, source, key="name", prefix=""):
    """Collect complete, deduplicated refs or fail instead of returning partial results."""
    names = {}
    page = 1
    for _ in range(defaults.MAX_REF_PAGES):
        response, refs = fetch_ref_page(url, source, page)
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
        current = [ref[key][len(prefix):] for ref in refs]
        if current and all(name in names for name in current):
            raise click.ClickException(f"Repeated page while fetching {source} refs ({url}).")
        names.update(dict.fromkeys(current))
        following = next_ref_page(response, url, page, len(refs))
        if following is None:
            return list(names)
        if not current:
            raise click.ClickException(f"Empty page with more pages for {source} refs ({url}).")
        page = following
    raise click.ClickException(
        f"Pagination limit ({defaults.MAX_REF_PAGES} pages) reached for {source} refs. "
        "Use explicit source refs or try again later."
    )


SNAPSHOT_TAG = re.compile(r"[0-9]{2}(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)([0-9]{2})")


def snapshot_years(tags):
    """Discover snapshot years (20YY) without confusing arbitrary tag suffixes for dates."""
    return sorted({"20" + match[1] for tag in tags
                   if (match := SNAPSHOT_TAG.fullmatch(tag))}, reverse=True)


def filter_tags_by_year(tags, year):
    """Select only DD MON YY snapshot tags from the discovered year."""
    return [tag for tag in tags if SNAPSHOT_TAG.fullmatch(tag) and "20" + tag[-2:] == year]


def fetch_snapshot_kos_tags():
    """Discover KallistiOS tags using GitHub's paginated repository tags endpoint."""
    return fetch_ref_names(defaults.KOS_TAGS_URL, "KallistiOS")


def fetch_snapshot_kosports_tags():
    """Discover kos-ports tags separately from branches."""
    return fetch_ref_names(defaults.KOS_PORTS_TAGS_URL, "kos-ports")


def fetch_release_branches_gldc():
    """Discover GitLab release branches; never invent a missing master branch."""
    branches = fetch_ref_names(defaults.GLDC_BRANCHES_URL, "GLdc")
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


def dockerfile_arguments(dockerfile):
    """Read ARG declarations, including case, whitespace and line continuations.

    This checks declared interface names, not whether a recipe uses them correctly.
    Ignore shell heredocs so their contents cannot impersonate Docker instructions.
    """
    arguments = set()
    pending = ""
    heredocs = []
    escape = "\\"
    for line in dockerfile.splitlines():
        if heredocs:
            if line.strip() == heredocs[0]:
                heredocs.pop(0)
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            directive = re.fullmatch(r"#\s*escape\s*=\s*([`\\])", stripped, re.IGNORECASE)
            if directive:
                escape = directive[1]
            continue
        if stripped.endswith(escape):
            pending += stripped[:-1] + " "
            continue
        instruction = pending + stripped
        pending = ""
        parts = instruction.split(None, 1)
        if len(parts) != 2:
            continue
        if parts[0].upper() == "ARG":
            try:
                declarations = shlex.split(parts[1])
            except ValueError as error:
                raise click.ClickException(
                    "Cannot parse ARG declaration in KallistiOS Dockerfile."
                ) from error
            arguments.update(value.split("=", 1)[0] for value in declarations)
        elif parts[0].upper() in ("RUN", "COPY"):
            heredocs = re.findall(r"<<-?['\"]?([A-Za-z_][A-Za-z0-9_]*)", parts[1])
    return frozenset(arguments)


def validate_toolchain(source_path, use_gdb, profile=defaults.DEFAULT_DC_CHAIN_PROFILE):
    """Validate selected profile and declared interface before starting Docker."""
    dockerfile_path = source_path / defaults.TOOLCHAIN_DOCKERFILE
    try:
        dockerfile = dockerfile_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as file_error:
        raise click.ClickException(
            f"Cannot read KallistiOS Dockerfile at {dockerfile_path}: {file_error}"
        ) from file_error
    arguments = dockerfile_arguments(dockerfile)
    if "profile" not in arguments:
        raise click.ClickException(
            f"The KallistiOS Dockerfile at {dockerfile_path} does not declare ARG profile. "
            "Use a checkout with the supported kos-chain build interface."
        )
    if use_gdb and "include_gdb" not in arguments:
        raise click.ClickException(
            "The KallistiOS Dockerfile does not support include_gdb. "
            f"Update your checkout at {source_path} before using --use-gdb."
        )
    profile_path = source_path / defaults.TOOLCHAIN_PROFILES / f"{profile}.mk"
    try:
        profile_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as file_error:
        raise click.ClickException(
            f"Cannot read selected toolchain profile {profile!r} at {profile_path}. "
            "Choose --profile from this checkout's profiles/dreamcast directory."
        ) from file_error
    return arguments


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
