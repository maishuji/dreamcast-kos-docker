"""Discovery, checkout ownership, and source-layout validation."""

from contextlib import contextmanager
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import re
import shlex
import time
from urllib.parse import parse_qs, urlsplit
import subprocess
from tempfile import TemporaryDirectory

import click
import requests

from dcdocker import defaults, provenance, validation


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


def cache_directory():
    """Return the per-user cache directory without creating it."""
    configured = os.environ.get("XDG_CACHE_HOME")
    root = Path(configured).expanduser() if configured else Path.home() / ".cache"
    return root / "dcdocker"


def _cache_path(catalog_key):
    """Map a catalog identity to a safe cache filename."""
    digest = hashlib.sha256(catalog_key.encode("utf-8")).hexdigest()
    return cache_directory() / f"catalog-{digest}.json"


def _read_cached_catalog(catalog_key):
    """Return a fresh cached catalog, or None for missing/invalid/expired data."""
    path = _cache_path(catalog_key)
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = float(cached["fetched_at"])
        values = cached["values"]
        if cached["version"] != defaults.CATALOG_CACHE_VERSION:
            return None
        if time.time() - fetched_at >= defaults.CATALOG_CACHE_TTL:
            return None
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            return None
        return values
    except (OSError, TypeError, ValueError, KeyError):
        return None


