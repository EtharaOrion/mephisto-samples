FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDGEBENCH_GEOMETRY_DIR=/mnt/geometry \
    EDGEBENCH_LOG_DIR=/logs/harness \
    EDGEBENCH_HARNESS_DIR=/opt/edgebench/harness \
    EDGEBENCH_WORKSPACE=/home/workspace

RUN apt-get update \
    && apt-get install --no-install-recommends -y sudo \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 solver \
    && mkdir -p /home/workspace /mnt/geometry /logs/harness /opt/edgebench/harness /opt/edgebench/reference \
    && chown -R solver:solver /home/workspace /logs/harness

COPY private/registry.py /opt/edgebench/private/registry.py
COPY private/mutations.py /opt/edgebench/private/mutations.py
RUN printf '#!/bin/sh\nexec /usr/local/bin/python3 /opt/edgebench/private/mutations.py "$@"\n' > /usr/local/bin/edgebench-advance \
    && chmod 0755 /usr/local/bin/edgebench-advance \
    && chown -R root:root /opt/edgebench/private \
    && chmod 0700 /opt/edgebench/private \
    && chmod 0600 /opt/edgebench/private/registry.py /opt/edgebench/private/mutations.py \
    && echo 'solver ALL=(root) NOPASSWD: /usr/local/bin/edgebench-advance' > /etc/sudoers.d/edgebench \
    && chmod 0440 /etc/sudoers.d/edgebench

COPY harness/ambient.py /opt/edgebench/harness/ambient.py
COPY harness/submit.py /opt/edgebench/harness/submit.py
COPY harness/localcheck.py /opt/edgebench/harness/localcheck.py
COPY starter/starter_construct.py /home/workspace/starter_construct.py
COPY notes/baseline_notes.md /home/workspace/baseline_notes.md
RUN chown solver:solver /home/workspace/starter_construct.py /home/workspace/baseline_notes.md \
    && chown -R root:root /opt/edgebench/harness \
    && chmod 0555 /opt/edgebench/harness \
    && chmod 0444 /opt/edgebench/harness/ambient.py /opt/edgebench/harness/submit.py /opt/edgebench/harness/localcheck.py

RUN /usr/local/bin/edgebench-advance --attempt-index 1 --geometry-dir /mnt/geometry \
    && chown -R root:root /mnt/geometry /opt/edgebench/reference \
    && chmod 0555 /mnt/geometry \
    && chmod 0444 /mnt/geometry/manifest.json /mnt/geometry/predicate.json \
    && chmod 0700 /opt/edgebench/reference

USER solver
WORKDIR /home/workspace
