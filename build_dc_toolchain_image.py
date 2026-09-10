"""
This script is used to build a docker image with the dc-chain toolchain.
It can serve as the base of an other image containing all the tools such
as the KOS and kos-ports libraries.
usage: build_dc_toolchain_image.py [-u USERNAME] [-p PROFILE] [-g] [--kos-path PATH]
    USERNAME : the docker username you want to use.
    PROFILE : Dreamcast toolchain profile (default: 16.2.0)
    -g : Include GDB in the toolchain image
    --kos-path : Use existing local sources instead of a fresh upstream checkout
profiles can be found here :
  https://github.com/KallistiOS/KallistiOS/tree/master/utils/kos-chain/profiles/dreamcast
"""

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import click

DEFAULT_DC_CHAIN_PROFILE = "16.2.0"
KOS_REPOSITORY = "https://github.com/KallistiOS/KallistiOS.git"


def build_dc_toolchains_image(username, dc_chain_profile, use_gdb=False, kos_path=None):
    """Build from fresh upstream sources, or an explicitly selected local checkout."""
    if kos_path is not None:
        source_path = Path(kos_path).expanduser().resolve()
        print(f"Using local KallistiOS sources: {source_path} (no updates fetched)")
        build_from_checkout(username, dc_chain_profile, use_gdb, source_path)
        return

    with TemporaryDirectory(prefix="dc-chain-kos-") as temporary_directory:
        source_path = Path(temporary_directory) / "kos"
        print(f"Cloning fresh KallistiOS sources from {KOS_REPOSITORY}")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", KOS_REPOSITORY, str(source_path)],
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
        build_from_checkout(username, dc_chain_profile, use_gdb, source_path)


def build_from_checkout(username, dc_chain_profile, use_gdb, source_path):
    """Use the Dockerfile and build context from the same source directory."""
    image_repository = "dc-chain-gdb" if use_gdb else "dc-chain"
    image_name = f"{username}/{image_repository}:{dc_chain_profile}"
    dockerfile_path = source_path / "utils/kos-chain/docker/Dockerfile"
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

    print(
        "Building Docker image... This may take a while. dc_chain_profile: ",
        dc_chain_profile,
    )
    command = [
        "docker",
        "build",
        "--build-arg",
        f"profile={dc_chain_profile}",
        "--build-arg",
        "makejobs=4",
        "--build-arg",
        f"include_gdb={int(use_gdb)}",
        "-t",
        image_name,
        "-f",
        str(dockerfile_path),
        str(source_path),
    ]

    try:
        print(f"Running command: {' '.join(command)}")
        subprocess.run(command, check=True, shell=False)
        print(f"Successfully built Docker image: {image_name}")
    except subprocess.CalledProcessError as process_error:
        raise click.ClickException(
            f"Toolchain Docker build failed (exit code {process_error.returncode}). "
            "See the Docker output above for details."
        ) from process_error
    except FileNotFoundError as process_error:
        raise click.ClickException("Docker is required to build the image.") from process_error


@click.command()
@click.option("-u", "--username", required=True, type=str, help="Docker username")
@click.option(
    "-p",
    "--profile",
    required=False,
    default=DEFAULT_DC_CHAIN_PROFILE,
    show_default=True,
    type=str,
    help="Dreamcast toolchain profile from the selected KallistiOS sources",
)
@click.option(
    "-g",
    "--use-gdb",
    is_flag=True,
    default=False,
    help="Include GDB in the toolchain image",
)
@click.option(
    "--kos-path",
    type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path),
    help="Use this local KallistiOS checkout as-is instead of cloning fresh upstream sources.",
)
def main(username, profile, use_gdb, kos_path):
    """Build a toolchain from a fresh upstream checkout by default.

    Use --kos-path to build from existing local sources without fetching updates.
    """
    build_dc_toolchains_image(username, profile, use_gdb, kos_path)


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()
