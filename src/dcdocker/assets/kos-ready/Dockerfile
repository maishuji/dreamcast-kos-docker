# This Dockerfile is used to build a docker image with the KallistiOS toolchain and kos-ports libraries
# and can be used to compile Dreamcast homebrew applications. The image is based on the dc-chain image

# Build Arguments
ARG base_image=maishuji/dc-chain:16.2.0
ARG snapshot_kos=master
ARG snapshot_kosports=master
ARG snapshot_gldc=master

# Complete toolchain image reference: normal/GDB variant, custom registry, tag or digest.
FROM ${base_image}

COPY --from=ghcr.io/astral-sh/uv:0.12.11 /uv /uvx /usr/local/bin/

ARG snapshot_kos
ENV SNAPSHOT_KOS=${snapshot_kos}

ARG snapshot_kosports
ENV SNAPSHOT_KOSPORTS=${snapshot_kosports}

ARG snapshot_gldc
ENV SNAPSHOT_GLDC=${snapshot_gldc}

RUN echo "KOS: $SNAPSHOT_KOS " && \
    echo "KOSPORTS : $SNAPSHOT_KOSPORTS" && \
    echo "GLDC : $SNAPSHOT_GLDC"


# Installing prerequisites with retries for transient repository/DNS failures.
COPY --chmod=755 apk-retry.sh /usr/local/bin/apk-retry
RUN apk-retry add --no-cache gawk patch bzip2 tar make gmp mpc mpfr-dev gettext wget \
    libelf texinfo bison flex sed git diffutils curl jpeg \
    libpng-dev python3 pkgconfig libisofs-dev meson ruby-rake \
    py3-setuptools \
    py3-wheel samurai cmake openssh cppcheck \
    coreutils # Need fmt binary

# Preparing kos directory
RUN mkdir -p /opt/toolchains/dc && \
    chmod -R 755 /opt/toolchains/dc && \
    mkdir -p /opt/toolchains/dc/bin && \
    chown -R $(id -u):$(id -g) /opt/toolchains/dc

COPY source_build.py /usr/local/lib/dcdocker/source_build.py

SHELL ["/bin/bash", "-c"]

RUN python3 /usr/local/lib/dcdocker/source_build.py checkout \
    https://github.com/maishuji/KallistiOS.git "$SNAPSHOT_KOS" /opt/toolchains/dc/kos

# Configuring environ.sh
RUN cd /opt/toolchains/dc/kos && cp doc/environ.sh.sample ./environ.sh && \
    source /opt/toolchains/dc/kos/environ.sh && \
    make

# Fetch once, including full commit IDs, then preserve submodule revisions.
RUN python3 /usr/local/lib/dcdocker/source_build.py checkout \
    https://github.com/maishuji/kos-ports "$SNAPSHOT_KOSPORTS" /opt/toolchains/dc/kos-ports && \
    git -C /opt/toolchains/dc/kos-ports submodule update --init --recursive && \
    python3 /usr/local/lib/dcdocker/source_build.py prepare-gldc \
    /opt/toolchains/dc/kos-ports "$SNAPSHOT_GLDC"

# (optional)If you want to compile libraries individually. In that case,
# you need to comment the build_all.sh call part
# Build and install libGL and libdcplib
#RUN source /opt/toolchains/dc/kos/environ.sh && \
#    cd /opt/toolchains/dc/kos-ports/libGL && \
#    make install && \
#    cd /opt/toolchains/dc/kos-ports/libdcplib && \
#    make install

# Removing non-compiling libraries
RUN rm -rf /opt/toolchains/dc/kos-ports/{libjimtcl,mruby,libmp3,cglm}

# raylib cannot compile due to fastmath flag, so need a workaround in this case
#RUN cd /opt/toolchains/dc/kos-ports/raylib4dc && \
#    sed -i 's|^GIT_REPOSITORY = .*|GIT_REPOSITORY = https://github.com/maishuji/raylib|' Makefile && \
#    sed -i 's|^GIT_BRANCH = .*|GIT_BRANCH = feature/dc-branch-compile|' Makefile

# Building kos-ports libraries and install them
# You may not want that if you just need specific libraries
RUN source /opt/toolchains/dc/kos/environ.sh && \
    make -C /opt/toolchains/dc/kos-ports/libGL install && \
    python3 /usr/local/lib/dcdocker/source_build.py record-gldc && \
    /opt/toolchains/dc/kos-ports/utils/build-all.sh && \
    python3 /usr/local/lib/dcdocker/source_build.py record

# Remove broken example kgl
#RUN sed -e s/kgl//g -i /opt/toolchains/dc/kos/examples/dreamcast/Makefile && cat /opt/toolchains/dc/kos/examples/dreamcast/Makefile

# mkdcdisc
RUN source /opt/toolchains/dc/kos/environ.sh && \
    git clone https://gitlab.com/simulant/mkdcdisc.git /opt/toolchains/dc/mkdcdisc && \
    cd /opt/toolchains/dc/ && \
    cd mkdcdisc && \
    meson setup builddir && \
    meson compile -C builddir && \
    cp builddir/mkdcdisc /usr/local/bin/ && \
    ln -s  /opt/toolchains/dc/mkdcdisc /opt/mkdcdisc

RUN apk-retry add --no-cache --upgrade \
    freetype-dev \
    mesa-dev \
    glew-dev \
    sdl12-compat-dev \
    sdl_image-dev \
    sdl_mixer-dev \
    freeglut-dev \
    include-what-you-use \
    clang-extra-tools

RUN apk-retry add --no-cache --upgrade \
    openssl-dev

# SOIL requires a newer version of cmake than the one available in alpine 3.17
RUN wget https://github.com/Kitware/CMake/releases/download/v3.31.4/cmake-3.31.4.tar.gz && \
    tar -xzf cmake-3.31.4.tar.gz &&  \
    cd cmake-3.31.4 && \
    ./bootstrap --parallel=$(nproc) && \
    make -j$(nproc) && \
    make install && \
    cd .. && \
    rm -rf cmake-3.31.4 cmake-3.31.4.tar.gz && \
    hash -r


RUN cd /opt/ && git clone https://github.com/paralin/soil.git && cd soil && \
    mkdir build && cd build && cmake .. && make && \
    mv libsoil.a /usr/lib/ && mv ../inc/SOIL /usr/include/ 


# Install dc-tool-ip
RUN source /opt/toolchains/dc/kos/environ.sh && \
    git clone https://github.com/sizious/dcload-ip.git /opt/dc-tool-ip && \
    cd /opt/dc-tool-ip && \
    make && \
    cp ./host-src/tool/dc-tool-ip /usr/local/bin/

# Source environ.sh in the shell profile (bashrc or bash_profile)
RUN echo "source /opt/toolchains/dc/kos/environ.sh" >> /etc/profile

# Create non-root user
ARG USER=non-root
ARG GROUPNAME=$USER
ARG UID=12345
ARG GID=23456

RUN addgroup --gid "$GID" "$GROUPNAME" && \
    adduser --disabled-password --gecos "" --ingroup "$GROUPNAME" --uid "$UID" --home /home/$USER $USER && \
    chown -R $USER:$GROUPNAME /home/$USER /opt/toolchains/dc

# Clean up
RUN rm -rf /var/cache/apk/*

# Set default user
# Alpine's login shell resets PATH, so also expose tools through /etc/profile.d.
RUN echo 'export PATH="$HOME/.local/bin:$PATH"' > /etc/profile.d/uv.sh
ENV PATH="/home/${USER}/.local/bin:${PATH}"
USER $USER
RUN uv tool install --no-cache --python /usr/bin/python3 cpplint
