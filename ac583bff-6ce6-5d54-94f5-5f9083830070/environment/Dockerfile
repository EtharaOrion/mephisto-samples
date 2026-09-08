FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl jq build-essential ca-certificates sudo xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash -u 1000 agent \
    && echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers \
    && git config --global safe.directory '*'

RUN mkdir -p /home/workspace/cryoem_reconstruction && chown -R agent:agent /home/workspace
WORKDIR /home/workspace/cryoem_reconstruction

COPY requirements.txt /home/workspace/cryoem_reconstruction/requirements.txt
RUN pip install --no-cache-dir -r /home/workspace/cryoem_reconstruction/requirements.txt

COPY answer_template.json baseline_solver.py initial_model.mrc instruction.md public_micrographs.npz public_problem_config.json /home/workspace/cryoem_reconstruction/
RUN chown -R agent:agent /home/workspace

USER agent
CMD ["python3"]
