FROM maishuji/dc-chain:14.1.1_gdb

RUN apk update

# Installing prerequites
RUN apk add gawk patch bzip2 tar make gmp mpc mpfr-dev gettext wget \
    libelf texinfo bison flex sed git diffutils curl jpeg \
    libpng-dev python3 pkgconfig libisofs-dev meson ruby-rake \
    py3-pip py3-setuptools \
    py3-wheel samurai cmake openssh cppcheck

# Preparing kos directory
RUN mkdir -p /opt/toolchains/dc && \
    chmod -R 755 /opt/toolchains/dc && \
    chown -R $(id -u):$(id -g) /opt/toolchains/dc
# Uses bash in docker ( necessary for sourcing environ.sh)
SHELL ["/bin/bash", "-c"]
RUN git clone --depth 1 --branch 13JUL24 https://github.com/maishuji/KallistiOS.git /opt/toolchains/dc/kos

# Configuring environ.sh
RUN cd /opt/toolchains/dc/kos && cp doc/environ.sh.sample ./environ.sh && \
    source /opt/toolchains/dc/kos/environ.sh && pwd && \
    make

# Kos-ports
RUN source /opt/toolchains/dc/kos/environ.sh && \
    git clone --branch feature/update-freetype-version --recursive https://github.com/maishuji/kos-ports /opt/toolchains/dc/kos-ports && \
    rm -rf /opt/toolchains/dc/kos-ports/libjimtcl # broken lib

RUN source /opt/toolchains/dc/kos/environ.sh && \
   /opt/toolchains/dc/kos-ports/utils/build-all.sh

# Remove broken examle kgl
RUN sed -e s/kgl//g -i /opt/toolchains/dc/kos/examples/dreamcast/Makefile && cat /opt/toolchains/dc/kos/examples/dreamcast/Makefile

# mkdcdisc
RUN source /opt/toolchains/dc/kos/environ.sh && \
    git clone https://gitlab.com/simulant/mkdcdisc.git /opt/toolchains/dc/mkdcdisc && \
    cd /opt/toolchains/dc/ && ls && \
    cd mkdcdisc && \
    meson setup builddir && \
    meson compile -C builddir && \
    cp builddir/mkdcdisc /usr/local/bin/ && \
    ln -s  /opt/toolchains/dc/mkdcdisc /opt/mkdcdisc

# Create the user
ARG USER=non-root
ARG GROUPNAME=$USER
ARG UID=12345
ARG GID=23456

RUN addgroup \
    --gid "$GID" \
    "$GROUPNAME" \
&&  adduser \
    --disabled-password \
    --gecos "" \
    --ingroup "$GROUPNAME" \
    --uid "$UID" \
    $USER
# ********************************************************
# * Anything else you want to do like clean up goes here *
# ********************************************************

# [Optional] Set the default user. Omit if you want to keep the default as root.
USER $USER