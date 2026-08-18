FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8


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

RUN mkdir -p /home/workspace/bpfc

WORKDIR /home/workspace/bpfc

COPY src/     /home/workspace/bpfc/src/
COPY include/ /home/workspace/bpfc/include/
COPY Makefile /home/workspace/bpfc/Makefile

COPY public_cases.jsonl /home/workspace/bpfc/public_cases.jsonl
COPY score.sh           /home/workspace/bpfc/score.sh
COPY docs/CONTRACT.md   /home/workspace/bpfc/docs/CONTRACT.md
RUN cp -r /opt/pinned_etc /home/workspace/bpfc/etc \
 && chmod +x /home/workspace/bpfc/score.sh

RUN make clean && make -j4 && test -x /home/workspace/bpfc/bpfc \
 && ./bpfc --cases /dev/null --out /tmp/_smoke.jsonl \
 && make clean

RUN chown -R agent:agent /home/workspace

USER agent
CMD ["/bin/bash"]
