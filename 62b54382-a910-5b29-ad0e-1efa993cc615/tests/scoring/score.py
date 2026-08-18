#!/usr/bin/env python3
"""Judge-side scorer for libpcap_bpf_codegen_fidelity.

Pure Python 3.11 standard library. No third-party imports.

    python3 score.py --golden golden.jsonl --candidate out.jsonl \
                     --manifest manifest.json --out reward.json \
                     [--reward-txt reward.txt] \
                     [--bench-candidate f.json --bench-upstream f.json]

Implements the frozen reward from the task contract verbatim:

    R = clip(0.88 * C + 0.12 * P * min(1, C / 0.25), 0, 1)

    per case, when upstream COMPILED the case:
        exact prog tuple-sequence equality             -> 1.00
        structurally valid but different               -> 0.60 * fcs
        invalid (fails structural validator) or absent -> 0.00
    per case, when upstream REJECTED the case:
        exact err string equality -> 1.00
        any other err string      -> 0.45
        returned ok               -> 0.00

    C = weighted mean of per-case scores over the 8 strata
    P = clip(ln(r/0.5) / ln(4.0/0.5), 0, 1),
        r = median(t_upstream) / median(t_candidate),
        3 discarded warmups then 5 timed trials, interleaved,
        dead zone r <= 1.05 scores 0

The formula is transcribed, never re-derived. `fcs` is
similarity.floor_corrected_similarity; the structural gate is
validator.validate.

reward.txt
----------
Exactly one bare decimal in [0, 1]: no label, no trailing newline, no
scientific notation, fixed 6 decimal places. This is load-bearing.
harness/sforge/harness/harbor_loader.py line 61 does

    SCORE=$(cat /logs/verifier/reward.txt 2>/dev/null | tr -dc '0-9.-' || echo 0)

and interpolates $SCORE straight into a JSON document. `tr -dc '0-9.-'`
keeps only digits, dot and minus, so any exponent ("1e-05" -> "1-05") or
stray sign would produce invalid JSON or a silently wrong score. The
formatter below is fixed-point, non-negative and clipped, and it is
regression-tested in test_score.py.

Graded failure modes
--------------------
Every one of the following is a graded outcome carrying a machine-readable
reason. None of them raises.

  missing candidate file      -> hard zero, reason empty_submission
  candidate with no records   -> hard zero, reason empty_submission
  unparseable line (mid-file) -> hard zero, reason malformed_output
  duplicate i                 -> hard zero, reason malformed_output
  unknown i                   -> hard zero, reason malformed_output
  out-of-order record         -> hard zero, reason malformed_output
  extra records               -> hard zero, reason malformed_output
  truncated candidate         -> NOT a hard zero. A file whose final line is
                                 incomplete (no terminating newline, does not
                                 parse) is truncation, not corruption: the
                                 records that did arrive are graded, and every
                                 absent case takes the contract's own
                                 "absent -> 0.00" cell. Recorded as the
                                 non-fatal note `truncated_output`.
  short/wrong record count    -> same treatment: absent cases score 0.00 and
                                 the note `record_count_mismatch` is recorded.

The split is deliberate. The per-case table has an explicit cell for an
absent record, so a short file must be graded through that cell rather than
collapsed to a hard zero; but the output contract fixes the record *envelope*
and its ordering, so a violated envelope is `malformed_output`, which the
contract lists as a hard-zero reason. Pass --lenient to downgrade envelope
violations to per-case zeros for calibration runs.

Hard-zero reasons are exactly the frozen seven: empty_submission,
build_failed, link_denylist, upstream_source_copy, harness_tamper, timeout,
malformed_output. The five that are detected outside this process (a failed
build, a denylisted dynamic import, an upstream-source containment hit, a
tampered harness, a timeout) are injected by the wrapper via --force-reason.

Feedback redaction
------------------
reward.json carries aggregates only: per-stratum breakdown, per-case counts
by outcome class, validator-rejection reason histogram, and every individual
timing trial. It deliberately carries NO per-case golden bytes, no per-case
diffs and no per-case stratum membership, because the task contract
anti_shortcut.feedback_redaction forbids returning those to the agent and a
50-iteration refinement loop would otherwise binary-search the hidden corpus.
Per-case detail is available only via --per-case-json, which is judge-only
and must never be surfaced to the solver.

No wall-clock timestamp is written, so reward.json is byte-reproducible for
a given input triple.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import traceback
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from similarity import floor_corrected_similarity  # noqa: E402
from validator import validate as validate_program  # noqa: E402

# --------------------------------------------------------------------------
# Frozen constants. Transcribed from the task contract; do not re-derive.
# --------------------------------------------------------------------------

REWARD_FORMULA = "R = clip(0.88*C + 0.12*P*min(1, C/0.25), 0, 1)"

W_CORRECTNESS = 0.88
W_THROUGHPUT = 0.12
CORRECTNESS_GATE_C = 0.25

SCORE_EXACT_PROG = 1.00
SCORE_SIMILAR_COEFF = 0.60
SCORE_INVALID_OR_ABSENT = 0.00
SCORE_ERR_EXACT = 1.00
SCORE_ERR_OTHER = 0.45
SCORE_ERR_RETURNED_OK = 0.00

P_R_LO = 0.5
P_R_HI = 4.0
P_DEAD_ZONE_R = 1.05
BENCH_WARMUPS = 3
BENCH_TIMED_TRIALS = 5

STRATUM_WEIGHTS: dict[str, float] = {
    "basic-proto": 0.12,
    "host-net-addr": 0.12,
    "port-portrange": 0.10,
    "boolean-nesting": 0.12,
    "byte-slice-arith": 0.12,
    "link-layer-and-encap": 0.12,
    "error-paths": 0.18,
    "optimizer-only": 0.12,
}

HARD_ZERO_REASONS = (
    "empty_submission",
    "build_failed",
    "link_denylist",
    "upstream_source_copy",
    "harness_tamper",
    "timeout",
    "malformed_output",
)

OUTCOME_CLASSES = (
    "compiled_exact",
    "compiled_similar",
    "compiled_invalid",
    "compiled_got_error",
    "compiled_absent",
    "rejected_exact_err",
    "rejected_other_err",
    "rejected_got_ok",
    "rejected_absent",
)

UNASSIGNED_STRATUM = "unassigned"
SCHEMA = "libpcap_bpf_codegen_fidelity/reward/1"


class GradedFailure(Exception):
    """A graded, non-crashing failure carrying a frozen hard-zero reason."""

    def __init__(self, reason: str, detail: str = ""):
        if reason not in HARD_ZERO_REASONS:
            raise ValueError(f"reason {reason!r} is not a frozen hard-zero reason")
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


# --------------------------------------------------------------------------
# reward.txt formatting
# --------------------------------------------------------------------------

def format_reward(value: float) -> str:
    """Render the reward as a bare fixed-point decimal in [0, 1].

    Survives `tr -dc '0-9.-'` unchanged. Never emits an exponent, a sign, a
    label or whitespace. NaN and infinities collapse to 0.000000 rather than
    producing 'nan'/'inf', which `tr` would erase into an empty $SCORE.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    if not math.isfinite(v):
        v = 0.0
    if v < 0.0:
        v = 0.0
    elif v > 1.0:
        v = 1.0
    text = f"{v:.6f}"
    # Defensive: the contract on this string is stricter than the format spec.
    assert "e" not in text and "E" not in text, text
    assert "-" not in text and "+" not in text, text
    assert text.count(".") == 1, text
    return text


