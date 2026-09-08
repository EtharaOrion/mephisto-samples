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

COPY scoring/judge.py             /home/workspace/scoring/judge.py
COPY scoring/cftc_book_lib.py     /home/workspace/scoring/cftc_book_lib.py

COPY hidden_test_data/cot_graded_truth.csv  /home/workspace/scoring/dataset/cot_graded_truth.csv
COPY hidden_test_data/macro_calendar.csv    /home/workspace/scoring/dataset/macro_calendar.csv

RUN mkdir -p /tests /logs/verifier
COPY test.sh        /tests/test.sh
COPY test_output.py /tests/test_output.py
RUN chmod +x /tests/test.sh

CMD ["/tests/test.sh"]
