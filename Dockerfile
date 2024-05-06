FROM ubuntu:latest

RUN apt-get update
# Installing prerequites
RUN apt install -y gawk patch bzip2 tar make libgmp-dev libmpfr-dev libmpc-dev gettext wget \
    libelf-dev texinfo bison flex sed git build-essential diffutils curl libjpeg-dev \
    libpng-dev python3 pkg-config libisofs-dev meson ninja-build rake \
    python3-pip python3-setuptools \
    python3-wheel ninja-build

# Preparing toolchains directory
RUN mkdir -p /opt/toolchains/dc && \
    chmod -R 755 /opt/toolchains/dc && \
    chown -R $(id -u):$(id -g) /opt/toolchains/dc

# KallistiOs
RUN git clone https://github.com/KallistiOS/KallistiOS.git /opt/toolchains/dc/kos && \
    cd /opt/toolchains/dc/kos/utils/dc-chain && \
    cp config/config.mk.stable.sample config.mk && \
    make && \
    make gdb && \
    make clean

SHELL ["/bin/bash", "-c"]

# Configuring environ.sh
RUN cd /opt/toolchains/dc/kos && cp doc/environ.sh.sample ./environ.sh && \
    source /opt/toolchains/dc/kos/environ.sh && \
    make

# Kos-ports
RUN apt install -y cmake
RUN source /opt/toolchains/dc/kos/environ.sh && \
    git clone --recursive https://github.com/KallistiOS/kos-ports /opt/toolchains/dc/kos-ports && \
    bash /opt/toolchains/dc/kos-ports/utils/build-all.sh


# Remove broken examle kgl
RUN sed -e s/kgl//g -i /opt/toolchains/dc/kos/examples/dreamcast/Makefile && cat /opt/toolchains/dc/kos/examples/dreamcast/Makefile

RUN source /opt/toolchains/dc/kos/environ.sh && \
    printenv && cd /opt/toolchains/dc/kos/examples && \
    make

# mkdcdisc
RUN source /opt/toolchains/dc/kos/environ.sh && \
    git clone https://gitlab.com/simulant/mkdcdisc.git /opt/toolchains/dc/mkdcdisc && \
    cd /opt/toolchains/dc/ && ls && \
    cd mkdcdisc && \
    meson setup builddir && \
    meson compile -C builddir && \
    cp builddir/mkdcdisc /usr/local/bin/