def write_reward_txt(path: str, value: float) -> None:
    payload = format_reward(value)
    _ensure_parent(path)
    with open(path, "w", encoding="ascii", newline="") as fh:
        fh.write(payload)


def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


# --------------------------------------------------------------------------
# Input loading
# --------------------------------------------------------------------------

def _read_text(path: str) -> str:
    with open(path, "rb") as fh:
        raw = fh.read()
    # errors="replace" so a truncated multibyte sequence degrades into a
    # JSON parse error on that one line instead of an exception here.
    return raw.decode("utf-8", errors="replace")


def load_manifest(path: str) -> dict[str, Any]:
    """Load the case manifest.

    Canonical shape:

        {"task_id": ..., "n_cases": N,
         "strata": [{"name": "basic-proto", "weight": 0.12}, ...],
         "cases":  [{"i": 0, "stratum": "basic-proto"}, ...]}

    Also accepted, because the generator is not written yet and the manifest
    schema was never frozen:
      strata as {"basic-proto": 0.12, ...} or as a bare list of names;
      membership as "case_strata": {"0": "basic-proto", ...}
                 or "strata_members": {"basic-proto": [0, 1, 2], ...}.
    Absent weights fall back to the frozen 8-stratum table.
    """
    if not os.path.exists(path):
        raise GradedFailure("harness_tamper", f"manifest not found: {path}")
    try:
        doc = json.loads(_read_text(path))
    except (ValueError, OSError) as exc:
        raise GradedFailure("harness_tamper", f"manifest unreadable: {exc}") from exc
    if not isinstance(doc, dict):
        raise GradedFailure("harness_tamper", "manifest is not a JSON object")

    notes: list[str] = []

    weights: dict[str, float] = {}
    raw_strata = doc.get("strata")
    if isinstance(raw_strata, dict):
        for name, w in raw_strata.items():
            if isinstance(w, (int, float)) and not isinstance(w, bool):
                weights[str(name)] = float(w)
    elif isinstance(raw_strata, list):
        for entry in raw_strata:
            if isinstance(entry, dict) and "name" in entry:
                name = str(entry["name"])
                w = entry.get("weight", STRATUM_WEIGHTS.get(name))
                if isinstance(w, (int, float)) and not isinstance(w, bool):
                    weights[name] = float(w)
                elif name in STRATUM_WEIGHTS:
                    weights[name] = STRATUM_WEIGHTS[name]
            elif isinstance(entry, str) and entry in STRATUM_WEIGHTS:
                weights[entry] = STRATUM_WEIGHTS[entry]
    if not weights:
        weights = dict(STRATUM_WEIGHTS)
        notes.append("manifest_missing_strata_weights")

    stratum_of: dict[int, str] = {}
    snaplen_of: dict[int, int] = {}
    order: list[int] = []

    cases = doc.get("cases")
    if isinstance(cases, list) and cases:
        for entry in cases:
            if not isinstance(entry, dict) or "i" not in entry:
                continue
            try:
                idx = int(entry["i"])
            except (TypeError, ValueError):
                continue
            order.append(idx)
            s = entry.get("stratum", entry.get("name"))
            if isinstance(s, str):
                stratum_of[idx] = s
            sl = entry.get("snaplen")
            if isinstance(sl, int) and not isinstance(sl, bool):
                snaplen_of[idx] = sl
    else:
        cs = doc.get("case_strata")
        if isinstance(cs, dict):
            for key, s in cs.items():
                try:
                    idx = int(key)
                except (TypeError, ValueError):
                    continue
                if isinstance(s, str):
                    stratum_of[idx] = s
        members = doc.get("strata_members")
        if isinstance(members, dict):
            for name, idxs in members.items():
                if not isinstance(idxs, list):
                    continue
                for raw in idxs:
                    try:
                        stratum_of[int(raw)] = str(name)
                    except (TypeError, ValueError):
                        continue

    if not stratum_of:
        notes.append("manifest_missing_case_strata")

    return {
        "weights": weights,
        "stratum_of": stratum_of,
        "snaplen_of": snaplen_of,
        "order": order,
        "n_cases": doc.get("n_cases"),
        "task_id": doc.get("task_id"),
        "notes": notes,
    }


