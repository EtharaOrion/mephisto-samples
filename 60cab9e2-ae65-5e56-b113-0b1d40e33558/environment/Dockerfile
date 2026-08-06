FROM python:3.11-slim@sha256:94c50be2dc994b873b55bc123e95e6dbade08095b3dfd790f51c34de3f08cbb7

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

RUN mkdir -p /home/workspace && chown -R agent:agent /home/workspace
WORKDIR /home/workspace

COPY attachments/requirements.txt /home/workspace/attachments/requirements.txt
RUN pip install --no-cache-dir -r /home/workspace/attachments/requirements.txt \
      numpy==2.4.6 packaging==26.2 pandas==3.0.5 \
      python-dateutil==2.9.0.post0 scipy==1.17.1 six==1.17.0

COPY attachments/ /home/workspace/attachments/
RUN for f in /home/workspace/attachments/*; do \
      base=$(basename "$f"); \
      ln -sf "attachments/$base" "/home/workspace/$base"; \
    done \
    && chown -R agent:agent /home/workspace

USER agent
CMD ["python3"]