def _write_cached_catalog(catalog_key, values):
    """Persist a successful catalog response using an atomic replacement."""
    path = _cache_path(catalog_key)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f".tmp-{os.getpid()}")
        temporary = temporary_path
        temporary_path.write_text(
            json.dumps({
                "version": defaults.CATALOG_CACHE_VERSION,
                "fetched_at": time.time(),
                "values": values,
            }, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    except OSError:
        # A read-only or unavailable cache must not make a read-only listing fail.
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _catalog(catalog_key, fetcher, refresh):
    """Return a cached catalog when fresh, otherwise fetch and cache it."""
    if not refresh:
        cached = _read_cached_catalog(catalog_key)
        if cached is not None:
            return cached
    values = fetcher()
    _write_cached_catalog(catalog_key, values)
    return values


def _fetch_profile_names(kos_ref=None):
    """Fetch only KallistiOS profile-directory metadata from GitHub."""
    params = {"ref": kos_ref} if kos_ref is not None else None
    try:
        response = requests.get(defaults.KOS_PROFILES_URL, params=params,
                                timeout=defaults.REQUEST_TIMEOUT)
    except requests.Timeout as error:
        raise click.ClickException(
            "Fetching KallistiOS profiles timed out. Try again later "
            f"({defaults.KOS_PROFILES_URL})."
        ) from error
    except requests.RequestException as error:
        raise click.ClickException(
            "Could not fetch KallistiOS profiles. Check your connection and try again "
            f"({defaults.KOS_PROFILES_URL})."
        ) from error
    if response.status_code != 200:
        guidance = (
            "Check service access or rate limits and try again later."
            if response.status_code in (403, 429)
            else "Check the repository, ref, and service availability."
        )
        raise click.ClickException(
            f"Could not fetch KallistiOS profiles (HTTP {response.status_code}). "
            f"{guidance} ({defaults.KOS_PROFILES_URL})"
        )
    try:
        entries = response.json()
    except ValueError as error:
        raise click.ClickException(
            "Invalid JSON while fetching KallistiOS profiles. Try again later "
            f"({defaults.KOS_PROFILES_URL})."
        ) from error
    if not isinstance(entries, list) or any(
            not isinstance(entry, dict) or not isinstance(entry.get("name"), str)
            for entry in entries):
        raise click.ClickException(
            "Unexpected response while fetching KallistiOS profiles. "
            f"Expected a directory listing ({defaults.KOS_PROFILES_URL})."
        )
    profiles = sorted({
        entry["name"][:-3] for entry in entries
        if entry.get("type") == "file"
        and entry["name"].endswith(".mk")
        and len(entry["name"]) > 3
    })
    if not profiles:
        raise click.ClickException(
            "No Dreamcast toolchain profiles found in the selected KallistiOS sources."
        )
    return profiles


def fetch_toolchain_profiles(kos_ref=None, refresh=False):
    """List profile names through the small GitHub directory API response."""
    ref_key = "<default>" if kos_ref is None else f"ref:{kos_ref}"
    return _catalog(f"profiles:{defaults.KOS_PROFILES_URL}:{ref_key}",
                    lambda: _fetch_profile_names(kos_ref), refresh)


def fetch_snapshot_entries(source, year=None, *, use_cache=False, refresh=False):
    """Return user-facing snapshot refs with explicit tag/branch labels."""
    if source == "kos":
        fetcher = fetch_snapshot_kos_tags
        key = f"snapshots:{defaults.KOS_TAGS_URL}"
    elif source == "kos-ports":
        fetcher = fetch_snapshot_kosports_tags
        key = f"snapshots:{defaults.KOS_PORTS_TAGS_URL}"
    elif source == "gldc":
        if year is not None:
            raise click.UsageError("--year applies only to KOS and kos-ports snapshots")
        fetcher = fetch_release_branches_gldc
        key = f"snapshots:{defaults.GLDC_BRANCHES_URL}"
    else:
        raise click.UsageError(f"Unsupported snapshot source: {source}")
    values = _catalog(key, fetcher, refresh) if use_cache else fetcher()
    if source == "gldc":
        return [("branch", branch) for branch in values]

    snapshot_tags = [tag for tag in values if SNAPSHOT_TAG.fullmatch(tag)]
    if year is not None:
        snapshot_tags = filter_tags_by_year(snapshot_tags, str(year))
    return [("tag", tag) for tag in snapshot_tags] + [("branch", "master")]


def list_toolchain_profiles(source_path):
    """List Dreamcast toolchain profile names from a KallistiOS checkout."""
    profile_directory = source_path / defaults.TOOLCHAIN_PROFILES
    try:
        if not profile_directory.is_dir():
            raise OSError("directory does not exist")
        profiles = sorted(
            path.stem for path in profile_directory.iterdir()
            if path.is_file() and path.suffix == ".mk"
        )
    except OSError as file_error:
        raise click.ClickException(
            f"Cannot read toolchain profiles at {profile_directory}: {file_error}"
        ) from file_error
    if not profiles:
        raise click.ClickException(
            f"No Dreamcast toolchain profiles found at {profile_directory}."
        )
    return profiles


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
def toolchain_checkout(kos_path=None, kos_ref=None):
    """Yield local sources unchanged or a fresh checkout owned by this invocation."""
    if kos_path is not None and kos_ref is not None:
        raise click.UsageError("--kos-path conflicts with --kos-ref")
    if kos_ref is not None:
        validation.source_ref(kos_ref, "--kos-ref")
    if kos_path is not None:
        source_path = Path(kos_path).expanduser().resolve()
        print(f"Using local KallistiOS sources: {source_path} (no updates fetched)")
        yield source_path
        return

    with TemporaryDirectory(prefix="dc-chain-kos-") as temporary_directory:
        source_path = Path(temporary_directory) / "kos"
        if kos_ref is not None:
            checkout_ref(defaults.KOS_REPOSITORY, kos_ref, source_path)
            yield source_path
            return
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


def checkout_ref(repository, ref, destination):
    """Fetch the requested ref once and detach at its commit; never fall back to HEAD."""
    commands = (["git", "init", str(destination)],
                ["git", "-C", str(destination), "remote", "add", "origin", repository],
                ["git", "-C", str(destination), "fetch", "--depth", "1", "origin", ref],
                ["git", "-C", str(destination), "checkout", "--detach", "FETCH_HEAD"])
    try:
        for command in commands:
            subprocess.run(command, check=True, timeout=300)
        commit = provenance.git_read(destination, "rev-parse", "--verify", "HEAD^{commit}")
        if not provenance.COMMIT.fullmatch(commit) or (
                provenance.COMMIT.fullmatch(ref.lower()) and commit != ref.lower()):
            raise click.ClickException(f"Checkout does not match requested commit {ref}.")
    except (OSError, subprocess.SubprocessError) as error:
        raise click.ClickException(
            f"Cannot check out KallistiOS ref {ref!r}: {error}. No fallback was attempted."
        ) from error


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