def load_golden(path: str) -> tuple[list[int], dict[int, dict[str, Any]], list[str]]:
    """Load the golden corpus. The golden file is trusted input."""
    if not os.path.exists(path):
        raise GradedFailure("harness_tamper", f"golden not found: {path}")
    try:
        text = _read_text(path)
    except OSError as exc:
        raise GradedFailure("harness_tamper", f"golden unreadable: {exc}") from exc

    order: list[int] = []
    records: dict[int, dict[str, Any]] = {}
    notes: list[str] = []

    for lineno, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError as exc:
            raise GradedFailure(
                "harness_tamper", f"golden line {lineno} does not parse: {exc}"
            ) from exc
        if not isinstance(rec, dict) or "i" not in rec or "ok" not in rec:
            raise GradedFailure("harness_tamper", f"golden line {lineno} malformed")
        try:
            idx = int(rec["i"])
        except (TypeError, ValueError) as exc:
            raise GradedFailure(
                "harness_tamper", f"golden line {lineno} has non-integer i"
            ) from exc
        if idx in records:
            raise GradedFailure("harness_tamper", f"golden has duplicate i={idx}")
        records[idx] = rec
        order.append(idx)

    if not order:
        raise GradedFailure("harness_tamper", "golden corpus is empty")
    return order, records, notes


# --------------------------------------------------------------------------
# Candidate loading -- the fragile path, and the one that must never crash
# --------------------------------------------------------------------------

