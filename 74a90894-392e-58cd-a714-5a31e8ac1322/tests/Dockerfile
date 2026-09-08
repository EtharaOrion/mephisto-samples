FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl jq build-essential ca-certificates python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir numpy pandas scipy

RUN mkdir -p /home/workspace/scoring/dataset
WORKDIR /home/workspace

COPY scoring/eval_script.py                     /home/workspace/scoring/eval_script.py
COPY scoring/score.py                           /home/workspace/scoring/score.py
COPY scoring/scorer_manifest.json               /home/workspace/scoring/scorer_manifest.json
COPY scoring/judge_requirements.txt             /home/workspace/scoring/judge_requirements.txt
COPY scoring/appellate_timing_reference.py      /home/workspace/scoring/appellate_timing_reference.py

RUN pip install --no-cache-dir -r /home/workspace/scoring/judge_requirements.txt

COPY hidden_test_data/dockets_test.csv          /home/workspace/scoring/dataset/dockets_test.csv
COPY hidden_test_data/dockets_train.csv         /home/workspace/scoring/dataset/dockets_train.csv
COPY hidden_test_data/true_disposition_days.json /home/workspace/scoring/dataset/true_disposition_days.json
COPY hidden_test_data/true_stall_flags.json     /home/workspace/scoring/dataset/true_stall_flags.json
COPY hidden_test_data/true_motion_counts.json   /home/workspace/scoring/dataset/true_motion_counts.json
COPY hidden_test_data/true_circuit_month_regime.json /home/workspace/scoring/dataset/true_circuit_month_regime.json
COPY hidden_test_data/q2_2025_case_ids.json     /home/workspace/scoring/dataset/q2_2025_case_ids.json
COPY hidden_test_data/test_case_ids.json        /home/workspace/scoring/dataset/test_case_ids.json

RUN mkdir -p /tests /logs/verifier
COPY test.sh /tests/test.sh
RUN chmod +x /tests/test.sh

CMD ["/tests/test.sh"]
