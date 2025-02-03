# dreamcast-kos-docker

## Introduction 

This repository aims to provide tools for creating ready-to-use docker image for Dreamcast programming.
This image can be used to setup a devcontainer with vscode (https://code.visualstudio.com/docs/devcontainers/containers) and aims to simplify the configuration of the dev environment.

## Components
The docker image includes several parts:
* **dc-chain** : The toolchain. A dockerfile exists in the kos repository to build a docker image.
   - https://github.com/KallistiOS/KallistiOS/blob/master/utils/dc-chain/docker/Dockerfile
* **kallistios** : SDK , https://github.com/KallistiOS
* **kos-ports** : All the librairies ported for KOS for sega dreamcast https://github.com/KallistiOS/kos-ports
* **mkdcdisc** : Tool to create a cdi image https://gitlab.com/simulant/mkdcdisc

*Note: The repos used in the Dockerfiles are forks from the repos above,as we need to have release tags to choose snapshots.*

## Usage

### Build the toolchain

```shell
python ./build_dc_toolchain_image.py -u <your-docker-name> -p <toolchain-profiles>
```

**toolchain-profiles** : The list of available profiles are here: https://github.com/KallistiOS/KallistiOS/tree/master/utils/dc-chain/profiles

**Dockerfile** : Currently, the script expects that you have cloned the kos repository at `/opt/toolchains/dc/kos`, as it looks to the Dockerfile provided  at https://github.com/KallistiOS/KallistiOS/tree/master/utils/dc-chain/docker


### Building a ready-to-use image

```shell
python ./build_dc_kos_full_image.py -u <your-docker-name>
```

The script will prompt you to enter which snapshots to use for kos, kos-ports and GLdc.



## Limitations
For now, some aspects have not yet been handled:
- Debugging functionalities
- Debug connection from container to remote (hardware)