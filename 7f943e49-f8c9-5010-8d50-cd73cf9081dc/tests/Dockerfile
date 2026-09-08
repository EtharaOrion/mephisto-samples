# Judge image for p8theta_rasterlab_bitexact_rewrite.
# From-source posture: every layer is reproducible from this file plus the
# checked-in bundle bytes. No opaque prebuilt layers (lesson from the
# EdgeBench platform analysis: opaque ECR images made ARM rebuilds and
# score audits impossible).
#
# Scoring platform is linux/amd64. The verifier's native-x86_64 guard is
# relaxed image-wide via RASTERLAB_ALLOW_EMULATION=1 (operator decision
# 2026-08-12) so dev/agent trajectories can be scored on ARM hosts without
# manual env injection. On ARM, lanes L1/L2/L3/L5 (80 of 100 points) remain
# integer-exact and fully valid; L4 timing ratios are platform-confounded
# (NEON vs AVX) and MUST NOT be used as Phase-4 signed pilot evidence.
# Signed pilots run on native Intel x86_64 (r7i) per seed/pilot.yaml, where
# this override is a no-op because the guard passes natively.
FROM rust:1.82-bookworm

ENV RASTERLAB_ALLOW_EMULATION=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        make \
        python3 \
    && rm -rf /var/lib/apt/lists/*

# Reference C sources. The verifier rebuilds the reference binary from these
# sources at scoring time, records expected transcripts and perf baselines,
# then deletes both the binary and this source tree before the candidate runs.
COPY reference-src/ /opt/reference-src/

# Verifier harness: environment guard, integrity scan, candidate build,
# fresh workload generation from sealed seeds, differential comparison,
# perf ratio scoring, reward emission.
COPY verify.py workload_generator.py run_workloads.py canary_tokens.json /opt/verifier/

COPY test.sh /opt/tests/test.sh
RUN chmod +x /opt/tests/test.sh

WORKDIR /home/workspace
