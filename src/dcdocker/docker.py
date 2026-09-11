"""Docker command construction and the shared execution boundary."""

import shlex
import subprocess

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
