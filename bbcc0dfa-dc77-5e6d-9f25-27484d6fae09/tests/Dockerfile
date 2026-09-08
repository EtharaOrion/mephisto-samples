# Judge image for p9iota_latticestore_workspace_reconstruction.
# From-source posture: the reference workspace ships as source under
# /opt/reference-src/ and is compiled inside the judge container at scoring
# time, then deleted before the candidate binary ever runs.
FROM rust:1.82-bookworm

# Operator note (2026-08-12): the scorer aborts with INVALID_ENVIRONMENT on
# non-x86_64 hosts unless this override is set. It is set image-wide so that
# development runs and agent trajectories remain scoreable on ARM hosts. On
# ARM the correctness lanes L1/L2/L3/L5 (75/100) stay valid; the L4 timing
# lane is platform-confounded and MUST NOT be used as Phase-4 signed pilot
# evidence. Signed pilots run on native Intel x86_64 hosts per seed/pilot.yaml
# where this override is a no-op.
ENV LATTICE_ALLOW_EMULATION=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        make \
        python3 \
    && rm -rf /var/lib/apt/lists/*

COPY reference-src/ /opt/reference-src/

COPY verify.py /opt/verifier/verify.py
COPY workload_generator.py /opt/verifier/workload_generator.py
COPY run_workloads.py /opt/verifier/run_workloads.py
COPY canary_tokens.json /opt/verifier/canary_tokens.json

COPY test.sh /opt/tests/test.sh
RUN chmod +x /opt/tests/test.sh

WORKDIR /home/workspace
