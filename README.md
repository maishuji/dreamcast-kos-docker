# dreamcast-kos-docker

## Introduction 

Definition of a Docker Image containing the necessary tools to start programming on Sega Dreamcast.

* **dc-chain** : The toolchain. A dockerfile exists in the kos repository to build a docker image.
   - https://github.com/KallistiOS/KallistiOS/blob/master/utils/dc-chain/docker/Dockerfile
* **kallistios** : SDK , https://github.com/KallistiOS
* **kos-ports** : All the librairies ported for KOS for sega dreamcast https://github.com/KallistiOS/kos-ports
* **mkdcdisc** : Tool to create a cdi image https://gitlab.com/simulant/mkdcdisc

## Usage
This image can be used to setup a devcontainer with vscode (https://code.visualstudio.com/docs/devcontainers/containers) and aims to simplify the configuration of the dev environment.
Such an example exists here : https://github.com/maishuji/dreamcast-in-devcontainer-example
```docker build . -t <name>/dc-kos-image:14.1.1_07JUL24```
```docker push <name>/dc-kos-image:14.1.1_07JUL24```


## Limitations
For now, some aspects have **not** been checked.
- Debugging functionalities
- Testing code through dc-tool from a container