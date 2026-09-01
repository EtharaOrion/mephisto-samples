FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDGEBENCH_MODEL_DIR=/mnt/machine_model \
    EDGEBENCH_KERNEL_DIR=/mnt/kernels \
    EDGEBENCH_LOG_DIR=/logs/harness \
    EDGEBENCH_WORKSPACE=/home/workspace

RUN apt-get update \
    && apt-get install --no-install-recommends -y sudo \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 solver \
    && mkdir -p /home/workspace /mnt/kernels /mnt/machine_model /logs/harness /opt/edgebench/harness \
    && chown -R solver:solver /home/workspace /logs/harness

COPY build/kernels.py /opt/edgebench/build/kernels.py
COPY build/make_public_kernels.py /opt/edgebench/build/make_public_kernels.py
RUN python3 /opt/edgebench/build/make_public_kernels.py --out /mnt/kernels/public --count 12 \
    && rm -rf /opt/edgebench/build

COPY private/registry.py /opt/edgebench/private/registry.py
COPY private/mutations.py /opt/edgebench/private/mutations.py
RUN printf '#!/bin/sh\nexec /usr/local/bin/python3 /opt/edgebench/private/mutations.py "$@"\n' > /usr/local/bin/edgebench-advance \
    && chmod 0755 /usr/local/bin/edgebench-advance \
    && chown -R root:root /opt/edgebench/private \
    && chmod 0700 /opt/edgebench/private \
    && chmod 0600 /opt/edgebench/private/registry.py /opt/edgebench/private/mutations.py \
    && echo 'solver ALL=(root) NOPASSWD: /usr/local/bin/edgebench-advance' > /etc/sudoers.d/edgebench \
    && chmod 0440 /etc/sudoers.d/edgebench

COPY harness/machine.py /opt/edgebench/harness/machine.py
COPY harness/trace_run.py /opt/edgebench/harness/trace_run.py
COPY harness/submit.py /opt/edgebench/harness/submit.py
COPY harness/hazard_preview.py /opt/edgebench/harness/hazard_preview.py
COPY starter /home/workspace/starter
RUN chown -R solver:solver /home/workspace/starter \
    && chmod 0755 /home/workspace/starter/build.sh \
    && chown -R root:root /opt/edgebench/harness \
    && chmod 0555 /opt/edgebench/harness \
    && chmod 0444 /opt/edgebench/harness/*.py

RUN /usr/local/bin/edgebench-advance --attempt-index 1 --model-dir /mnt/machine_model --kernel-dir /mnt/kernels \
    && chown -R root:root /mnt/kernels /mnt/machine_model \
    && find /mnt/kernels /mnt/machine_model -type d -exec chmod 0555 {} + \
    && find /mnt/kernels /mnt/machine_model -type f -exec chmod 0444 {} +

USER solver
WORKDIR /home/workspace
