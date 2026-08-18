#!/bin/sh

set -eu

BUILD=1
[ "${1:-}" = "--no-build" ] && BUILD=0

cd "$(dirname "$0")"

if [ "$BUILD" -eq 1 ]; then
    make clean >/dev/null 2>&1 || true
    make -j4 || { echo "score.sh: build failed"; exit 1; }
fi

[ -x ./bpfc ] || { echo "score.sh: ./bpfc not found or not executable"; exit 1; }

./bpfc --cases public_cases.jsonl --out /tmp/score_out.jsonl

python3 - public_cases.jsonl /tmp/score_out.jsonl <<'PY'
import json, sys, collections

WEIGHTS = {
    "basic-proto": 0.12, "host-net-addr": 0.12, "port-portrange": 0.10,
    "boolean-nesting": 0.12, "byte-slice-arith": 0.12,
    "link-layer-and-encap": 0.12, "error-paths": 0.18, "optimizer-only": 0.12,
}
SCORE_EXACT_PROG, SCORE_SIMILAR_SCALE = 1.00, 0.60
SCORE_EXACT_ERR, SCORE_OTHER_ERR = 1.00, 0.45
FLOOR_PROGRAM = [[6, 0, 0, 0]]


def similarity(a, b):
    """Normalized sequence similarity over instruction 4-tuples."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    ta = [tuple(x) for x in a]
    tb = [tuple(x) for x in b]
    # Longest common subsequence, length-normalized.
    n, m = len(ta), len(tb)
    prev = [0] * (m + 1)
    for i in range(1, n + 1):
        cur = [0] * (m + 1)
        for j in range(1, m + 1):
            cur[j] = prev[j - 1] + 1 if ta[i - 1] == tb[j - 1] else max(prev[j], cur[j - 1])
        prev = cur
    return 2.0 * prev[m] / (n + m)


def floor_corrected(cand, gold):
    sim = similarity(cand, gold)
    base = similarity(FLOOR_PROGRAM, gold)
    if base >= 1.0:
        return 0.0
    return max(0.0, (sim - base) / (1.0 - base))


cases = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
got = {}
for l in open(sys.argv[2]):
    if l.strip():
        r = json.loads(l)
        got[r["i"]] = r

per_stratum = collections.defaultdict(list)
counts = collections.Counter()

for c in cases:
    exp = c["expected"]
    r = got.get(c["i"])
    s = 0.0
    if r is None:
        counts["absent"] += 1
    elif exp["ok"]:
        if not r.get("ok"):
            counts["compiled_got_error"] += 1
        elif r.get("prog") == exp["prog"]:
            s = SCORE_EXACT_PROG
            counts["compiled_exact"] += 1
        else:
            s = SCORE_SIMILAR_SCALE * floor_corrected(r.get("prog") or [], exp["prog"])
            counts["compiled_similar"] += 1
    else:
        if r.get("ok"):
            counts["rejected_got_ok"] += 1
        elif r.get("err") == exp["err"]:
            s = SCORE_EXACT_ERR
            counts["rejected_exact_err"] += 1
        else:
            s = SCORE_OTHER_ERR
            counts["rejected_other_err"] += 1
    per_stratum[c["stratum"]].append(s)

C = 0.0
print()
print("  %-24s %6s %6s %8s" % ("stratum", "weight", "n", "mean"))
for name in sorted(WEIGHTS):
    vals = per_stratum.get(name, [])
    mean = sum(vals) / len(vals) if vals else 0.0
    C += WEIGHTS[name] * mean
    print("  %-24s %6.2f %6d %8.4f" % (name, WEIGHTS[name], len(vals), mean))

n_exact = counts["compiled_exact"] + counts["rejected_exact_err"]
print()
print("  C (conformance)   = %.6f" % C)
print("  R if P were zero  = %.6f" % (0.88 * C))
print("  byte-exact cases  = %d / %d" % (n_exact, len(cases)))
print()
print("  outcome counts:")
for k in sorted(counts):
    print("    %-22s %d" % (k, counts[k]))
print()
print("  Throughput is NOT modelled here. The judge charges it against")
print("  byte-exact cases only, so it earns nothing until conformance rises.")
PY
