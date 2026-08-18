# ARM64 rebuild of the EdgeBench ffmpeg_swscale_reimplementation WORK image.
# Recompiles FFmpeg (C-only, --disable-asm) + the baseline .so for arm64 from the
# source extracted from the upstream amd64 image. Rust/Zig toolchains installed
# arm64-native. All source/data (scaffold, media, python tools) is arch-portable.
#
# Built and pushed as:
#   426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.work.ffmpeg_swscale_reimplementation
#   :arm64-20260812@sha256:bf652aeaa575f18f74a5d68305c1d8ddc7cecd9f4e1797bc9162f04ec22c6502
# The digest above is what ../task.toml pins and what the harness runs.
#
# BUILD CONTEXT = this directory. Two inputs are not committed here and must be
# staged in first for a from-scratch build:
#   1. ffmpeg-src/      30 MB / 734 files; ships at /reference/ffmpeg-src in the image.
#                       Restore from the pinned image or seed/build/ffmpeg_arm64/context/.
#   2. instruction.md   byte-identical to ../instruction.md (the Harbor bundle root);
#                       copied here rather than duplicated in-tree to avoid a dedup finding.
FROM --platform=linux/arm64 ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl jq build-essential cmake gcc g++ libffi-dev pkg-config ca-certificates sudo \
        python3 python3-numpy python3-pip xz-utils file \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash agent \
    && echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers \
    && git config --global safe.directory '*'

# --- FFmpeg 7.1 (C-only, arm64): reference binary + C-only libswscale/libavutil ---
# The extracted ffmpeg-src is trimmed (no configure); fetch full 7.1 (same version
# as the extracted libs: libavutil 59.39 / libswscale 8.3) and build --disable-asm.
RUN mkdir -p /reference && cd /tmp \
    && curl -sSL https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz -o ff.tar.xz \
    && tar xf ff.tar.xz && cd ffmpeg-7.1 \
    && ./configure \
        --disable-asm --disable-doc --disable-network --disable-autodetect \
        --disable-static --enable-shared --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && cp -f ffmpeg /reference/ffmpeg \
    && cd / && rm -rf /tmp/ff.tar.xz /tmp/ffmpeg-7.1
# Keep the exact extracted source tree for the agent to study (matches upstream).
# NOTE: ffmpeg-src (30 MB, 734 files) lives at /reference/ffmpeg-src in the shipped
# image but is not committed in this bundle; restore it from the pinned image or
# from seed/build/ffmpeg_arm64/context/ffmpeg-src to rebuild from scratch.
COPY ffmpeg-src /reference/ffmpeg-src

# --- Baseline shared library (C-only FFmpeg swscale) for arm64 ---
RUN mkdir -p /home/workspace /app
COPY baseline_wrapper.c swscale_api.h /home/workspace/
RUN gcc -shared -fPIC -O2 -o /home/workspace/libswscale_public_baseline.so \
        /home/workspace/baseline_wrapper.c \
        -I/usr/local/include -L/usr/local/lib -lswscale -lavutil \
    && cp -f /home/workspace/libswscale_public_baseline.so /app/libswscale_public_baseline.so \
    && ldconfig

# --- Rust (stable + nightly for portable SIMD) arm64-native ---
ENV RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo PATH=/usr/local/cargo/bin:$PATH
RUN for i in 1 2 3 4 5; do curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
        sh -s -- -y --no-modify-path --default-toolchain stable --profile minimal && break || sleep 8; done \
    && for i in 1 2 3 4 5; do rustup toolchain install nightly --profile minimal && break || sleep 8; done \
    && chmod -R a+w "$RUSTUP_HOME" "$CARGO_HOME"

# --- Zig arm64 (for the optional Zig scaffold path) ---
RUN curl -sSL https://ziglang.org/download/0.14.0/zig-linux-aarch64-0.14.0.tar.xz -o /tmp/zig.tar.xz \
    && mkdir -p /opt && tar -xf /tmp/zig.tar.xz -C /opt && rm /tmp/zig.tar.xz \
    && ln -sf /opt/zig-linux-aarch64-0.14.0/zig /usr/local/bin/zig

# --- Agent workspace (arch-portable source/data) ---
COPY scaffold      /home/workspace/scaffold
COPY media         /home/workspace/media
COPY swscale-impl  /home/workspace/swscale-impl
COPY pixel_formats.py verify_correctness.py run_dev_bench.py instruction.md /home/workspace/
RUN mkdir -p /home/workspace/results && chown -R agent:agent /home/workspace \
    && rm -rf /app && ln -sfn /home/workspace /app

USER agent
WORKDIR /home/workspace/swscale-impl
CMD ["/bin/bash"]