def load_candidate(path: str, expected_order: list[int], lenient: bool):
    """Parse the candidate output stream against the frozen output contract.

    Returns (records, notes, stats). Raises GradedFailure for envelope
    violations, which the contract classifies as malformed_output.
    """
    if not os.path.exists(path):
        raise GradedFailure("empty_submission", f"candidate output not found: {path}")

    try:
        text = _read_text(path)
    except OSError as exc:
        raise GradedFailure(
            "malformed_output", f"candidate unreadable: {exc}"
        ) from exc

    notes: list[str] = []
    if text == "" or not text.strip():
        raise GradedFailure("empty_submission", "candidate output is empty")

    ends_with_newline = text.endswith("\n")
    segments = text.split("\n")
    if ends_with_newline:
        segments = segments[:-1]

    expected_set = set(expected_order)
    records: dict[int, dict[str, Any]] = {}
    seen_order: list[int] = []
    truncated = False
    last_index = len(segments) - 1

    for pos, line in enumerate(segments):
        if not line.strip():
            continue
        is_last_segment = pos == last_index
        try:
            rec = json.loads(line)
        except ValueError as exc:
            if is_last_segment and not ends_with_newline:
                # Classic truncation signature: the writer died mid-line.
                # Graded through the contract's "absent -> 0.00" cell.
                truncated = True
                notes.append("truncated_output")
                break
            raise GradedFailure(
                "malformed_output",
                f"line {pos + 1} is not valid JSON: {exc}",
            ) from exc

        idx, envelope_error = _check_envelope(rec, pos)
        if envelope_error is not None:
            if lenient:
                notes.append(f"lenient_skipped_line_{pos + 1}")
                continue
            raise GradedFailure("malformed_output", envelope_error)

        if idx not in expected_set:
            msg = f"line {pos + 1} carries i={idx}, which is not a graded case"
            if lenient:
                notes.append("unknown_i")
                continue
            raise GradedFailure("malformed_output", msg)
        if idx in records:
            msg = f"line {pos + 1} repeats i={idx}"
            if lenient:
                notes.append("duplicate_i")
                continue
            raise GradedFailure("malformed_output", msg)

        position = len(seen_order)
        if position >= len(expected_order):
            msg = (
                f"line {pos + 1} is record {position + 1} but only "
                f"{len(expected_order)} cases are graded"
            )
            if lenient:
                notes.append("extra_records")
                continue
            raise GradedFailure("malformed_output", msg)
        if not lenient and idx != expected_order[position]:
            raise GradedFailure(
                "malformed_output",
                f"out-of-order record at line {pos + 1}: got i={idx}, "
                f"expected i={expected_order[position]}",
            )

        records[idx] = rec
        seen_order.append(idx)

    if not records:
        raise GradedFailure(
            "empty_submission", "candidate output carries no usable records"
        )

    missing = len(expected_order) - len(records)
    if missing > 0 and not truncated:
        notes.append("record_count_mismatch")

    stats = {
        "lines": len(segments),
        "parsed": len(records),
        "expected": len(expected_order),
        "missing": missing,
        "truncated": truncated,
        "ends_with_newline": ends_with_newline,
    }
    return records, notes, stats


def _check_envelope(rec: Any, pos: int) -> tuple[int | None, str | None]:
    """Validate the record envelope. Payload content is graded, not fatal."""
    where = f"line {pos + 1}"
    if not isinstance(rec, dict):
        return None, f"{where} is not a JSON object"
    if "i" not in rec:
        return None, f"{where} has no 'i' field"
    raw_i = rec["i"]
    if isinstance(raw_i, bool) or not isinstance(raw_i, int):
        return None, f"{where} has a non-integer 'i'"
    if "ok" not in rec:
        return raw_i, f"{where} has no 'ok' field"
    if not isinstance(rec["ok"], bool):
        return raw_i, f"{where} has a non-boolean 'ok'"
    if rec["ok"]:
        if "prog" not in rec:
            return raw_i, f"{where} is ok:true but has no 'prog'"
    else:
        if "err" not in rec:
            return raw_i, f"{where} is ok:false but has no 'err'"
        if not isinstance(rec["err"], str):
            return raw_i, f"{where} has a non-string 'err'"
    return raw_i, None


# --------------------------------------------------------------------------
# Per-case scoring
# --------------------------------------------------------------------------

def _prog_tuples(prog: Any):
    """Exact 4-tuple sequence, or None when the payload is not a program."""
    if not isinstance(prog, list):
        return None
    out = []
    for ins in prog:
        if not isinstance(ins, list) or len(ins) != 4:
            return None
        vals = []
        for v in ins:
            if isinstance(v, bool) or not isinstance(v, int):
                return None
            vals.append(v)
        out.append(tuple(vals))
    return tuple(out)


