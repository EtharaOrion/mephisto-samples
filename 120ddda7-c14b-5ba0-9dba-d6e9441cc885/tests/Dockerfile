# Verifier image for libpcap_bpf_codegen_fidelity.
#
# REWRITTEN after an adversarial review. The previous revision:
#   * COPYd four asset names that existed nowhere in the build tree, so the
#     image could not build at all;
#   * COPYd 430 KB of verbatim libpcap source into /opt/verifier/upstream_ngrams
#     under a comment claiming it shipped fingerprints;
#   * left golden.jsonl at the COPY default 0644 while the agent's binary ran as
#     root in this container, so reading the answers was a one-line exploit;
#   * declared no USER, so agent-authored code ran as root with write access to
#     every grading asset and to the reward file itself.
#
# The trust model this image exists to enforce: the agent's Makefile and the
# agent's binary run here, as an unprivileged user, with the answers unreadable
# to that user. Nothing about that is left to convention; test.sh asserts it
# before it grades.

# THE MUTATED ORACLE. This must be the same compiler that produced
# golden.jsonl, not stock libpcap 1.10.6. The judge uses it for the
# interleaved throughput reference, so a pristine oracle here would time a
# DIFFERENT compiler than the one the candidate is graded against and quietly
# bias r. It is also the archive CTL_LINK_LIBPCAP links, so a submission that
# defeated the import denylist must find the mutated compiler behind it.
FROM mephisto/bpfc-oracle:1.10.6-mut1 AS oracle

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# build-essential: the judge rebuilds the submission from source and never
#   trusts a shipped binary.
# binutils: nm and ldd back the import denylist.
# util-linux: setpriv drops privilege for every agent-authored execution.
# netbase: /etc/services and /etc/protocols. Without it libpcap resolves
#   `port ssh` to "unknown port 'ssh'", which would make the judge's own oracle
#   disagree with the golden corpus that was generated with it present.
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

# A SECOND unprivileged identity, used only to run the timing reference.
#
# Phase 3 Hacker defeated the previous revision with 28 lines of C: the oracle
# binary sat at mode 0755 in the same container as agent code and answers the
# identical invocation contract, so posix_spawn on it returned C = 1.000000.
# posix_spawn is not in the import denylist, and it never can be made safe by
# listing, because syscall, execveat, fexecve and raw inline assembly all reach
# execve without naming it. A denylist is a blocklist and blocklists fail open.
#
# So the oracle is made UNREACHABLE instead of merely un-nameable. It runs as
# `bench`, the candidate runs as `runner`, and neither can reach the other. Both
# are unprivileged and pinned to the same cores, so the throughput comparison
# stays symmetric.
RUN useradd --no-create-home --shell /usr/sbin/nologin --uid 1002 bench

# --------------------------------------------------------------------------
# The pinned upstream oracle, used ONLY for the interleaved timing reference.
# It is never used to produce or repair the golden corpus at grading time: the
# golden bytes were frozen at authoring time and the judge never runs libpcap
# to decide a score.
# --------------------------------------------------------------------------
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

# --------------------------------------------------------------------------
# Hidden assets. Modes are load-bearing, not cosmetic.
#
#   cases + bench   0644  the candidate must read these to be graded at all
#   golden          0600  root only. This is the answer key.
#   manifest        0600  root only. Stratum membership is not agent-visible.
#   fingerprints    0600  root only, and it is hashes rather than source text.
# --------------------------------------------------------------------------
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

# Assert the trust boundary at BUILD time, so a broken image never ships. The
# runner must be unable to read the answer key, the stratum map, or the
# fingerprint set, and must still be able to read the cases it is graded on.
RUN set -e; \
    ! runuser -u runner -- test -r /opt/verifier/cases/golden.jsonl; \
    ! runuser -u runner -- test -r /opt/verifier/cases/manifest.json; \
    ! runuser -u runner -- test -r /opt/verifier/ref/upstream_fingerprints.json; \
    runuser -u runner -- test -r /opt/verifier/cases/hidden_cases.jsonl; \
    runuser -u runner -- test -r /opt/verifier/bench/bench_cases.jsonl; \
    echo "trust boundary asserted at build time"

# The oracle must be unreachable to the identity that runs agent code. This is
# the assertion that closes the Phase 3 Hacker finding, and it is checked at
# BUILD time so a regression can never ship.
RUN set -e; \
    ! runuser -u runner -- test -x /opt/verifier/oracle/bpfc-oracle; \
    ! runuser -u runner -- test -r /opt/verifier/oracle/bpfc-oracle; \
    ! runuser -u runner -- test -r /opt/verifier/oracle/libpcap.a; \
    runuser -u bench  -- test -x /opt/verifier/oracle/bpfc-oracle; \
    echo "oracle unreachable to runner, executable by bench"

# Assert the embedded oracle is the MUTATED one, against a behaviour literal.
# A stock-oracle image would still build and still pass every check above, then
# silently time a different compiler than the one the golden came from. The
# literal is `tcp port 80` on DLT_EN10MB at optimize=1. Stock libpcap emits the
# same INSTRUCTION COUNT, 20, and a different ORDER: it lays out the IPv6 branch
# first, the mutated compiler lays out IPv4 first. Comparing lengths would not
# catch this; comparing bytes does.
RUN set -e; \
    printf '%s\n' '{"i":0,"dlt":1,"snaplen":262144,"optimize":1,"netmask":null,"filter":"tcp port 80"}' \
      > /tmp/probe.jsonl; \
    runuser -u bench -- /opt/verifier/oracle/bpfc-oracle \
      --cases /tmp/probe.jsonl --out /tmp/probe_out.jsonl; \
    printf '%s\n' '{"i":0,"ok":true,"prog":[[40,0,0,12],[21,10,0,34525],[21,0,15,2048],[48,0,0,23],[21,0,13,6],[40,0,0,20],[69,11,0,8191],[177,0,0,14],[72,0,0,14],[21,9,0,80],[72,0,0,16],[21,7,6,80],[48,0,0,20],[21,0,4,6],[40,0,0,54],[21,3,0,80],[40,0,0,56],[21,1,0,80],[6,0,0,0],[6,0,0,262144]]}' > /tmp/probe_expected.jsonl; \
    diff -q /tmp/probe_out.jsonl /tmp/probe_expected.jsonl \
      || { echo "FATAL: embedded oracle is not the mutated build" >&2; exit 1; }; \
    rm -f /tmp/probe.jsonl /tmp/probe_out.jsonl /tmp/probe_expected.jsonl; \
    echo "embedded oracle asserted as the mutated build"

# Assert that no upstream source text reached this image. The previous revision
# shipped gencode.c here, so this check exists because the failure happened.
RUN set -e; \
    if find / -xdev \( -name 'gencode.c' -o -name 'optimize.c' -o -name 'grammar.y' \
                      -o -name 'scanner.l' -o -name 'nametoaddr.c' -o -name 'pcap.h' \
                      -o -name 'libpcap*.tar.*' \) -print -quit | grep -q .; then \
        echo "FATAL: upstream source text present in the verifier image" >&2; exit 1; \
    fi; \
    echo "no upstream source text in image"

COPY test.sh /tests/test.sh
RUN chmod 0755 /tests/test.sh

# Must equal [environment].workdir byte for byte: the submission tar is created
# relative to cwd on the work side and extracted relative to cwd here.
WORKDIR /home/workspace/bpfc

# Runs as root on purpose. test.sh drops to `runner` for every agent-authored
# execution and needs root only to read the answer key and write the reward.
USER root
ENTRYPOINT []
CMD ["/bin/bash", "/tests/test.sh"]
