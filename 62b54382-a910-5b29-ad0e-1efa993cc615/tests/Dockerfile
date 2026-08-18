FROM mephisto/bpfc-oracle:1.10.6 AS oracle

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive


RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        binutils \
        python3 \
        util-linux \
        coreutils \
        netbase \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The unprivileged identity that executes every agent-authored byte.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 1001 runner

RUN useradd --no-create-home --shell /usr/sbin/nologin --uid 1002 bench


COPY --from=oracle /usr/local/bin/bpfc-oracle /opt/verifier/oracle/bpfc-oracle
COPY --from=oracle /usr/local/lib/libpcap.a   /opt/verifier/oracle/libpcap.a

# Name tables, byte-identical to the image that produced the golden corpus. A
# drifting table silently changes what the reference compiles.
COPY --from=oracle /pinned/etc/services  /etc/services
COPY --from=oracle /pinned/etc/protocols /etc/protocols
COPY --from=oracle /pinned/etc/networks  /etc/networks
COPY --from=oracle /pinned/etc/ethers    /etc/ethers

# --------------------------------------------------------------------------
# Scoring code. Auditable and locally re-runnable; only the DATA is hidden.
# --------------------------------------------------------------------------
COPY scoring/score.py       /opt/verifier/score.py
COPY scoring/validator.py   /opt/verifier/validator.py
COPY scoring/similarity.py  /opt/verifier/similarity.py
COPY scoring/containment.py /opt/verifier/containment.py

COPY hidden_test_data/hidden_cases.jsonl          /opt/verifier/cases/hidden_cases.jsonl
COPY hidden_test_data/golden.jsonl                /opt/verifier/cases/golden.jsonl
COPY hidden_test_data/manifest.json               /opt/verifier/cases/manifest.json
COPY hidden_test_data/bench_cases.jsonl           /opt/verifier/bench/bench_cases.jsonl
COPY hidden_test_data/REPS                        /opt/verifier/bench/REPS
COPY hidden_test_data/upstream_fingerprints.json  /opt/verifier/ref/upstream_fingerprints.json

RUN chown -R root:root /opt/verifier \
 && chmod 0755 /opt/verifier /opt/verifier/cases /opt/verifier/bench \
               /opt/verifier/ref \
 && chmod 0644 /opt/verifier/cases/hidden_cases.jsonl \
               /opt/verifier/bench/bench_cases.jsonl \
               /opt/verifier/bench/REPS \
               /opt/verifier/score.py /opt/verifier/validator.py \
               /opt/verifier/similarity.py /opt/verifier/containment.py \
 && chmod 0600 /opt/verifier/cases/golden.jsonl \
               /opt/verifier/cases/manifest.json \
               /opt/verifier/ref/upstream_fingerprints.json \
 && chown -R root:bench /opt/verifier/oracle \
 && chmod 0750 /opt/verifier/oracle \
 && chmod 0750 /opt/verifier/oracle/bpfc-oracle \
 && chmod 0640 /opt/verifier/oracle/libpcap.a

RUN set -e; \
    ! runuser -u runner -- test -r /opt/verifier/cases/golden.jsonl; \
    ! runuser -u runner -- test -r /opt/verifier/cases/manifest.json; \
    ! runuser -u runner -- test -r /opt/verifier/ref/upstream_fingerprints.json; \
    runuser -u runner -- test -r /opt/verifier/cases/hidden_cases.jsonl; \
    runuser -u runner -- test -r /opt/verifier/bench/bench_cases.jsonl; \
    echo "trust boundary asserted at build time"

RUN set -e; \
    ! runuser -u runner -- test -x /opt/verifier/oracle/bpfc-oracle; \
    ! runuser -u runner -- test -r /opt/verifier/oracle/bpfc-oracle; \
    ! runuser -u runner -- test -r /opt/verifier/oracle/libpcap.a; \
    runuser -u bench  -- test -x /opt/verifier/oracle/bpfc-oracle; \
    echo "oracle unreachable to runner, executable by bench"

RUN set -e; \
    if find / -xdev \( -name 'gencode.c' -o -name 'optimize.c' -o -name 'grammar.y' \
                      -o -name 'scanner.l' -o -name 'nametoaddr.c' -o -name 'pcap.h' \
                      -o -name 'libpcap*.tar.*' \) -print -quit | grep -q .; then \
        echo "FATAL: upstream source text present in the verifier image" >&2; exit 1; \
    fi; \
    echo "no upstream source text in image"

COPY test.sh /tests/test.sh
RUN chmod 0755 /tests/test.sh

WORKDIR /home/workspace/bpfc

USER root
ENTRYPOINT []
CMD ["/bin/bash", "/tests/test.sh"]
