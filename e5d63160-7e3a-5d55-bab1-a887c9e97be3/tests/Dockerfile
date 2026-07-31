FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl jq build-essential ca-certificates python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir numpy pandas scipy

RUN mkdir -p /home/workspace/scoring
WORKDIR /home/workspace

COPY scoring/eval_script.py         /home/workspace/scoring/eval_script.py
COPY scoring/score.py               /home/workspace/scoring/score.py
COPY scoring/scorer_manifest.json   /home/workspace/scoring/scorer_manifest.json
COPY scoring/judge_requirements.txt /home/workspace/scoring/judge_requirements.txt

RUN pip install --no-cache-dir -r /home/workspace/scoring/judge_requirements.txt

COPY hidden_test_data/financials_test.csv        /home/workspace/scoring/financials_test.csv
COPY hidden_test_data/macro_indicators_test.csv  /home/workspace/scoring/macro_indicators_test.csv
COPY hidden_test_data/test_institutions.json     /home/workspace/scoring/test_institutions.json
COPY hidden_test_data/true_pca_zone_events.json  /home/workspace/scoring/true_pca_zone_events.json
COPY hidden_test_data/bank_capital_projection_reference.py /home/workspace/scoring/bank_capital_projection_reference.py

RUN mkdir -p /tests /logs/verifier
COPY test.sh /tests/test.sh
RUN chmod +x /tests/test.sh

CMD ["/tests/test.sh"]
