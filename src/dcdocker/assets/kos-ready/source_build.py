"""Git checkout and provenance helpers executed inside the ready-image build."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys


GLDC_REPOSITORY = "https://gitlab.com/quentin.cartier.dev/GLdc.git"
RECORD_DIRECTORY = Path("/usr/local/share/dcdocker")


def git(path, *arguments):
    """Return Git output and stop the recipe on any failure."""
    return subprocess.run(["git", "--no-optional-locks", "-C", str(path), *arguments],
                          check=True, text=True, stdout=subprocess.PIPE).stdout.strip()


def checkout(repository, ref, destination):
    """Fetch branch, tag, or full commit into a new directory with no fallback."""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", ref) or ".." in ref:
        raise ValueError("Unsupported source ref")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    git(destination, "init")
    git(destination, "remote", "add", "origin", repository)
    git(destination, "fetch", "--depth", "1", "origin", ref)
    git(destination, "checkout", "--detach", "FETCH_HEAD")
    commit = git(destination, "rev-parse", "--verify", "HEAD^{commit}")
    if re.fullmatch(r"[0-9a-fA-F]{40}", ref) and commit != ref.lower():
        raise ValueError("Fetched commit differs from requested commit")
    print(f"Resolved {repository} {ref} to {commit}", flush=True)
    return commit


def observe(path, requested):
    """Record an actual checkout, including modifications made by the recipe."""
    commit = git(path, "rev-parse", "--verify", "HEAD^{commit}")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid source commit")
    dirty = bool(git(path, "status", "--porcelain=v1", "--untracked-files=all"))
    return {"repository": git(path, "remote", "get-url", "origin"),
            "requested_ref": requested, "commit": commit, "dirty": dirty,
            "state": "dirty" if dirty else "clean", "path": str(path),
            "evidence": "checkout inside Docker build"}


def save(path, data):
    """Write build-stage evidence into the image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def prepare_gldc(ports, ref, selection_file, repository=GLDC_REPOSITORY):
    """Seed the port's dist checkout and disable its moving-ref update path."""
    makefile = ports / "libGL/Makefile"
    text = makefile.read_text(encoding="utf-8")
    download = (ports / "scripts/download.mk").read_text(encoding="utf-8")
    unpack = (ports / "scripts/unpack.mk").read_text(encoding="utf-8")
    if ('elif [ -z "${GIT_TAG}" ]' not in download
            or 'cp -r ../dist/${PORTNAME}-${PORTVERSION} .' not in unpack
            or "DOWNLOAD_FILES" in text or "GIT_REPOSITORY" not in text):
        raise ValueError("Unsupported libGL fetch/unpack interface; cannot guarantee pinned GLdc")
    values = {}
    for key in ("PORTNAME", "PORTVERSION"):
        matches = re.findall(rf"^{key}\s*:?=\s*([A-Za-z0-9_.-]+)\s*$", text, re.MULTILINE)
        if len(matches) != 1:
            raise ValueError(f"Cannot determine libGL {key}")
        values[key] = matches[0]
    name = values["PORTNAME"] + "-" + values["PORTVERSION"]
    commit = checkout(repository, ref, ports / "libGL/dist" / name)
    # A populated dist checkout plus GIT_TAG skips both clone and pull in download.mk.
    with makefile.open("a", encoding="utf-8") as output:
        output.write(f"\n# Pinned checkout prepared by dcdocker.\n"
                     f"override GIT_TAG := {commit}\n"
                     f"override GIT_REPOSITORY := {repository}\n")
    save(selection_file, {"path": str(ports / "libGL/build" / name),
                          "requested_ref": ref, "commit": commit})


def record_gldc(selection_file, output):
    """Observe the unpacked source used by make install before build-all can clean it."""
    selection = json.loads(selection_file.read_text(encoding="utf-8"))
    source = observe(Path(selection["path"]), selection["requested_ref"])
    if source["commit"] != selection["commit"]:
        raise ValueError("GLdc build used a different commit than the prepared checkout")
    save(output, source)


def main():
    """Use explicit subcommands so each Docker stage fails at the responsible operation."""
    action, *args = sys.argv[1:]
    if action == "checkout":
        checkout(*args)
    elif action == "prepare-gldc":
        prepare_gldc(Path(args[0]), args[1], RECORD_DIRECTORY / "gldc-selection.json")
    elif action == "record-gldc":
        record_gldc(RECORD_DIRECTORY / "gldc-selection.json", RECORD_DIRECTORY / "gldc.json")
    elif action == "record":
        sources = {"kos": observe(Path("/opt/toolchains/dc/kos"), os.environ["SNAPSHOT_KOS"]),
                   "kos_ports": observe(Path("/opt/toolchains/dc/kos-ports"),
                                        os.environ["SNAPSHOT_KOSPORTS"]),
                   "gldc": json.loads((RECORD_DIRECTORY / "gldc.json").read_text("utf-8"))}
        save(RECORD_DIRECTORY / "sources.json", {"schema_version": 1, "sources": sources})
        for name, source in sources.items():
            print(f"{name}: {source['commit']} ({source['state']})", flush=True)
    else:
        raise ValueError(f"Unknown source-build action: {action}")


if __name__ == "__main__":
    main()
