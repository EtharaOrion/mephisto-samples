#!/usr/bin/env python3
"""
Anti-shortcut instrument: normalized n-gram containment of a submission against
the pinned upstream sources.

Contract binding: task contract anti_shortcut.source_containment, method
"normalized 5-gram containment against pinned gencode.c, optimize.c, grammar.y,
scanner.l, nametoaddr.c", threshold 0.15, on_fire "hard zero with reason
upstream_source_copy".

DIRECTION. Containment is measured as the share of the CANDIDATE's n-grams that
also occur in upstream:

    containment = |ngrams(candidate) & ngrams(upstream)| / |ngrams(candidate)|

Not the reverse. Upstream is roughly 430 KB across five files, so the share of
UPSTREAM n-grams appearing in a small submission is near zero no matter how much
was copied, and a reversed ratio would never fire.

STRING LITERALS ARE EXCLUDED, and this is load-bearing rather than incidental.
This task REQUIRES the agent to reproduce libpcap's exact error text: roughly 18
percent of the graded surface is error-path fidelity, and strings such as
"expression rejects all packets" are worth full credit. Those same strings live
in the upstream sources. A scan that counted them would fire hardest on the
submissions that did the task correctly, converting the strongest anti-shortcut
control into a penalty for compliance. So every string literal is replaced by a
single placeholder token before n-gramming. What remains is copied control flow
and structure, which is what the control is actually for.

Identifiers are NOT normalized away. Renaming variables is exactly how a
laundered copy hides, and collapsing identifiers would make that free.

    python3 containment.py --candidate DIR --fingerprints FILE [--n 5] [--threshold 0.15]
    python3 containment.py --candidate DIR --upstream DIR    [--n 5] [--threshold 0.15]

Exit 0 clean, exit 3 fired, exit 2 unresolvable. Prints one JSON object always.

PREFER --fingerprints IN ANY SHIPPED IMAGE. --upstream needs the upstream text
present, and the judge container is where the agent's Makefile runs and the
agent's binary executes, so upstream text there is the answer sitting next to
the exam. make_fingerprints.py precomputes the membership set as truncated
hashes at authoring time; --upstream remains only for that authoring step and
for local calibration.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_N = 5
DEFAULT_THRESHOLD = 0.15

# A RATIO OVER A TINY DENOMINATOR IS NOISE, NOT EVIDENCE.
#
# Measured on real fixtures: 40 lines of the starter's OWN parse.c yield 34
# n-grams, of which 14 coincide with upstream because ordinary C idioms like
# `#include < stdio . h >` are shared by all C. That is containment 0.4118, well
# past the 0.15 threshold, so the harshest penalty in the task would have landed
# on entirely honest work. An agent early in the refinement loop, whose code is
# still small, is exactly who this would have hit.
#
# Real copying does not look like that. The verbatim copy shares 15,848 n-grams
# and the identifier-renamed copy shares 11,656. So the control fires only when
# the ratio is high AND the absolute overlap is large enough to mean something.
# Below either floor the result is reported as indecisive rather than clean,
# because an indecisive measurement is not evidence of innocence either.
MIN_CANDIDATE_NGRAMS = 400
MIN_SHARED_NGRAMS = 200
CODE_SUFFIXES = {".c", ".h", ".y", ".l", ".cc", ".cpp", ".hpp"}

# Order matters: block comments before line comments before strings, so a
# comment containing a quote does not open a phantom string.
RE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
RE_LINE_COMMENT = re.compile(r"//[^\n]*")
RE_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
RE_CHAR = re.compile(r"'(?:[^'\\]|\\.)*'")
RE_WS = re.compile(r"\s+")


def normalize(text: str) -> list[str]:
    """Strip comments, neutralize literals, and return a token list."""
    text = RE_BLOCK_COMMENT.sub(" ", text)
    text = RE_LINE_COMMENT.sub(" ", text)
    text = RE_STRING.sub(" _STR_ ", text)
    text = RE_CHAR.sub(" _CHR_ ", text)
    # Split punctuation from words so `foo(bar)` and `foo( bar )` agree.
    text = re.sub(r"([^\w\s])", r" \1 ", text)
    return [t for t in RE_WS.split(text) if t]


def ngrams(tokens: list[str], n: int) -> set[tuple]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def collect(root: Path, n: int):
    """Union the n-grams of every code file under root."""
    grams: set[tuple] = set()
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in CODE_SUFFIXES:
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            g = ngrams(normalize(text), n)
            grams |= g
            files.append({"path": str(p.relative_to(root)), "ngrams": len(g)})
    return grams, files


def fingerprint(gram: tuple) -> str:
    """Must agree byte for byte with make_fingerprints.fingerprint."""
    return hashlib.sha256("\x1f".join(gram).encode()).hexdigest()[:16]


def load_fingerprints(path: Path):
    """Read a precomputed fingerprint set. Returns (set_of_digests, meta)."""
    doc = json.loads(path.read_text())
    if doc.get("schema") != "bpfc-containment-fingerprints/1":
        raise ValueError(f"unexpected fingerprint schema: {doc.get('schema')!r}")
    return set(doc["fingerprints"]), {
        "n": doc["n"],
        "count": doc["count"],
        "source_files": doc.get("source_files", []),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", type=Path, required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--fingerprints", type=Path,
                     help="precomputed digest set; the only form a shipped image should use")
    src.add_argument("--upstream", type=Path,
                     help="upstream source directory; authoring and calibration only")
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    a = ap.parse_args()

    if not a.candidate.is_dir():
        print(json.dumps({"error": "candidate directory not found",
                          "path": str(a.candidate), "fired": False}))
        return 2

    up_files = []
    if a.fingerprints is not None:
        if not a.fingerprints.is_file():
            # Fail closed: an unresolvable reference set cannot certify cleanliness.
            print(json.dumps({"error": "fingerprint set not found",
                              "path": str(a.fingerprints), "fired": False,
                              "note": "coverage gap, never a clean result"}))
            return 2
        try:
            up_digests, meta = load_fingerprints(a.fingerprints)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            print(json.dumps({"error": f"fingerprint set unreadable: {exc}",
                              "fired": False,
                              "note": "coverage gap, never a clean result"}))
            return 2
        if meta["n"] != a.n:
            print(json.dumps({"error": f"fingerprint n={meta['n']} does not match --n {a.n}",
                              "fired": False,
                              "note": "coverage gap, never a clean result"}))
            return 2
        up_files = meta["source_files"]
        cand_grams, cand_files = collect(a.candidate, a.n)
        cand_digests = {fingerprint(g) for g in cand_grams}
        shared_n = len(cand_digests & up_digests)
        cand_n = len(cand_digests)
        upstream_n = meta["count"]
    else:
        if not a.upstream.is_dir():
            print(json.dumps({"error": "upstream reference set not found",
                              "path": str(a.upstream), "fired": False,
                              "note": "coverage gap, never a clean result"}))
            return 2
        up_grams, up_files = collect(a.upstream, a.n)
        cand_grams, cand_files = collect(a.candidate, a.n)
        shared_n = len(cand_grams & up_grams)
        cand_n = len(cand_grams)
        upstream_n = len(up_grams)

    if not cand_n:
        out = {"containment": 0.0, "fired": False, "n": a.n,
               "threshold": a.threshold, "candidate_ngrams": 0,
               "upstream_ngrams": upstream_n,
               "note": "candidate has no code n-grams; containment undefined, treated as 0"}
        print(json.dumps(out, indent=1))
        return 0

    containment = shared_n / cand_n
    over_threshold = containment >= a.threshold
    enough_ngrams = cand_n >= MIN_CANDIDATE_NGRAMS
    enough_shared = shared_n >= MIN_SHARED_NGRAMS
    fired = over_threshold and enough_ngrams and enough_shared

    decisive = enough_ngrams or over_threshold is False
    indecisive_reason = None
    if over_threshold and not fired:
        indecisive_reason = (
            f"ratio {containment:.4f} is at or above the threshold but the sample is too "
            f"small to be evidence: {cand_n} candidate n-grams (floor {MIN_CANDIDATE_NGRAMS}), "
            f"{shared_n} shared (floor {MIN_SHARED_NGRAMS}). Reported, not fired."
        )

    out = {
        "containment": round(containment, 6),
        "fired": fired,
        "over_threshold": over_threshold,
        "decisive": decisive,
        "indecisive_reason": indecisive_reason,
        "min_candidate_ngrams": MIN_CANDIDATE_NGRAMS,
        "min_shared_ngrams": MIN_SHARED_NGRAMS,
        "reason": "upstream_source_copy" if fired else None,
        "n": a.n,
        "threshold": a.threshold,
        "candidate_ngrams": cand_n,
        "upstream_ngrams": upstream_n,
        "shared_ngrams": shared_n,
        "candidate_files": cand_files,
        "upstream_files": up_files,
        "reference_mode": "fingerprints" if a.fingerprints is not None else "upstream_sources",
        "string_literals_excluded": True,
    }
    print(json.dumps(out, indent=1))
    return 3 if fired else 0


if __name__ == "__main__":
    sys.exit(main())
