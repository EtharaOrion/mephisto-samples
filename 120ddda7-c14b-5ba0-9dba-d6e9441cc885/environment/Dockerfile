# =============================================================================
# WORK image - edgebench/libpcap_bpf_codegen_fidelity
# Materializes to <bundle>/environment/Dockerfile; build context is that dir.
#
# Base is ubuntu:22.04 with the touchstones/BENCHMARK.yaml `cpp` package set,
# which is the base_image key bound in task.toml ([extensions.sforge].base_image).
#
# AGENT-VISIBLE SURFACE (seed/contract.yaml boundaries.agent_visible):
#   instruction.md, src/ (weak starter), include/, Makefile,
#   public_cases.jsonl (750 cases WITH golden outputs), score.sh,
#   etc/ (the five pinned name-resolution tables), docs/CONTRACT.md
#
# AGENT-FORBIDDEN (boundaries.agent_forbidden), enforced here or by the harness:
#   libpcap source/header/binary  -> asserted absent at build time, below
#   network egress                -> [environment].network_mode = "no-network"
#   hidden corpus + strata map    -> never enters this image; judge-image only
# =============================================================================

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# netbase is load-bearing, exactly as in the private oracle image: ubuntu:22.04
# ships NO /etc/services and NO /etc/protocols. Without it the agent's local
# score.sh would resolve `port ssh` differently from the judge, and the agent
# would be debugging against a phantom.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        make \
        cmake \
        pkg-config \
        libffi-dev \
        binutils \
        file \
        util-linux \
        git \
        curl \
        jq \
        python3 \
        sudo \
        ca-certificates \
        netbase \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash -u 1000 agent \
    && echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers \
    && git config --global safe.directory '*'

# --- ANTI-SHORTCUT: no libpcap anywhere in the work image ---------------------
# The task is to reconstruct libpcap 1.10.6 codegen from behaviour alone. If a
# pcap header or library survives in this image the agent can #include it or
# link it and the slot measures nothing. Purge, then ASSERT. The assertion is
# the point: a silent purge that stopped working would be undetectable.
RUN apt-get purge -y libpcap0.8 libpcap0.8-dev libpcap-dev 2>/dev/null || true; \
    rm -rf /usr/include/pcap /usr/include/pcap.h /usr/include/pcap-bpf.h \
           /usr/include/pcap-namedb.h /usr/include/pcap-int.h \
           /usr/local/include/pcap /usr/local/include/pcap.h; \
    find / -xdev \( -name 'libpcap.*' -o -name 'pcap.h' -o -name 'pcap-bpf.h' \) \
         -not -path '/proc/*' -delete 2>/dev/null || true; \
    LEFT="$(find / -xdev \( -name 'libpcap*' -o -name 'pcap.h' -o -name 'pcap-bpf.h' \) \
             -not -path '/proc/*' 2>/dev/null)"; \
    if [ -n "$LEFT" ]; then echo "FATAL: libpcap artefacts survive in the work image:"; \
      echo "$LEFT"; exit 1; fi; \
    echo "verified: no libpcap header, library, or binary in the work image"

# --- Pinned name-resolution tables -------------------------------------------
# corpus.determinism_pins: the five tables must be byte-identical in the work
# image, the judge image, and the private oracle image that produced the golden
# corpus. These digests are the ones the oracle image recorded at
# /pinned/etc/SHA256SUMS. A drifting table silently changes the golden bytes for
# every `port ssh` / `proto tcp` / `host localhost` case, so a mismatch is a
# build failure, never a warning.
#
# NOTE on /etc/hosts: Docker bind-mounts /etc/hosts at RUNTIME, so the copy
# baked in here is overwritten in the running container. It is still pinned in
# the image so the file is present, auditable, and hash-checkable; the runtime
# restore is the verifier's job (tests/test.sh Step 0).
COPY etc/services  /opt/pinned_etc/services
COPY etc/protocols /opt/pinned_etc/protocols
COPY etc/hosts     /opt/pinned_etc/hosts
COPY etc/networks  /opt/pinned_etc/networks
COPY etc/ethers    /opt/pinned_etc/ethers
RUN printf '%s\n' \
      "f6183055fd949f9c53d49ee620f85d0150123ea691d25ed1bba0c641b4ee2f48  /opt/pinned_etc/services" \
      "a90a2be9c2a88be6fbfc1fc73ba76f34698377bb19513e5de503dbb0bfe13be1  /opt/pinned_etc/protocols" \
      "f969610b9f4ed5f29917185f0dcf4a611dc618e9918a61504baf5dbb7b187a1a  /opt/pinned_etc/hosts" \
      "20f4b0486ba8a442644f0f10fc1c947db554c83f31037d6a2ba9be8d67998c25  /opt/pinned_etc/networks" \
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  /opt/pinned_etc/ethers" \
      > /opt/pinned_etc/SHA256SUMS \
 && sha256sum -c /opt/pinned_etc/SHA256SUMS \
 && for f in services protocols hosts networks ethers; do \
        cp "/opt/pinned_etc/$f" "/etc/$f"; \
    done

# --- Workspace ---------------------------------------------------------------
# /home/workspace/bpfc is byte-identical to [environment].workdir and to
# [verifier.environment].workdir in task.toml (boundaries.workdir_rule).
RUN mkdir -p /home/workspace/bpfc

WORKDIR /home/workspace/bpfc

# The weak starter. src/, include/ and Makefile are exactly the three
# submit_paths, so the submission tar always has all three to archive.
# include/ MUST exist and MUST be non-empty even if the starter needs no public
# header: harness/sforge/harness/run_agent.py line 182 runs
#   tar czf ... src/ include/ Makefile
# with no existence filter, and a missing path makes tar exit non-zero.
COPY src/     /home/workspace/bpfc/src/
COPY include/ /home/workspace/bpfc/include/
COPY Makefile /home/workspace/bpfc/Makefile

# Agent-visible evaluation surface. public_cases.jsonl carries its own golden
# outputs (750 cases, disjoint generator seeds from the hidden 12,000, NOT the same
# strata proportions). score.sh mirrors the judge's field names and strata table
# but never sees hidden data.
COPY public_cases.jsonl /home/workspace/bpfc/public_cases.jsonl
COPY score.sh           /home/workspace/bpfc/score.sh
COPY docs/CONTRACT.md   /home/workspace/bpfc/docs/CONTRACT.md
RUN cp -r /opt/pinned_etc /home/workspace/bpfc/etc \
 && chmod +x /home/workspace/bpfc/score.sh

# The starter must build in this image before the agent ever touches it. If
# `make clean && make -j4` does not yield ./bpfc here it will not yield it in
# the judge either, and every submission would grade build_failed.
RUN make clean && make -j4 && test -x /home/workspace/bpfc/bpfc \
 && ./bpfc --cases /dev/null --out /tmp/_smoke.jsonl \
 && make clean

RUN chown -R agent:agent /home/workspace

USER agent
CMD ["/bin/bash"]
