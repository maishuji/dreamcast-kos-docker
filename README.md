# Dreamcast KOS Docker Image

## Introduction

This repository provides tools for creating a ready-to-use Docker image for Dreamcast programming. The image can be used to set up a development container with VS Code ([Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers)) and simplifies the configuration of the development environment.

## Components

The Docker image includes several key components:

- **dc-chain**: The toolchain. A Dockerfile exists in the KOS repository to build a Docker image.
  - [KallistiOS dc-chain Dockerfile](https://github.com/KallistiOS/KallistiOS/blob/master/utils/dc-chain/docker/Dockerfile)
- **KallistiOS (KOS)**: The Dreamcast SDK.
  - [KallistiOS GitHub](https://github.com/KallistiOS)
- **kos-ports**: Libraries ported for KOS on the Sega Dreamcast.
  - [kos-ports GitHub](https://github.com/KallistiOS/kos-ports)
- **mkdcdisc**: A tool to create a CDI image.
  - [mkdcdisc GitLab](https://gitlab.com/simulant/mkdcdisc)

*Note:* The repositories used in the Dockerfiles are forks of the original repositories listed above, as release tags are required to select specific snapshots.

---

## How to Use

### 1. Build the Toolchain

Run the following command to build the toolchain:

```sh
python ./build_dc_toolchain_image.py -u <your-docker-name> -p <toolchain-profiles>
```

- **`toolchain-profiles`**: The list of available profiles can be found here:  
  [KOS Toolchain Profiles](https://github.com/KallistiOS/KallistiOS/tree/master/utils/dc-chain/profiles)
- **Dockerfile Requirement**: The script expects that you have cloned the KOS repository at `/opt/toolchains/dc/kos`, as it relies on the Dockerfile provided here:  
  [KOS dc-chain Dockerfile](https://github.com/KallistiOS/KallistiOS/tree/master/utils/dc-chain/docker)

### 2. Build a Ready-to-Use Image

**Note:** *By default, the ready-to-use image is based on `maishuji/dc-chain:14.2.1-dev`, available on Docker Hub. This means you do not need to build the toolchain unless you want to customize it. If customization is needed, modify the `Dockerfile` accordingly.*

To create the ready-to-use KOS image, run the following script:

```sh
python ./build_dc_kos_full_image.py -u <your-docker-name>
```

This script will prompt you to select specific snapshots for `kos`, `kos-ports`, and `GLdc`.

---

## Useful Commands

### Run the Container

```sh
# Check available images
docker image ls | grep "dc-kos-image"

# Start a container from the chosen image
docker run -it <docker-name>/dc-kos-image:<version-tag>
```

### Version Tag Format

The version tag follows this format:

```
<gcc-profile>-<DDMMYY-kos-snapshot>-kp<DDMMYY-kosports-snapshot>-gl<DDMMYY-GLdc-snapshot>
```

- `kp` and `gl` versioning appear only when a specific snapshot is used.
- Example usage:

```sh
docker run -it maishuji/dc-kos-image:14.2.1-dev-01mar25-kp01mar25-gl01mar25 bash
```

(This image is available on Docker Hub.)

---

## Limitations

Currently, the following features are not yet implemented:

- Debugging functionalities.