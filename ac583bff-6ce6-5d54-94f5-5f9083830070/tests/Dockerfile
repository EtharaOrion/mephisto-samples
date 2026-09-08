FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl jq build-essential ca-certificates python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir numpy>=1.24 scipy>=1.11 mrcfile>=1.5 starfile>=0.5 pandas>=2.0

RUN mkdir -p /opt/cryoem_scoring
WORKDIR /home/workspace

COPY scoring/evaluate.py             /opt/cryoem_scoring/evaluate.py
COPY scoring/hidden_forward_model.py /opt/cryoem_scoring/hidden_forward_model.py
COPY scoring/hidden_eval_config.json /opt/cryoem_scoring/hidden_eval_config.json
COPY scoring/hidden_true_volume.mrc  /opt/cryoem_scoring/hidden_true_volume.mrc
COPY scoring/hidden_micrographs.npz  /opt/cryoem_scoring/hidden_micrographs.npz
COPY scoring/hidden_true_poses.star  /opt/cryoem_scoring/hidden_true_poses.star
COPY scoring/hidden_public_true_poses.star /opt/cryoem_scoring/hidden_public_true_poses.star

RUN mkdir -p /tests /logs/verifier
COPY test.sh /tests/test.sh
RUN chmod +x /tests/test.sh

CMD ["/tests/test.sh"]
