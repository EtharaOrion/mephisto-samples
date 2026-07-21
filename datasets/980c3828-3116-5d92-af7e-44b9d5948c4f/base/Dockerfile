FROM --platform=linux/amd64 python:3.11
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    jq \
    build-essential sudo \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash agent \
    && echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers \
    && git config --global safe.directory '*'

