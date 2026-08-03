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

COPY hidden_test_data/fed_funds_test.csv                    /home/workspace/scoring/fed_funds_test.csv
COPY hidden_test_data/rates_test.csv                        /home/workspace/scoring/rates_test.csv
COPY hidden_test_data/macro_test.csv                        /home/workspace/scoring/macro_test.csv
COPY hidden_test_data/fomc_meetings_test_2025_2026.csv      /home/workspace/scoring/fomc_meetings_test_2025_2026.csv
COPY hidden_test_data/test_windows_schedule.json            /home/workspace/scoring/test_windows_schedule.json
COPY hidden_test_data/test_windows_truth.json               /home/workspace/scoring/test_windows_truth.json
COPY hidden_test_data/test_fomc_events.json                 /home/workspace/scoring/test_fomc_events.json
COPY hidden_test_data/true_regime_events.json               /home/workspace/scoring/true_regime_events.json
COPY hidden_test_data/fed_funds_positioning_reference.py    /home/workspace/scoring/fed_funds_positioning_reference.py

RUN mkdir -p /tests /logs/verifier
COPY test.sh /tests/test.sh
RUN chmod +x /tests/test.sh

CMD ["/tests/test.sh"]
