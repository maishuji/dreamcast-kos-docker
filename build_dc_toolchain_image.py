"""
This script is used to build a docker image with the dc-chain toolchain.
It can serve as the base of an other image containing all the tools such
as the KOS and kos-ports libraries.
usage: build_dc_toolchain_image.py [-h] [-u USERNAME] [-p PROFILE] [-g]
    USERNAME : the docker username you want to use.
    PROFILE : e.g 15.0.1-dev
    -g : Include GDB in the toolchain image
profiles can be found here :
  https://github.com/KallistiOS/KallistiOS/tree/master/utils/kos-chain/profiles
"""

import os
from pathlib import Path
import subprocess

import click

DEFAULT_DC_CHAIN_PROFILE = "stable"


def build_dc_toolchains_image(username, dc_chain_profile, use_gdb=False):
    """
    Builds a Docker image with specified username and version tag,
    using the upstream KallistiOS Dockerfile.
    Args:
        username (str): The username to be used as part of the image name.
        dc_chain_profile (str): Which dc_chain profile to build.
        use_gdb (bool): If True, include GDB and use the dc-chain-gdb image name.
    """
    path_to_docker = "/opt/toolchains/dc/kos/"
    image_repository = "dc-chain-gdb" if use_gdb else "dc-chain"
    image_name = f"{username}/{image_repository}:{dc_chain_profile}"
    try:
        print(f"Changing directory to: {path_to_docker}")
        os.chdir(path_to_docker)
    except FileNotFoundError:
        print(f"Error: Directory '{path_to_docker}' does not exist.")
        return

    dockerfile_path = Path("utils/kos-chain/docker/Dockerfile")
    if use_gdb and not any(
        line.strip().split("=", 1)[0] == "ARG include_gdb"
        for line in dockerfile_path.read_text(encoding="utf-8").splitlines()
    ):
        raise click.ClickException(
            "The KallistiOS Dockerfile does not support include_gdb. "
            "Update your checkout at /opt/toolchains/dc/kos before using --use-gdb."
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
        "./utils/kos-chain/docker/Dockerfile",
        "."
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


@click.command()
@click.option("-u", "--username", required=True, type=str, help="Docker username")
@click.option(
    "-p",
    "--profile",
    required=False,
    default="stable",
    type=str,
    help="dc-chain profile : e.g 16.2.0",
)
@click.option(
    "-g",
    "--use-gdb",
    is_flag=True,
    default=False,
    help="Include GDB in the toolchain image",
)
def main(username, profile, use_gdb):
    """
    Main function to parse command line arguments and call the build function.
    """
    build_dc_toolchains_image(username, profile, use_gdb)


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()