def score_case(golden_rec, cand_rec, snaplen=None):
    """Score one case. Returns (score, outcome_class, detail)."""
    golden_ok = bool(golden_rec.get("ok"))

    if cand_rec is None:
        if golden_ok:
            return SCORE_INVALID_OR_ABSENT, "compiled_absent", None
        return SCORE_INVALID_OR_ABSENT, "rejected_absent", None

    cand_ok = bool(cand_rec.get("ok"))

    if golden_ok:
        if not cand_ok:
            # Upstream compiled it; the candidate refused. No cell in the
            # table awards credit for that: the program is absent.
            return SCORE_INVALID_OR_ABSENT, "compiled_got_error", None

        golden_prog = _prog_tuples(golden_rec.get("prog"))
        cand_prog = _prog_tuples(cand_rec.get("prog"))

        if cand_prog is None:
            return (SCORE_INVALID_OR_ABSENT, "compiled_invalid",
                    "malformed_instruction (payload is not a program)")

        if golden_prog is not None and cand_prog == golden_prog:
            return SCORE_EXACT_PROG, "compiled_exact", None

        ok, reason = validate_program(cand_prog, max_packet=snaplen)
        if not ok:
            return SCORE_INVALID_OR_ABSENT, "compiled_invalid", reason

        fcs = floor_corrected_similarity(cand_prog, golden_prog or ())
        return SCORE_SIMILAR_COEFF * fcs, "compiled_similar", None

    # upstream REJECTED the case
    if cand_ok:
        return SCORE_ERR_RETURNED_OK, "rejected_got_ok", None
    if cand_rec.get("err") == golden_rec.get("err"):
        return SCORE_ERR_EXACT, "rejected_exact_err", None
    return SCORE_ERR_OTHER, "rejected_other_err", None


# --------------------------------------------------------------------------
# C -- weighted mean over the 8 strata
# --------------------------------------------------------------------------

def compute_C(per_case, stratum_of, weights):
    """Return (C, strata_breakdown, global_counts)."""
    buckets: dict[str, dict[str, Any]] = {}
    global_counts = {cls: 0 for cls in OUTCOME_CLASSES}

    for idx, (score, outcome, _detail) in per_case.items():
        name = stratum_of.get(idx, UNASSIGNED_STRATUM)
        b = buckets.setdefault(
            name,
            {"n": 0, "sum": 0.0, "counts": {cls: 0 for cls in OUTCOME_CLASSES}},
        )
        b["n"] += 1
        b["sum"] += score
        b["counts"][outcome] += 1
        global_counts[outcome] += 1

    # Only strata that actually carry cases contribute; the remaining weight
    # is renormalized so C stays a weighted mean on [0, 1].
    total_weight = 0.0
    for name, b in buckets.items():
        if b["n"] > 0:
            total_weight += weights.get(name, 1.0 if name == UNASSIGNED_STRATUM else 0.0)

    C = 0.0
    breakdown = []
    for name in sorted(buckets):
        b = buckets[name]
        weight = weights.get(name, 1.0 if name == UNASSIGNED_STRATUM else 0.0)
        mean = (b["sum"] / b["n"]) if b["n"] else 0.0
        share = (weight / total_weight) if total_weight > 0 else 0.0
        contribution = share * mean
        C += contribution
        breakdown.append(
            {
                "name": name,
                "weight": weight,
                "normalized_weight": share,
                "n": b["n"],
                "sum": b["sum"],
                "mean": mean,
                "weighted_contribution": contribution,
                "counts": dict(b["counts"]),
            }
        )

    for name in sorted(weights):
        if name not in buckets:
            breakdown.append(
                {
                    "name": name,
                    "weight": weights[name],
                    "normalized_weight": 0.0,
                    "n": 0,
                    "sum": 0.0,
                    "mean": 0.0,
                    "weighted_contribution": 0.0,
                    "counts": {cls: 0 for cls in OUTCOME_CLASSES},
                }
            )

    return _clip01(C), breakdown, global_counts


def _clip01(x: float) -> float:
    """clip(x, 0, 1), with non-finite input collapsing to 0."""
    if not math.isfinite(x):
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


# --------------------------------------------------------------------------
# P -- throughput
# --------------------------------------------------------------------------

def _parse_bench_payload(text: str):
    """Accept a JSON object, a JSON array, or JSONL. Returns a list of dicts."""
    stripped = text.strip()
    if not stripped:
        return []
    try:
        doc = json.loads(stripped)
    except ValueError:
        out = []
        for line in stripped.split("\n"):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue
            out.extend(_flatten_bench(item))
        return out
    return _flatten_bench(doc)


