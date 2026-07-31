# Agent-visible environment for treasury_curve_positioning_book.
# Thin Harbor adapter: image is later built via buildx and pushed to ECR with
# the tag that fills PLACEHOLDER_WORK_TAG in task.toml. See DESIGN.md.
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl jq build-essential ca-certificates sudo \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash -u 1000 agent \
    && echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers \
    && git config --global safe.directory '*'

RUN mkdir -p /home/workspace && chown -R agent:agent /home/workspace
WORKDIR /home/workspace

COPY attachments/requirements.txt /home/workspace/attachments/requirements.txt
RUN pip install --no-cache-dir -r /home/workspace/attachments/requirements.txt

COPY attachments/ /home/workspace/attachments/
RUN for f in /home/workspace/attachments/*; do \
      base=$(basename "$f"); \
      ln -sf "attachments/$base" "/home/workspace/$base"; \
    done \
    && chown -R agent:agent /home/workspace

USER agent
CMD ["python3"]
