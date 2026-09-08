# Agent environment image for p9iota_latticestore_workspace_reconstruction.
# From-source posture: everything the agent sees is buildable from the bytes in
# this build context. The only prebuilt artifact is the frozen reference CLI at
# /reference/lattice, declared in the task contract as a development-time
# comparison tool. It does not exist in the judge image, so wrapping or
# invoking it from submitted code scores zero via the kill band.
FROM rust:1.82-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc make python3 sudo \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash agent \
    && echo "agent ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/agent \
    && chmod 0440 /etc/sudoers.d/agent

# Frozen prebuilt reference CLI (linux/amd64). Development-time only.
COPY reference-bin/lattice /reference/lattice
RUN chmod 755 /reference/lattice

# Agent workspace: stripped multi-crate sources, spec, public probes with
# expected store-state digests, and the local checker.
COPY --chown=agent:agent task_instruction.md /home/workspace/task_instruction.md
COPY --chown=agent:agent SPEC.md /home/workspace/SPEC.md
COPY --chown=agent:agent workspace/ /home/workspace/workspace/
COPY --chown=agent:agent public_probes/ /home/workspace/public_probes/
COPY --chown=agent:agent verify_local.py /home/workspace/verify_local.py
COPY --chown=agent:agent run_workloads.py /home/workspace/run_workloads.py

USER agent
WORKDIR /home/workspace
CMD ["/bin/bash"]
