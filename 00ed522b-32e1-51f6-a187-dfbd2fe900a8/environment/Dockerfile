FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDGEBENCH_INSTANCE_DIR=/mnt/instances \
    EDGEBENCH_AUTHORITY_DIR=/mnt/authority \
    EDGEBENCH_LOG_DIR=/logs/harness \
    EDGEBENCH_WORKSPACE=/home/workspace

RUN apt-get update \
    && apt-get install --no-install-recommends -y sudo \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 solver \
    && mkdir -p /home/workspace /mnt/instances /mnt/authority /logs/harness /opt/edgebench/harness \
    && chown -R solver:solver /home/workspace /logs/harness

COPY private/geometry.py /opt/edgebench/private/geometry.py
COPY private/placement.py /opt/edgebench/private/placement.py
COPY private/instances.py /opt/edgebench/private/instances.py
COPY private/registry.py /opt/edgebench/private/registry.py
COPY private/mutations.py /opt/edgebench/private/mutations.py
COPY private/instance_seed.json /opt/edgebench/private/instance_seed.json
RUN printf '#!/bin/sh\nexec /usr/local/bin/python3 /opt/edgebench/private/mutations.py "$@"\n' > /usr/local/bin/edgebench-private \
    && chmod 0755 /usr/local/bin/edgebench-private \
    && chown -R root:root /opt/edgebench/private \
    && chmod 0700 /opt/edgebench/private \
    && chmod 0600 /opt/edgebench/private/* \
    && echo 'solver ALL=(root) NOPASSWD: /usr/local/bin/edgebench-private' > /etc/sudoers.d/edgebench \
    && chmod 0440 /etc/sudoers.d/edgebench

COPY harness/submit.py /opt/edgebench/harness/submit.py
COPY harness/preview.py /opt/edgebench/harness/preview.py
COPY harness/geometry.py /opt/edgebench/harness/geometry.py
COPY starter /home/workspace/starter
RUN chown -R solver:solver /home/workspace/starter \
    && chown -R root:root /opt/edgebench/harness \
    && chmod 0555 /opt/edgebench/harness \
    && chmod 0444 /opt/edgebench/harness/submit.py /opt/edgebench/harness/preview.py /opt/edgebench/harness/geometry.py

RUN /usr/local/bin/edgebench-private advance --attempt-index 1 \
        --instance-dir /mnt/instances --authority-dir /mnt/authority \
    && chown -R root:root /mnt/instances /mnt/authority \
    && find /mnt/instances /mnt/authority -type d -exec chmod 0555 {} + \
    && find /mnt/instances /mnt/authority -type f -exec chmod 0444 {} +

USER solver
WORKDIR /home/workspace
