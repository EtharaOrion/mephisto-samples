FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl jq build-essential ca-certificates python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir numpy pandas scipy

RUN mkdir -p /home/workspace/scoring /home/workspace/scoring/dataset/train /home/workspace/scoring/dataset/test
WORKDIR /home/workspace

COPY scoring/eval_script.py         /home/workspace/scoring/eval_script.py
COPY scoring/score.py               /home/workspace/scoring/score.py
COPY scoring/scorer_manifest.json   /home/workspace/scoring/scorer_manifest.json
COPY scoring/judge_requirements.txt /home/workspace/scoring/judge_requirements.txt

RUN pip install --no-cache-dir -r /home/workspace/scoring/judge_requirements.txt

COPY hidden_test_data/xbrl_train.jsonl                /home/workspace/scoring/dataset/train/xbrl.jsonl
COPY hidden_test_data/universe_train.jsonl            /home/workspace/scoring/dataset/train/universe.jsonl
COPY hidden_test_data/macro_train.jsonl               /home/workspace/scoring/dataset/train/macro.jsonl
COPY hidden_test_data/xbrl_test.jsonl                 /home/workspace/scoring/dataset/test/xbrl.jsonl
COPY hidden_test_data/universe_test.jsonl             /home/workspace/scoring/dataset/test/universe.jsonl
COPY hidden_test_data/macro_test.jsonl                /home/workspace/scoring/dataset/test/macro.jsonl
COPY hidden_test_data/test_filer_quarters.json        /home/workspace/scoring/dataset/test/test_filer_quarters.json
COPY hidden_test_data/TRUTH.md                        /home/workspace/scoring/TRUTH.md
COPY hidden_test_data/leverage_trajectory_reference.py /home/workspace/scoring/leverage_trajectory_reference.py

RUN mkdir -p /tests /logs/verifier
COPY test.sh /tests/test.sh
RUN chmod +x /tests/test.sh

CMD ["/tests/test.sh"]
