# Work image for p8theta_rasterlab_bitexact_rewrite.
# From-source posture: every layer is built from checked-in sources on a
# public base image. No opaque prebuilt layers (lesson from the EdgeBench
# platform-architecture analysis: opaque images make cross-arch rebuilds and
# audits impossible).
FROM rust:1.82-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc make python3 sudo \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -s /bin/bash agent \
 && echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# Readable reference C source (agent-visible by design).
COPY rasterlab-src/ /reference/rasterlab-src/

# Prebuilt reference binary for local experimentation only; it does not exist
# in the scoring environment.
RUN make -C /reference/rasterlab-src \
 && cp /reference/rasterlab-src/rasterlab /reference/rasterlab \
 && (make -C /reference/rasterlab-src clean || true) \
 && test -x /reference/rasterlab

# Agent workspace: sparse man page, public probes with recorded reference
# outputs, local checker, and the candidate crate scaffold.
COPY --chown=agent:agent task_instruction.md /home/workspace/task_instruction.md
COPY --chown=agent:agent rasterlab.1 /home/workspace/rasterlab.1
COPY --chown=agent:agent public_probes/ /home/workspace/public_probes/
COPY --chown=agent:agent verify_local.py /home/workspace/verify_local.py
COPY --chown=agent:agent candidate/ /home/workspace/candidate/

USER agent
WORKDIR /home/workspace
CMD ["/bin/bash"]
