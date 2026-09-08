# 62b54382-a910-5b29-ad0e-1efa993cc615

Rebuild libpcap 1.10.6's BPF filter compiler in C from observable behaviour alone — no libpcap
source, headers, binary, documentation, or network. The submitted program reads
`(dlt, snaplen, optimize, netmask, filter)` cases as JSON and must emit, for each one, either the
exact classic BPF instruction sequence libpcap 1.10.6 produces or the exact error string it
produces on rejection. Exactness is the entire task: one wrong jump offset, immediate value, or
error word is scored as wrong.

## Hidden set

12,000 hidden cases across 8 weighted strata, graded on exact cBPF bytecode tuple equality and
exact error-string equality, plus a gated interleaved compile-throughput term. The only evidence
about the target behaviour is the 2,000-case public corpus in the working directory
(`public_cases.jsonl`), which carries real golden outputs. This is an excavation task: the graded
value is not what a correct filter "should" look like, it is what libpcap 1.10.6 actually emitted.

## Invocation contract

```
./bpfc --cases <in.jsonl> --out <out.jsonl>
./bpfc --bench <in.jsonl> --reps N
```

The judge runs `make clean && make -j4` in the submission root and invokes the binary that build
produced — a shipped binary is never trusted or graded. One binary must answer both invocation
forms. `docs/CONTRACT.md` is normative for every field, type, ordering, and exit code, and is
identical to the contract the reference answers, so a correct implementation is indistinguishable
from the reference at the process boundary.

Name lookups resolve exclusively from the five pinned resolution tables under `etc/` (one is
legitimately empty by design); nothing ever resolves over the network.

## Environment

- Work image: `mephisto/bpfc-work` (pinned by digest), no network, 8 cpus, 6 GB, workdir
  `/home/workspace/bpfc`, 12-hour agent envelope.
- Judge image: `mephisto/bpfc-judge` (pinned by digest), separate container, no network,
  15-minute verifier envelope.
- Submission whitelist: `src/`, `include/`, `Makefile`. Build artifacts, caches, and the public
  corpus are excluded from the archive.
- Optimization lane: up to 50 attempts inside the 12-hour envelope, best score kept,
  `score_direction = maximize`.

## Working directory

```
src/ include/ Makefile      starter C11 implementation — this and only this is submitted
public_cases.jsonl          2,000 public cases with golden outputs and stratum names
score.sh                    local scorer mirroring the judge's field names, per-case rules,
                            and stratum table over the public corpus
docs/CONTRACT.md            the JSON invocation contract, restated in full and normatively
etc/                        the five name-resolution tables, pinned byte-identically
```

## Layout

```
task.toml            task contract; images pinned by digest
instruction.md       agent-facing specification
environment/         work image: Dockerfile plus the starter workspace above
tests/               judge image: Dockerfile, hidden_test_data, scoring, test.sh,
                     test_output.py, rubrics.jsonl
solution/            private oracle tree: TRUTH.md, rubrics.json, solve.sh
trajectory/          recorded run
plots/               trajectory plots
inspect.html         bundle inspector
```
