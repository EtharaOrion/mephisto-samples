# Agent work image. Carries the container specification, the recorded corpus, the local
# checker and the stub. It carries no reference encoder, no verifier, no sealed seed and no
# version-control history.
FROM python:3.11-slim@sha256:90744cff8f32887f075c47d747a173ff333e9e98801667af93c357fa9f5e28ff

# curl, sudo and xz are the agent runtime's install dependencies, not this task's. The harness
# starts the work container on a networked bridge, runs the agent's install_cmds
# (`sudo -E bash -c '... curl -fsSL .../node-v20.18.0-linux-$ARCH.tar.xz | tar -xJ -C /usr/local ...'`
# followed by `sudo -E npm install -g`), and only then cuts the container over to the isolated
# network the task is graded on. Every other work image in this dataset carries these three, and
# this one did not, so the install step failed here and nowhere else. The no-network declaration
# in task.toml governs the graded run and does not reach the install phase.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl sudo xz-utils \
 && rm -rf /var/lib/apt/lists/*

# NOPASSWD for the agent account, matching the other work images. The privilege exists so the
# agent runtime can write itself into /usr/local before grading begins; it does not widen what
# the graded run can reach, because that run has no network and the verifier is a separate image.
RUN useradd -m -u 1000 agent \
 && echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
WORKDIR /home/workspace

COPY --chown=agent:agent spec/ /home/workspace/spec/
COPY --chown=agent:agent corpus/ /home/workspace/corpus/
COPY --chown=agent:agent submission/ /home/workspace/submission/
COPY --chown=agent:agent verify_local.py /home/workspace/verify_local.py
COPY --chown=agent:agent task_instruction.md /home/workspace/task_instruction.md

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
USER agent
ENTRYPOINT []
CMD ["sleep", "infinity"]
