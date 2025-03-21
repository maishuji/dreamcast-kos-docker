# This Dockerfile is used to build a docker image with the KallistiOS toolchain and kos-ports libraries
# and can be used to compile Dreamcast homebrew applications. The image is based on the dc-chain image

# Build Arguments
ARG snapshotKos=master
ARG snapshotKosPorts=master
ARG snapshotGLdc=master

# Base image : Kos toolchain. The tag corresponds to the version of the toolchain (profile) used.
FROM maishuji/dc-chain:14.2.1-dev

ARG snapshotKos
ENV SNAPSHOT_KOS=${snapshotKos}

ARG snapshotKosPorts
ENV SNAPSHOT_KOSPORTS=${snapshotKosPorts}

ARG snapshotGLdc
ENV SNAPSHOT_GLDC=${snapshotGLdc}

RUN echo "KOS: $SNAPSHOT_KOS " && \
    echo "KOSPORTS : $SNAPSHOT_KOSPORTS" && \
    echo "GLDC : $SNAPSHOT_GLDC"

# Installing prerequites
RUN apk update && apk add --no-cache gawk patch bzip2 tar make gmp mpc mpfr-dev gettext wget \
    libelf texinfo bison flex sed git diffutils curl jpeg \
    libpng-dev python3 pkgconfig libisofs-dev meson ruby-rake \
    py3-pip py3-setuptools pipx\
    py3-wheel samurai cmake openssh cppcheck \
    coreutils # Need fmt binary

# Preparing kos directory
RUN mkdir -p /opt/toolchains/dc && \
    chmod -R 755 /opt/toolchains/dc && \
    chown -R $(id -u):$(id -g) /opt/toolchains/dc

SHELL ["/bin/bash", "-c"]

RUN echo "Cloning branch: ${SNAPSHOT_KOS}" && \
    echo "Cloning branch: $SNAPSHOT_KOS " && \
    git clone --depth 1 --branch $SNAPSHOT_KOS https://github.com/maishuji/KallistiOS.git /opt/toolchains/dc/kos

# Configuring environ.sh
RUN cd /opt/toolchains/dc/kos && cp doc/environ.sh.sample ./environ.sh && \
    source /opt/toolchains/dc/kos/environ.sh && pwd && \
    make

# Kos-ports
RUN echo "Checkout kos-ports" && source /opt/toolchains/dc/kos/environ.sh && \
git clone --branch $snapshotKosPorts --recursive https://github.com/maishuji/kos-ports /opt/toolchains/dc/kos-ports && \
cd /opt/toolchains/dc/kos-ports/libGL && \
sed -i 's|https://gitlab.com/simulant/GLdc.git|https://gitlab.com/quentin.cartier.dev/GLdc.git|g' Makefile && \
echo "new3" && \
sed -i "/GIT_REPOSITORY/s|$|\nGIT_BRANCH = $snapshotGLdc|" Makefile

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
   /opt/toolchains/dc/kos-ports/utils/build-all.sh

# Remove broken examle kgl
#RUN sed -e s/kgl//g -i /opt/toolchains/dc/kos/examples/dreamcast/Makefile && cat /opt/toolchains/dc/kos/examples/dreamcast/Makefile

# mkdcdisc
RUN source /opt/toolchains/dc/kos/environ.sh && \
    git clone https://gitlab.com/simulant/mkdcdisc.git /opt/toolchains/dc/mkdcdisc && \
    cd /opt/toolchains/dc/ && ls && \
    cd mkdcdisc && \
    meson setup builddir && \
    meson compile -C builddir && \
    cp builddir/mkdcdisc /usr/local/bin/ && \
    ln -s  /opt/toolchains/dc/mkdcdisc /opt/mkdcdisc

RUN apk add include-what-you-use
RUN apk add --upgrade freetype-dev
RUN apk add mesa-dev glew-dev sdl12-compat-dev sdl_image-dev sdl_mixer-dev
RUN apk add freeglut-dev
RUN cd /opt/ && git clone https://github.com/paralin/soil.git && cd soil && \
     mkdir build && cd build && cmake .. && make && \
     mv libsoil.a /usr/lib/ && mv ../inc/SOIL /usr/include/ 

RUN apk add --no-cache clang-extra-tools


# Create non-root user
ARG USER=non-root
ARG GROUPNAME=$USER
ARG UID=12345
ARG GID=23456

RUN addgroup --gid "$GID" "$GROUPNAME" && \
    adduser --disabled-password --gecos "" --ingroup "$GROUPNAME" --uid "$UID" --home /home/$USER $USER && \
    chown -R $USER:$GROUPNAME /home/$USER

# Clean up
RUN rm -rf /var/cache/apk/*

# Set default user
USER $USER
RUN pipx install cpplint && pipx ensurepath
