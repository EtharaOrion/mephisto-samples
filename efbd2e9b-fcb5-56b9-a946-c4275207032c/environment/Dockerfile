FROM python:3.11-slim
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Etc/UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates sudo xz-utils git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash -u 1000 agent \
    && echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers \
    && git config --global safe.directory '*' \
    && mkdir -p /home/workspace && chown -R agent:agent /home/workspace
WORKDIR /home/workspace
COPY --chown=agent:agent work/credit_lib.py work/gate.py work/check.py work/README.md /home/workspace/
COPY --chown=agent:agent work/data/ /home/workspace/data/
COPY --chown=agent:agent work/strategy/ /home/workspace/strategy/
USER agent
CMD ["python3"]
