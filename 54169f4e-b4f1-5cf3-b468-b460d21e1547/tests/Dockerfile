FROM python:3.11-slim
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Etc/UTC
RUN mkdir -p /judge/data /tests /logs/verifier /home/workspace
WORKDIR /home/workspace
COPY judge/score.py judge/metric_lib.py /judge/
COPY judge/data/ /judge/data/
COPY tests/test.sh /tests/test.sh
RUN chmod +x /tests/test.sh
CMD ["/tests/test.sh"]
