FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDGEBENCH_ISA_DIR=/mnt/isa \
    EDGEBENCH_LOG_DIR=/logs/harness \
    EDGEBENCH_SUITE_DIR=/logs/suite \
    EDGEBENCH_BASELINE_DIR=/opt/edgebench/harness/baseline \
    EDGEBENCH_WORKSPACE=/home/workspace

RUN apt-get update \
    && apt-get install --no-install-recommends -y sudo \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 solver \
    && mkdir -p /home/workspace /mnt/isa /logs/harness /logs/suite /opt/edgebench/harness \
    && chown -R solver:solver /home/workspace /logs/harness /logs/suite

COPY private/registry.py /opt/edgebench/private/registry.py
COPY private/arcl.py /opt/edgebench/private/arcl.py
COPY private/corpus.py /opt/edgebench/private/corpus.py
COPY private/mutations.py /opt/edgebench/private/mutations.py
RUN printf '#!/bin/sh\nexec /usr/local/bin/python3 /opt/edgebench/private/mutations.py "$@"\n' > /usr/local/bin/edgebench-advance \
    && chmod 0755 /usr/local/bin/edgebench-advance \
    && chown -R root:root /opt/edgebench/private \
    && chmod 0700 /opt/edgebench/private \
    && chmod 0600 /opt/edgebench/private/registry.py /opt/edgebench/private/arcl.py /opt/edgebench/private/corpus.py /opt/edgebench/private/mutations.py \
    && echo 'solver ALL=(root) NOPASSWD: /usr/local/bin/edgebench-advance' > /etc/sudoers.d/edgebench \
    && chmod 0440 /etc/sudoers.d/edgebench

COPY harness/submit.py /opt/edgebench/harness/submit.py
COPY harness/measure.py /opt/edgebench/harness/measure.py
COPY harness/baseline /opt/edgebench/harness/baseline
COPY starter /home/workspace
RUN chown -R solver:solver /home/workspace \
    && chown -R root:root /opt/edgebench/harness \
    && find /opt/edgebench/harness -type d -exec chmod 0555 {} + \
    && find /opt/edgebench/harness -type f -exec chmod 0444 {} +

RUN /usr/local/bin/edgebench-advance --attempt-index 1 --isa-dir /mnt/isa \
    && chown -R root:root /mnt/isa \
    && find /mnt/isa -type d -exec chmod 0555 {} + \
    && find /mnt/isa -type f -exec chmod 0444 {} +

USER solver
WORKDIR /home/workspace