def _flatten_bench(doc) -> list[dict[str, Any]]:
    if isinstance(doc, list):
        out = []
        for item in doc:
            out.extend(_flatten_bench(item))
        return out
    if isinstance(doc, (int, float)) and not isinstance(doc, bool):
        return [{"elapsed_sec": float(doc)}]
    if not isinstance(doc, dict):
        return []
    if "trials" in doc or "warmups" in doc:
        out = []
        for entry in _as_list(doc.get("warmups")):
            for item in _flatten_bench(entry):
                item["_warmup"] = True
                out.append(item)
        for entry in _as_list(doc.get("trials")):
            for item in _flatten_bench(entry):
                item.setdefault("_warmup", False)
                out.append(item)
        return out
    if "elapsed_sec" in doc:
        return [dict(doc)]
    return []


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _load_bench_series(paths):
    """Collect trials from one or more bench files."""
    series: list[dict[str, Any]] = []
    notes: list[str] = []
    for path in paths or []:
        if not os.path.exists(path):
            notes.append(f"bench_file_missing:{os.path.basename(path)}")
            continue
        try:
            series.extend(_parse_bench_payload(_read_text(path)))
        except OSError as exc:
            notes.append(f"bench_file_unreadable:{exc}")
    return series, notes


def _split_trials(series):
    """Discard 3 warmups, keep 5 timed trials, per the frozen P protocol."""
    notes: list[str] = []
    explicit_warmups = [s for s in series if s.get("_warmup") is True]
    explicit_trials = [s for s in series if s.get("_warmup") is False]

    if explicit_warmups or explicit_trials:
        warmups, trials = explicit_warmups, explicit_trials
    elif len(series) >= BENCH_WARMUPS + BENCH_TIMED_TRIALS:
        warmups = series[:BENCH_WARMUPS]
        trials = series[BENCH_WARMUPS:BENCH_WARMUPS + BENCH_TIMED_TRIALS]
        if len(series) > BENCH_WARMUPS + BENCH_TIMED_TRIALS:
            notes.append("bench_extra_trials_ignored")
    elif len(series) > BENCH_WARMUPS:
        warmups = series[:BENCH_WARMUPS]
        trials = series[BENCH_WARMUPS:]
        notes.append("bench_insufficient_trials")
    else:
        warmups, trials = [], list(series)
        if series:
            notes.append("bench_insufficient_trials")

    if len(trials) > BENCH_TIMED_TRIALS:
        trials = trials[:BENCH_TIMED_TRIALS]
    return warmups, trials, notes


def _elapsed(entry) -> float | None:
    v = entry.get("elapsed_sec")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) and v > 0.0 else None


def _compiles(entry):
    v = entry.get("compiles")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(v) if v > 0 else None


def _side_summary(series):
    warmups, trials, notes = _split_trials(series)
    values = [_elapsed(t) for t in trials]
    clean = [v for v in values if v is not None]
    if len(clean) != len(values):
        notes.append("bench_invalid_trial_dropped")
    median = statistics.median(clean) if clean else None
    compiles = {c for c in (_compiles(t) for t in trials) if c is not None}
    return {
        "warmups": [
            {"elapsed_sec": _elapsed(w), "compiles": _compiles(w)} for w in warmups
        ],
        "trials": [
            {"elapsed_sec": _elapsed(t), "compiles": _compiles(t)} for t in trials
        ],
        "n_warmups_discarded": len(warmups),
        "n_timed_trials": len(trials),
        "median_elapsed_sec": median,
        "compiles": sorted(compiles),
        "notes": notes,
    }


