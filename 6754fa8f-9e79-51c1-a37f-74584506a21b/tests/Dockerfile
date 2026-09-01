FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDGEBENCH_MODEL_DIR=/mnt/machine_model \
    EDGEBENCH_KERNEL_DIR=/mnt/kernels \
    EDGEBENCH_LOG_DIR=/logs/harness \
    EDGEBENCH_WORKSPACE=/home/workspace \
    EDGEBENCH_PRIVATE_DIR=/verifier/private

RUN pip install --no-cache-dir pytest==8.3.4

WORKDIR /verifier
COPY . /verifier
RUN chmod 0700 /verifier/private && chmod 0600 /verifier/private/* && mkdir -p /logs/verifier && mkdir -p /home/workspace
