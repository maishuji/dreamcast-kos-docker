"""
This script is used to build a docker image with the dc-chain toolchain.
It can serve as the base of an other image containing all the tools such
as the KOS and kos-ports libraries.
usage: build_dc_toolchain_image.py [-h] [-u USERNAME] [-p PROFILE] [-g]
    USERNAME : the docker username you want to use.
    PROFILE : e.g 15.0.1-dev
    -g : Build GDB-enabled image in addition to base toolchain
profiles can be found here :
  https://github.com/KallistiOS/KallistiOS/tree/master/utils/kos-chain/profiles
"""

import os
import subprocess

import click

DEFAULT_DC_CHAIN_PROFILE = "stable"


def build_gdb_image(username, dc_chain_profile, base_image_name):
    """
    Builds a GDB-enabled Docker image based on the base toolchain image.
    Args:
        username (str): The username to be used as part of the image name.
        dc_chain_profile (str): Which dc_chain profile was built.
        base_image_name (str): The base image to build from.
    """
    gdb_image_name = f"{username}/dc-chain-gdb:{dc_chain_profile}"
    dockerfile_path = os.path.join(os.path.dirname(__file__), "dc-chain/Dockerfile2")

    print(f"\nBuilding GDB-enabled Docker image: {gdb_image_name}")
    print(f"Base image: {base_image_name}")

    command = [
        "docker",
        "build",
        "--build-arg",
        f"base_image={base_image_name}",
        "--build-arg",
        f"profile={dc_chain_profile}",
        "-t",
        gdb_image_name,
        "-f",
        dockerfile_path,
        "."
    ]

    try:
        print(f"Running command: {' '.join(command)}")
        subprocess.run(command, check=True, shell=False)
        print(f"Successfully built GDB-enabled Docker image: {gdb_image_name}")
    except subprocess.CalledProcessError as process_error:
        raise click.ClickException(
            f"GDB Docker build failed (exit code {process_error.returncode}). "
            "See the Docker output above for details."
        ) from process_error


def build_dc_toolchains_image(username, dc_chain_profile, use_gdb=False):
    """
    Builds a Docker image with specified username and version tag,
    and includes an input parameter 'dc_chain'.
    Args:
        username (str): The username to be used as part of the image name.
        dc_chain_profile (str): Which dc_chain profile to build.
        use_gdb (bool): If True, build an additional GDB-enabled image from the base toolchain.
    """
    path_to_docker = "/opt/toolchains/dc/kos/"
    image_name = f"{username}/dc-chain:{dc_chain_profile}"
    try:
        print(f"Changing directory to: {path_to_docker}")
        os.chdir(path_to_docker)
    except FileNotFoundError:
        print(f"Error: Directory '{path_to_docker}' does not exist.")
        return

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

    # Build GDB-enabled image if requested
    if use_gdb:
        build_gdb_image(username, dc_chain_profile, image_name)


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
    help="Build GDB-enabled image in addition to base toolchain",
)
def main(username, profile, use_gdb):
    """
    Main function to parse command line arguments and call the build function.
    """
    build_dc_toolchains_image(username, profile, use_gdb)


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()
