# ARM64 rebuild of the EdgeBench ffmpeg_swscale_reimplementation JUDGE image.
# Grader is pure python (extracted verbatim from the upstream judge). The only
# arch-specific piece is the STATICALLY-linked baseline .so at
# /verifier-data/libswscale_baseline.so (FFmpeg C swscale baked in, so it survives
# the grade-time deletion of system FFmpeg libs). Rust/Zig present to rebuild the
# agent candidate from source at grade time.
#
# Built and pushed as:
#   426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.judge.ffmpeg_swscale_reimplementation
#   :arm64-20260812-fixed@sha256:936302e094e1020cfc943f9c9661d49c78c6fa4aecaf278db7b70beceb1fb8ea
# The digest above is what ../task.toml pins and what the harness runs.
# The earlier :arm64-20260812 tag (@sha256:083943c0…) is SUPERSEDED — it lacked the
# exec workdir below and made every submission fail with "archive listing failed".
#
# BUILD CONTEXT = this directory. The seven files in scoring/ are byte-identical to
# /opt/tests in the shipped image. One input is not committed here:
#   /opt/tests/test.sh  the inner grader entrypoint invoked by this image's CMD.
#                       Restore it from the pinned image or from
#                       seed/build/ffmpeg_arm64/context/judge-tests/ before a rebuild.
#                       It is NOT the same file as ./test.sh, which is the Harbor
#                       verifier wrapper the harness injects at run time.
FROM --platform=linux/arm64 ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl jq build-essential cmake gcc g++ libffi-dev pkg-config ca-certificates sudo \
        python3 python3-numpy python3-pip xz-utils file \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash agent \
    && echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers \
    && git config --global safe.directory '*'

# --- FFmpeg 7.1 (C-only) arm64 with STATIC libs, for the static baseline ---
RUN cd /tmp \
    && curl -sSL https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz -o ff.tar.xz \
    && tar xf ff.tar.xz && cd ffmpeg-7.1 \
    && ./configure \
        --disable-asm --disable-doc --disable-network --disable-autodetect \
        --enable-static --enable-shared --enable-pic --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && cd / && rm -rf /tmp/ff.tar.xz /tmp/ffmpeg-7.1

# --- STATIC baseline .so -> /verifier-data (FFmpeg swscale/avutil baked in) ---
# Static linking is deliberate: the grader deletes the system FFmpeg libraries
# before it scores, so a dynamically linked baseline would stop working.
# baseline_hash.txt pins the .so the reward is measured against.
COPY scoring/baseline_wrapper.c scoring/swscale_api.h /tmp/bl/
RUN mkdir -p /verifier-data \
    && gcc -shared -fPIC -O2 -o /verifier-data/libswscale_baseline.so \
         /tmp/bl/baseline_wrapper.c -I/usr/local/include \
         -Wl,-Bstatic -lswscale -lavutil -Wl,-Bdynamic -lm -lpthread -ldl \
    && file /verifier-data/libswscale_baseline.so \
    && ( objdump -p /verifier-data/libswscale_baseline.so | grep -i NEEDED || true ) \
    && sha256sum /verifier-data/libswscale_baseline.so | awk '{print $1}' > /verifier-data/baseline_hash.txt \
    && cp -f /verifier-data/libswscale_baseline.so /usr/local/lib/libswscale_baseline.so \
    && rm -rf /tmp/bl

# --- Rust (stable+nightly) + Zig arm64 (to rebuild the agent candidate) ---
ENV RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo PATH=/usr/local/cargo/bin:$PATH
RUN for i in 1 2 3 4 5; do curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
        sh -s -- -y --no-modify-path --default-toolchain stable --profile minimal && break || sleep 8; done \
    && for i in 1 2 3 4 5; do rustup toolchain install nightly --profile minimal && break || sleep 8; done \
    && chmod -R a+w "$RUSTUP_HOME" "$CARGO_HOME"
RUN for i in 1 2 3; do curl -sSL https://ziglang.org/download/0.14.0/zig-linux-aarch64-0.14.0.tar.xz -o /tmp/zig.tar.xz && break || sleep 8; done \
    && mkdir -p /opt && tar -xf /tmp/zig.tar.xz -C /opt && rm /tmp/zig.tar.xz \
    && ln -sf /opt/zig-linux-aarch64-0.14.0/zig /usr/local/bin/zig

# --- Grader (pure python, extracted verbatim from the upstream judge) ---
# The harness execs grading at this workdir (tar tzf / rebuild / score), so it MUST
# exist in the image. Its absence is what broke the superseded 083943c0 build.
RUN mkdir -p /home/workspace/swscale-impl && chown -R agent:agent /home/workspace

COPY scoring /opt/tests
RUN chmod +x /opt/tests/test.sh /opt/tests/pytest_shim.sh 2>/dev/null || true

CMD ["/opt/tests/test.sh"]
