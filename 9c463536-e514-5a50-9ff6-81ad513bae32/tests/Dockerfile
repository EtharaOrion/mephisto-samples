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

COPY scoring/eval_script.py                    /home/workspace/scoring/eval_script.py
COPY scoring/score.py                          /home/workspace/scoring/score.py
COPY scoring/scorer_manifest.json              /home/workspace/scoring/scorer_manifest.json
COPY scoring/judge_requirements.txt            /home/workspace/scoring/judge_requirements.txt
COPY scoring/treasury_liquidity_reference.py   /home/workspace/scoring/treasury_liquidity_reference.py

RUN pip install --no-cache-dir -r /home/workspace/scoring/judge_requirements.txt

COPY hidden_test_data/sofr_test.csv              /home/workspace/scoring/dataset/sofr_test.csv
COPY hidden_test_data/repo_test.csv              /home/workspace/scoring/dataset/repo_test.csv
COPY hidden_test_data/pd_positions_test.csv     /home/workspace/scoring/dataset/pd_positions_test.csv
COPY hidden_test_data/tga_dts_test.csv           /home/workspace/scoring/dataset/tga_dts_test.csv
COPY hidden_test_data/macro_test.csv             /home/workspace/scoring/dataset/macro_test.csv
COPY hidden_test_data/bill_auctions_test.csv    /home/workspace/scoring/dataset/bill_auctions_test.csv
COPY hidden_test_data/short_end_curve_test.csv  /home/workspace/scoring/dataset/short_end_curve_test.csv
COPY hidden_test_data/test_ladder_dates.json    /home/workspace/scoring/dataset/test_ladder_dates.json
COPY hidden_test_data/true_ladder_returns.json  /home/workspace/scoring/dataset/true_ladder_returns.json

COPY hidden_test_data/sofr_train.csv              /home/workspace/scoring/dataset/sofr_train.csv
COPY hidden_test_data/repo_train.csv              /home/workspace/scoring/dataset/repo_train.csv
COPY hidden_test_data/pd_positions_train.csv     /home/workspace/scoring/dataset/pd_positions_train.csv
COPY hidden_test_data/tga_dts_train.csv           /home/workspace/scoring/dataset/tga_dts_train.csv
COPY hidden_test_data/macro_train.csv             /home/workspace/scoring/dataset/macro_train.csv
COPY hidden_test_data/bill_auctions_train.csv    /home/workspace/scoring/dataset/bill_auctions_train.csv
COPY hidden_test_data/short_end_curve_train.csv  /home/workspace/scoring/dataset/short_end_curve_train.csv

RUN mkdir -p /tests /logs/verifier
COPY test.sh /tests/test.sh
RUN chmod +x /tests/test.sh

CMD ["/tests/test.sh"]
