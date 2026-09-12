"""Read-only source observations and optional versioned build reports."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit, urlunsplit

import click


COMMIT = re.compile(r"[0-9a-f]{40}")


def git_read(path, *arguments):
    """Disable optional index writes and filesystem-monitor hooks while inspecting Git."""
    return subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(path),
         *arguments], check=True, capture_output=True, text=True, timeout=30,
    ).stdout.strip()


def public_remote(value):
    """Omit HTTP credentials and query parameters from reports and console output."""
    if "://" not in value:
        return value
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, "", ""))


def inspect_source(path, requested_ref=None):
    """Observe the selected root, never accidentally attribute a parent repository to it."""
    path = Path(path).resolve()
    result = {"path": str(path), "repository": None, "requested_ref": requested_ref,
              "commit": None, "dirty": None, "state": "non-git",
              "evidence": "checkout before Docker build"}
    if not (path / ".git").exists():
        return result
    result["state"] = "unknown"
    try:
        if Path(git_read(path, "rev-parse", "--show-toplevel")).resolve() != path:
            return result
        commit = git_read(path, "rev-parse", "--verify", "HEAD^{commit}")
        if not COMMIT.fullmatch(commit):
            return result
        result["commit"] = commit
        result["dirty"] = bool(git_read(path, "status", "--porcelain=v1",
                                        "--untracked-files=all", "--ignore-submodules=none"))
        result["state"] = "dirty" if result["dirty"] else "clean"
        try:
            result["repository"] = public_remote(git_read(path, "remote", "get-url", "origin"))
        except subprocess.CalledProcessError:
            pass  # Valid repositories need not have an origin remote.
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        result["state"] = "unknown"
    return result


def show_source(name, source):
    """Keep unknown revisions and modified sources visible without a report file."""
    print(f"{name} source: {source['repository'] or source['path'] or 'unknown'}; "
          f"commit: {source['commit'] or 'unknown'}; state: {source['state']}")


def file_identity(path):
    """Identify the recipe observed before Docker execution."""
    try:
        return {"sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                "evidence": "Dockerfile bytes before Docker build"}
    except OSError as error:
        raise click.ClickException(f"Cannot identify Dockerfile {path}: {error}") from error


def new_report(kind, spec, plan):
    """Version 1 uses null for unknown observations, never a guessed revision."""
    return {"schema_version": 1, "build_kind": kind, "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
            "image": {"name": plan.image, "id": None}, "base": None,
            "profile": spec.profile, "gdb_requested": spec.gdb,
            "sources": {}, "dockerfile": None, "error": None}


def write_report(path, report):
    """Replace only the report reserved by this invocation, using a complete JSON file."""
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                prefix=".dcdocker-metadata-", delete=False) as output:
            temporary = Path(output.name)
            json.dump(report, output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(temporary, path)
    except OSError as error:
        raise click.ClickException(f"Cannot write build metadata at {path}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def reporting(path, report):
    """Reserve a new output before building; preserve failure and interruption states."""
    if path is not None:
        path = Path(path)
        try:
            with path.open("x", encoding="utf-8"):
                pass
        except OSError as error:
            raise click.ClickException(
                f"Cannot create metadata file {path}: {error}. Choose a new writable path."
            ) from error
        write_report(path, report)
    try:
        yield report
    except BaseException as error:
        report["status"] = "cancelled" if isinstance(error, (KeyboardInterrupt, SystemExit)) \
            else "failed"
        report["error"] = str(error) or type(error).__name__
        raise
    else:
        report["status"] = "success"
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        if path is not None:
            write_report(path, report)
