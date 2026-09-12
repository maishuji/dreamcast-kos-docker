"""Docker command construction and the shared execution boundary."""

import shlex
import subprocess
import re
from pathlib import Path
from tempfile import TemporaryDirectory

import click


def build_command(image, context, build_args, dockerfile=None):
    """Construct arguments without reading files or starting any processes."""
    command = ["docker", "build"]
    for key, value in build_args:
        command.extend(["--build-arg", f"{key}={value}"])
    command.extend(["-t", image])
    if dockerfile is not None:
        command.extend(["-f", str(dockerfile)])
    command.append(str(context))
    return tuple(command)


def display_command(command):
    """Render a command for copying into a shell without changing its arguments."""
    return shlex.join(command)


def execute_build(command, description="Docker build"):
    """Run Docker synchronously; subprocess.run waits for child cleanup on interruption."""
    try:
        subprocess.run(list(command), check=True, shell=False)
    except subprocess.CalledProcessError as error:
        raise click.ClickException(
            f"{description} failed (exit code {error.returncode}). "
            "See the Docker output above for details."
        ) from error
    except FileNotFoundError as error:
        raise click.ClickException(
            "Docker is required to build the image. Install Docker and try again."
        ) from error


def read_command(*arguments):
    """Run a bounded Docker observation without starting an image's entry point."""
    try:
        return subprocess.run(["docker", *arguments], check=True, capture_output=True,
                              text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise click.ClickException(f"Docker metadata collection failed: {error}") from error


def recorded_build(command, report, *, collect=None, description="Docker build"):
    """Bind metadata to Docker's output image ID rather than a possibly moved output tag."""
    with TemporaryDirectory(prefix="dcdocker-result-") as directory:
        iidfile = Path(directory) / "image-id"
        execute_build((*command[:2], "--iidfile", str(iidfile), *command[2:]), description)
        try:
            image_id = iidfile.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise click.ClickException(
                "Docker succeeded but did not produce an image ID."
            ) from error
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise click.ClickException("Docker returned an invalid output image ID.")
        report["image"]["id"] = image_id
        if collect is not None:
            collect(image_id, Path(directory))


def copy_image_file(image_id, source, destination):
    """Copy from an owned stopped container; never run the image or remove user containers."""
    container = read_command("create", "--pull=never", "--entrypoint", "/bin/true", image_id)
    if not re.fullmatch(r"[0-9a-f]{64}", container):
        raise click.ClickException("Docker returned an invalid metadata container ID.")
    try:
        read_command("cp", f"{container}:{source}", str(destination))
    finally:
        read_command("rm", "--volumes", container)
