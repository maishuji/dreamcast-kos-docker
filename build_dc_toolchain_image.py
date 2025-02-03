"""
This script is used to build a docker image with the dc-chain toolchain.
It can serve as the base of an other image containing all the tools such as the KOS and kos-ports libraries.
usage: build_dc_toolchain_image.py [-h] [-u USERNAME] [-p PROFILE]
    USERNAME : the docker username you want to use.
    PROFILE : e.g 15.0.1-dev ( default is stable and all the profiles can be found here : https://github.com/KallistiOS/KallistiOS/tree/master/utils/dc-chain/profiles )
"""

import subprocess
import argparse
import os

def build_dc_toolchains_image(username, dc_chain_profile):
    """
    Builds a Docker image with specified username and version tag, and includes an input parameter 'dc_chain'.
    
    Args:
        username (str): The username to be used as part of the image name.
        dc_chain_profile (str): Which dc_chain profile to build.
    """
    path_to_docker = "/opt/toolchains/dc/kos/utils/dc-chain/"
    image_name = f"{username}/dc-chain:{dc_chain_profile}"
    try:
        print(f"Changing directory to: {path_to_docker}")
        os.chdir(path_to_docker)
    except FileNotFoundError:
        print(f"Error: Directory '{path_to_docker}' does not exist.")
        return
    # docker build -t dcchain:stable --build-arg dc_chain=stable .
    # docker build -t ma    ishuji/dc-chain:15.0.1-dev --build-arg dc_chain=15.0.1-dev --build-arg makejobs=4 .
    print("Building Docker image... This may take a while. dc_chain_profile: ", dc_chain_profile)
    command = [
        "docker", "build",
        "--build-arg", f"dc_chain={dc_chain_profile}",
        "--build-arg", "makejobs=4",
        "-t", image_name,
        "./docker/"
    ]
    
    print(f"Running command: {' '.join(command)}")
    #return
    try:
        print(f"Running command: {' '.join(command)}")
        
        subprocess.run(command, check=False, shell=False)
        print(f"Successfully built Docker image: {image_name}")
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while building the Docker image: {e}")

def main():
    parser = argparse.ArgumentParser(description="Build a Docker image with specified username and version tag.")
    parser.add_argument("-u", "--username", type=str, help="Docker username")
    parser.add_argument("-p", "--profile", type=str, required=False, default="stable", help="dc-chain profile : e.g 15.0.1-dev")
    
    args = parser.parse_args()
    build_dc_toolchains_image(args.username, args.profile)

if __name__ == "__main__":
    main()