def compute_P(cand_paths, up_paths, n_exact=None, n_total=None):
    """Return (P, r, timing_block). Absent benchmarks yield P = 0, not a failure.

    r is throughput per BYTE-EXACT case, not per case attempted:

        r = (t_upstream / N_total) / (t_candidate / N_exact)

    Measured reason for that shape. The shipped weak starter compiles nothing
    correctly (compiled_exact = 0) yet ran 181x faster than real libpcap over
    60,000 compiles, which drove r = 181.2 and pinned P at its 1.0 ceiling. A
    per-attempt ratio therefore paid maximum throughput credit for omitting the
    work, and the old min(1, C/0.25) throttle saturated at C = 0.25 and stopped
    resisting past that point. Dividing the candidate's time by the number of
    cases it actually got byte-exact removes the exploit at the source: a
    compiler that skips work has no exact cases to divide by, so r collapses to
    0. The anchors are unchanged, because a faithful implementation running at
    libpcap's speed still measures r = 1.0 and P = 0.333.
    """
    cand_series, cand_notes = _load_bench_series(cand_paths)
    up_series, up_notes = _load_bench_series(up_paths)

    timing: dict[str, Any] = {
        "protocol": {
            "warmups_discarded": BENCH_WARMUPS,
            "timed_trials": BENCH_TIMED_TRIALS,
            "aggregate": "median",
            "interleaved": "candidate and upstream alternate trial by trial",
            "dead_zone_r": P_DEAD_ZONE_R,
            "P_formula": "clip(ln(r/0.5)/ln(4.0/0.5), 0, 1)",
        },
        "candidate": _side_summary(cand_series),
        "upstream": _side_summary(up_series),
        "notes": list(cand_notes) + list(up_notes),
        "r": None,
        "P": 0.0,
        "dead_zone_applied": False,
    }

    if not cand_series and not up_series:
        timing["notes"].append("bench_absent")
        return 0.0, None, timing
    if not cand_series or not up_series:
        timing["notes"].append("bench_one_sided")
        return 0.0, None, timing

    t_cand = timing["candidate"]["median_elapsed_sec"]
    t_up = timing["upstream"]["median_elapsed_sec"]
    if t_cand is None or t_up is None:
        timing["notes"].append("bench_no_valid_trials")
        return 0.0, None, timing
    if t_cand <= 0.0:
        timing["notes"].append("bench_nonpositive_candidate_median")
        return 0.0, None, timing

    c_compiles = timing["candidate"]["compiles"]
    u_compiles = timing["upstream"]["compiles"]
    if c_compiles and u_compiles and c_compiles != u_compiles:
        # Different workloads are not comparable head to head; fall back to
        # seconds-per-compile so r stays meaningful. (The previous revision
        # called max() on these ints, which raises TypeError; ints are scalars.)
        timing["notes"].append("bench_compiles_mismatch_normalized")
        t_cand = t_cand / float(c_compiles)
        t_up = t_up / float(u_compiles)

    # Fidelity normalization: charge the candidate's time against the cases it
    # got byte-exact, not against the cases it merely attempted.
    timing["n_exact"] = n_exact
    timing["n_total"] = n_total
    if n_exact is not None and n_total:
        if n_exact <= 0:
            timing["notes"].append("no_exact_cases_throughput_unearned")
            timing["r"] = 0.0
            timing["P"] = 0.0
            return 0.0, 0.0, timing
        exact_fraction = float(n_exact) / float(n_total)
        t_cand = t_cand / exact_fraction
        timing["exact_fraction"] = exact_fraction
    else:
        timing["notes"].append("exact_normalization_unavailable")

    r = t_up / t_cand
    timing["r"] = r

    if r <= P_DEAD_ZONE_R:
        timing["dead_zone_applied"] = True
        timing["P"] = 0.0
        return 0.0, r, timing

    P = _clip01(math.log(r / P_R_LO) / math.log(P_R_HI / P_R_LO))
    timing["P"] = P
    return P, r, timing


# --------------------------------------------------------------------------
# Report assembly
# --------------------------------------------------------------------------

def _blank_report() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "task_id": "libpcap_bpf_codegen_fidelity",
        "formula": REWARD_FORMULA,
        "score": 0.0,
        "reward": 0.0,
        "C": 0.0,
        "P": 0.0,
        "r": None,
        "correctness_gate": 0.0,
        "hard_zero": False,
        "reason": None,
        "reason_detail": "",
        "notes": [],
        "cases": {},
        "counts": {cls: 0 for cls in OUTCOME_CLASSES},
        "strata": [],
        "validator_rejections": {},
        "timing": {},
    }


def build_hard_zero(reason: str, detail: str, partial=None) -> dict[str, Any]:
    report = partial if partial is not None else _blank_report()
    report["hard_zero"] = True
    report["reason"] = reason
    report["reason_detail"] = detail
    report["score"] = 0.0
    report["reward"] = 0.0
    report["C"] = 0.0
    report["P"] = 0.0
    report["correctness_gate"] = 0.0
    return report


