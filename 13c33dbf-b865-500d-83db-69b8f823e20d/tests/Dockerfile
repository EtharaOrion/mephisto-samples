FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDGEBENCH_ISA_DIR=/mnt/isa \
    EDGEBENCH_LOG_DIR=/logs/harness \
    EDGEBENCH_SUITE_DIR=/logs/suite \
    EDGEBENCH_WORKSPACE=/home/workspace \
    EDGEBENCH_PRIVATE_DIR=/verifier/private

RUN pip install --no-cache-dir pytest==8.3.4

WORKDIR /verifier
COPY . /verifier
RUN chmod 0700 /verifier/private \
    && find /verifier/private -type f -exec chmod 0600 {} + \
    && mkdir -p /logs/verifier && mkdir -p /home/workspace