def grade(golden_path, candidate_path, manifest_path,
          bench_candidate=None, bench_upstream=None, lenient=False):
    """Full grading pass. Returns (report, per_case_detail)."""
    report = _blank_report()

    manifest = load_manifest(manifest_path)
    order, golden, golden_notes = load_golden(golden_path)
    report["notes"].extend(manifest["notes"])
    report["notes"].extend(golden_notes)

    if manifest["order"] and set(manifest["order"]) != set(order):
        report["notes"].append("manifest_case_set_differs_from_golden")

    records, cand_notes, stats = load_candidate(candidate_path, order, lenient)
    report["notes"].extend(cand_notes)

    stratum_of = manifest["stratum_of"]
    snaplen_of = manifest["snaplen_of"]

    per_case: dict[int, tuple[float, str, str | None]] = {}
    rejections: dict[str, int] = {}
    detail_rows: list[dict[str, Any]] = []

    for idx in order:
        cand = records.get(idx)
        score, outcome, why = score_case(
            golden[idx], cand, snaplen=snaplen_of.get(idx)
        )
        per_case[idx] = (score, outcome, why)
        if why:
            token = why.split("@", 1)[0].split(" ", 1)[0]
            rejections[token] = rejections.get(token, 0) + 1
        detail_rows.append(
            {
                "i": idx,
                "stratum": stratum_of.get(idx, UNASSIGNED_STRATUM),
                "outcome": outcome,
                "score": score,
                "reason": why,
            }
        )

    C, breakdown, counts = compute_C(per_case, stratum_of, manifest["weights"])
    n_exact = sum(1 for _, outcome, _ in per_case.values()
                  if outcome in ("compiled_exact", "rejected_exact_err"))
    P, r, timing = compute_P(bench_candidate, bench_upstream,
                             n_exact=n_exact, n_total=len(per_case))

    gate = min(1.0, C / CORRECTNESS_GATE_C) if CORRECTNESS_GATE_C > 0 else 1.0
    R = _clip01(W_CORRECTNESS * C + W_THROUGHPUT * P * gate)

    report["score"] = R
    report["reward"] = R
    report["C"] = C
    report["P"] = P
    report["r"] = r
    report["correctness_gate"] = gate
    report["counts"] = counts
    report["strata"] = breakdown
    report["validator_rejections"] = dict(sorted(rejections.items()))
    report["timing"] = timing
    report["cases"] = {
        "graded": len(order),
        "present": len(records),
        "absent": stats["missing"],
        "lines_read": stats["lines"],
        "truncated": stats["truncated"],
        "golden_compiled": sum(1 for i in order if golden[i].get("ok")),
        "golden_rejected": sum(1 for i in order if not golden[i].get("ok")),
    }
    report["strata_weight_total"] = sum(manifest["weights"].values())
    return report, detail_rows


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="score.py",
        description="Judge-side scorer for libpcap_bpf_codegen_fidelity.",
    )
    p.add_argument("--golden", required=True, help="golden.jsonl (trusted)")
    p.add_argument("--candidate", required=True, help="candidate out.jsonl")
    p.add_argument("--manifest", required=True, help="manifest.json")
    p.add_argument("--out", required=True, help="reward.json destination")
    p.add_argument(
        "--reward-txt",
        default=None,
        help="reward.txt destination; defaults to reward.txt beside --out",
    )
    p.add_argument("--bench-candidate", action="append", default=None,
                   help="candidate --bench output; repeatable")
    p.add_argument("--bench-upstream", action="append", default=None,
                   help="upstream shim --bench output; repeatable")
    p.add_argument(
        "--force-reason",
        default=None,
        choices=list(HARD_ZERO_REASONS),
        help="force a hard zero with this frozen reason (build_failed, "
             "link_denylist, upstream_source_copy, harness_tamper, timeout "
             "are detected by the wrapper, not by this scorer)",
    )
    p.add_argument("--force-detail", default="", help="detail for --force-reason")
    p.add_argument("--lenient", action="store_true",
                   help="downgrade envelope violations to per-case zeros")
    p.add_argument("--per-case-json", default=None,
                   help="JUDGE ONLY per-case detail; never show to the solver")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    reward_txt = args.reward_txt
    if reward_txt is None:
        reward_txt = os.path.join(
            os.path.dirname(os.path.abspath(args.out)) or ".", "reward.txt"
        )

    detail_rows: list[dict[str, Any]] = []
    try:
        if args.force_reason:
            report = build_hard_zero(args.force_reason, args.force_detail)
        else:
            report, detail_rows = grade(
                args.golden,
                args.candidate,
                args.manifest,
                bench_candidate=args.bench_candidate,
                bench_upstream=args.bench_upstream,
                lenient=args.lenient,
            )
    except GradedFailure as exc:
        report = build_hard_zero(exc.reason, exc.detail)
    except Exception as exc:  # never crash: every failure is graded
        report = build_hard_zero(
            "malformed_output",
            f"unhandled scorer exception: {type(exc).__name__}: {exc}",
        )
        report["traceback"] = traceback.format_exc(limit=8)

    # reward.txt first: it is what the harness actually reads.
    try:
        write_reward_txt(reward_txt, report["score"])
    except OSError as exc:
        report.setdefault("notes", []).append(f"reward_txt_unwritable:{exc}")

    try:
        _ensure_parent(args.out)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=False)
            fh.write("\n")
    except OSError:
        pass

    if args.per_case_json and detail_rows:
        try:
            _ensure_parent(args.per_case_json)
            with open(args.per_case_json, "w", encoding="utf-8") as fh:
                json.dump({"cases": detail_rows}, fh, indent=2)
                fh.write("\n")
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
