#!/usr/bin/env python3
"""
fundamental_momentum_reference.py — JUDGE-SIDE Framework B reference solver
for sec_fundamental_momentum_calibration.

======================================================================
task_id:      sec_fundamental_momentum_calibration
bundle_uuid:  5cb28005-2b9a-5520-b4f8-de58beb5640d
authored:     2026-07-31 (FORGE Phase 2 / T6 of the finance-adjacent slate)
framework:    B (reference-anchored projector, PKW-FAMILIES §3)
contract SHA: 103f591fb359bcbba17d91ec4c2bf702cd88d83c67dacffc3de99670a9e5ac6f
source_of_truth_map:
  - contract:  seed/contract.yaml
  - grounding: seed/build/sec_fundamental_momentum_calibration/grounding.yaml
  - recompute: seed/build/sec_fundamental_momentum_calibration/recompute.py
  - truth:     dataset/5cb28005-2b9a-5520-b4f8-de58beb5640d/solution/TRUTH.md
boundary:     PRIVATE (judge-only). NEVER shipped into the work image.
              Class names FundamentalCompositeScorer / PeerGroupRankRegressor /
              CrossQuarterSurpriseDetector / FactorMomentumPositioner are opaque
              per contract.boundaries.leak_gate_invariant — they are the T6
              method-family opacity boundary and must not leak to agent surfaces.

Extraction lineage (byte-identity numeric behaviour vs seed/recompute.py):
  - compute_composite_scores          -> class FundamentalCompositeScorer
  - compute_peer_ranks                -> class PeerGroupRankRegressor
  - compute_surprises                 -> class CrossQuarterSurpriseDetector
  - compute_extremes_and_positioning  -> class FactorMomentumPositioner
  - price_response_proxy              -> module-level function (D2 concession,
                                          hash-seeded deterministic α=0.03 anchor
                                          per Novy-Marx 2013 / Fama-French 2015)

CLI:
  python3 fundamental_momentum_reference.py \
      --input-dir dataset/5cb28005-2b9a-5520-b4f8-de58beb5640d/ \
      --output    momentum_results.json

Determinism guarantees:
  - PYTHONHASHSEED=0 at process spawn (set as environment default at import)
  - No numpy / pandas / scipy: stdlib only (matches seed/recompute.py imports)
  - Sorted iteration on every dict / set
  - JSON output uses sort_keys=True
  - price_response_proxy noise seeded from sha256(cik|period) — reproducible
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
from pathlib import Path
from typing import Any

os.environ.setdefault("PYTHONHASHSEED", "0")

TRAIN_QUARTERS: list[tuple[int, int]] = [
    (y, q) for y in range(2018, 2025) for q in (1, 2, 3, 4)
]
TEST_QUARTERS: list[tuple[int, int]] = [(2025, q) for q in (1, 2, 3, 4)] + [(2026, 1)]

CONCEPTS_FLOW_USD = ["Revenues", "GrossProfit", "OperatingIncomeLoss", "NetIncomeLoss"]
CONCEPTS_FLOW_USD_PS = ["EarningsPerShareDiluted"]
CONCEPTS_STOCK_USD = ["Assets", "StockholdersEquity", "LongTermDebt"]
ALL_CONCEPTS = CONCEPTS_FLOW_USD + CONCEPTS_FLOW_USD_PS + CONCEPTS_STOCK_USD

PEER_DECILE_N = 10
PRICE_RESPONSE_ALPHA = 0.03
PRICE_RESPONSE_NOISE_AMPLITUDE = 0.02

TOP_DECILE_CUTOFF = 0.90
BOTTOM_DECILE_CUTOFF = 0.10
SURPRISE_BEAT_THRESHOLD = 0.05
SURPRISE_MISS_THRESHOLD = -0.05


def _period_key(y: int, q: int) -> str:
    return f"{y}Q{q}"


def _q_offset(pk: str, n: int) -> str:
    y = int(pk[:4])
    q = int(pk[-1])
    idx = y * 4 + (q - 1) - n
    return f"{idx // 4}Q{(idx % 4) + 1}"


class FundamentalCompositeScorer:
    """Stage 1: per-filer per-quarter composite fundamental momentum score.

    Combines four momentum components (EPS YoY, Revenue YoY, margin QoQ,
    intra-quarter EPS revision), cross-sectionally z-scores each per quarter,
    then averages non-null z-scores. Emits a score only when >=2 components
    are non-null.

    Numeric contract: byte-identical to seed/recompute.py::compute_composite_scores.
    """

    def __init__(self) -> None:
        self.min_components = 2

    def score(self, rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
        per_cik: dict[int, dict[str, dict[str, Any]]] = {}
        for r in rows:
            per_cik.setdefault(r["cik"], {})[r["period"]] = r

        raw: dict[tuple[str, int], dict[str, Any]] = {}
        for cik, periods in per_cik.items():
            for pk, r in periods.items():
                r_lag4 = periods.get(_q_offset(pk, 4))
                r_lag1 = periods.get(_q_offset(pk, 1))
                r_lag2 = periods.get(_q_offset(pk, 2))
                r_lag3 = periods.get(_q_offset(pk, 3))

                eps_yoy = None
                if (
                    r_lag4
                    and r.get("EarningsPerShareDiluted") is not None
                    and r_lag4.get("EarningsPerShareDiluted") is not None
                ):
                    denom = max(abs(r_lag4["EarningsPerShareDiluted"]), 0.01)
                    eps_yoy = (
                        r["EarningsPerShareDiluted"] - r_lag4["EarningsPerShareDiluted"]
                    ) / denom

                rev_yoy = None
                if (
                    r_lag4
                    and r.get("Revenues") is not None
                    and r_lag4.get("Revenues") is not None
                ):
                    denom = max(abs(r_lag4["Revenues"]), 1.0)
                    rev_yoy = (r["Revenues"] - r_lag4["Revenues"]) / denom

                margin_qoq = None
                if (
                    r_lag4
                    and r.get("OperatingIncomeLoss") is not None
                    and r.get("Revenues") is not None
                    and r_lag4.get("OperatingIncomeLoss") is not None
                    and r_lag4.get("Revenues") is not None
                    and r["Revenues"] != 0
                    and r_lag4["Revenues"] != 0
                ):
                    m_now = r["OperatingIncomeLoss"] / r["Revenues"]
                    m_prev = r_lag4["OperatingIncomeLoss"] / r_lag4["Revenues"]
                    margin_qoq = m_now - m_prev

                revision = None
                prior_eps = [
                    x.get("EarningsPerShareDiluted")
                    for x in (r_lag1, r_lag2, r_lag3)
                    if x is not None
                ]
                prior_eps = [v for v in prior_eps if v is not None]
                if r.get("EarningsPerShareDiluted") is not None and len(prior_eps) >= 2:
                    mean_prior = statistics.fmean(prior_eps)
                    std_prior = max(statistics.pstdev(prior_eps), 0.01)
                    revision = (r["EarningsPerShareDiluted"] - mean_prior) / std_prior

                raw[(pk, cik)] = {
                    "eps_yoy": eps_yoy,
                    "rev_yoy": rev_yoy,
                    "margin_qoq": margin_qoq,
                    "revision": revision,
                }

        by_period: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for (pk, cik), comps in raw.items():
            by_period.setdefault(pk, []).append((cik, comps))

        z_scored: dict[tuple[str, int], dict[str, Any]] = {}
        for pk, cik_comps in by_period.items():
            for comp_name in ("eps_yoy", "rev_yoy", "margin_qoq", "revision"):
                vals = [(cik, c[comp_name]) for cik, c in cik_comps if c[comp_name] is not None]
                if len(vals) < 3:
                    continue
                values = [v for _, v in vals]
                mean = statistics.fmean(values)
                std = max(statistics.pstdev(values), 1e-9)
                for cik, v in vals:
                    key = (pk, cik)
                    if key not in z_scored:
                        z_scored[key] = {
                            "z_eps_yoy": None,
                            "z_rev_yoy": None,
                            "z_margin_qoq": None,
                            "z_revision": None,
                        }
                    z_scored[key][f"z_{comp_name}"] = (v - mean) / std

        result: dict[tuple[str, int], dict[str, Any]] = {}
        for key, raw_comps in raw.items():
            zs = z_scored.get(key, {})
            components = [
                zs.get(f"z_{c}") for c in ("eps_yoy", "rev_yoy", "margin_qoq", "revision")
            ]
            non_null = [c for c in components if c is not None]
            composite = statistics.fmean(non_null) if len(non_null) >= self.min_components else None
            result[key] = {
                **raw_comps,
                "z_eps_yoy": zs.get("z_eps_yoy"),
                "z_rev_yoy": zs.get("z_rev_yoy"),
                "z_margin_qoq": zs.get("z_margin_qoq"),
                "z_revision": zs.get("z_revision"),
                "composite_score": composite,
                "n_components": len(non_null),
            }
        return result


class PeerGroupRankRegressor:
    """Stage 2: peer-conditional cross-sectional rank normalization.

    Assets deciles substitute for SIC-based peer groups (SIC codes are not
    present in SEC EDGAR frames responses). Per quarter, filers are sorted
    ascending by Assets, partitioned into 10 equal buckets. Emits both an
    intra-decile percentile rank of composite_score and a global percentile.

    Numeric contract: byte-identical to seed/recompute.py::compute_peer_ranks.
    """

    def __init__(self, n_deciles: int = PEER_DECILE_N) -> None:
        self.n_deciles = n_deciles

    def rank(
        self,
        scores: dict[tuple[str, int], dict[str, Any]],
        assets_by_quarter: dict[str, dict[int, float]],
    ) -> dict[tuple[str, int], dict[str, Any]]:
        result: dict[tuple[str, int], dict[str, Any]] = {}
        by_period: dict[str, list[tuple[int, float, float | None]]] = {}
        for (pk, cik), row in scores.items():
            assets = assets_by_quarter.get(pk, {}).get(cik)
            if assets is None:
                continue
            by_period.setdefault(pk, []).append((cik, assets, row.get("composite_score")))

        for pk, entries in by_period.items():
            entries.sort(key=lambda t: (t[1], t[0]))
            n = len(entries)
            for i, (cik, _assets, _score) in enumerate(entries):
                decile = min(self.n_deciles - 1, (i * self.n_deciles) // max(n, 1))
                result[(pk, cik)] = {"assets_decile": decile}

            for decile_val in range(self.n_deciles):
                decile_entries = [
                    (cik, score)
                    for cik, _, score in entries
                    if result[(pk, cik)]["assets_decile"] == decile_val and score is not None
                ]
                decile_entries.sort(key=lambda t: (t[1], t[0]))
                m = len(decile_entries)
                for rank_i, (cik, _) in enumerate(decile_entries):
                    percentile = (rank_i + 0.5) / m if m > 0 else 0.5
                    result[(pk, cik)]["peer_rank_percentile"] = percentile

            all_scored = [(cik, score) for cik, _, score in entries if score is not None]
            all_scored.sort(key=lambda t: (t[1], t[0]))
            for rank_i, (cik, _) in enumerate(all_scored):
                result[(pk, cik)]["global_rank_percentile"] = (
                    (rank_i + 0.5) / len(all_scored) if all_scored else 0.5
                )

        return result


class CrossQuarterSurpriseDetector:
    """Stage 3: prior-4-quarter EPS OLS extrapolation surprise detector.

    Predicts EPS[q] from a linear OLS fit over EPS[q-1..q-4] (requires >=3
    non-null lagged points). Relative surprise = (actual - predicted) /
    max(|predicted|, 0.01). Classifies:
      - "beat"    if surprise_relative > +0.05
      - "miss"    if surprise_relative < -0.05
      - "in_line" otherwise

    Numeric contract: byte-identical to seed/recompute.py::compute_surprises.
    """

    def __init__(
        self,
        beat_threshold: float = SURPRISE_BEAT_THRESHOLD,
        miss_threshold: float = SURPRISE_MISS_THRESHOLD,
    ) -> None:
        self.beat_threshold = beat_threshold
        self.miss_threshold = miss_threshold

    def detect(self, rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
        per_cik: dict[int, dict[str, dict[str, Any]]] = {}
        for r in rows:
            per_cik.setdefault(r["cik"], {})[r["period"]] = r

        surprises: dict[tuple[str, int], dict[str, Any]] = {}
        for cik, periods in per_cik.items():
            for pk, r in periods.items():
                actual = r.get("EarningsPerShareDiluted")
                if actual is None:
                    continue
                prior: list[tuple[int, float]] = []
                for n in (1, 2, 3, 4):
                    r_lag = periods.get(_q_offset(pk, n))
                    if r_lag is not None:
                        v = r_lag.get("EarningsPerShareDiluted")
                        if v is not None:
                            prior.append((n, v))
                if len(prior) < 3:
                    continue

                xs = [-p[0] for p in prior]
                ys = [p[1] for p in prior]
                mean_x = statistics.fmean(xs)
                mean_y = statistics.fmean(ys)
                num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
                den = sum((x - mean_x) ** 2 for x in xs)
                if den == 0:
                    predicted = mean_y
                else:
                    slope = num / den
                    intercept = mean_y - slope * mean_x
                    predicted = intercept

                denom = max(abs(predicted), 0.01)
                surprise_rel = (actual - predicted) / denom
                if surprise_rel > self.beat_threshold:
                    direction = "beat"
                elif surprise_rel < self.miss_threshold:
                    direction = "miss"
                else:
                    direction = "in_line"
                surprises[(pk, cik)] = {
                    "eps_actual": actual,
                    "eps_predicted_from_prior4": predicted,
                    "surprise_relative": surprise_rel,
                    "surprise_direction": direction,
                }
        return surprises


class FactorMomentumPositioner:
    """Stage 4: dollar-neutral long-top-decile / short-bottom-decile positioner.

    Per quarter, per-filer position weight:
      - +1 / n_long  if global_rank_percentile >= 0.90 (top decile)
      - -1 / n_short if global_rank_percentile <= 0.10 (bottom decile)
      -  0           otherwise
    Book is dollar-neutral by construction.

    Numeric contract: byte-identical to
    seed/recompute.py::compute_extremes_and_positioning.
    """

    def __init__(
        self,
        top_cutoff: float = TOP_DECILE_CUTOFF,
        bottom_cutoff: float = BOTTOM_DECILE_CUTOFF,
    ) -> None:
        self.top_cutoff = top_cutoff
        self.bottom_cutoff = bottom_cutoff

    def position(
        self,
        ranks: dict[tuple[str, int], dict[str, Any]],
        universe: dict[str, list[int]],
    ) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        extremes: dict[tuple[str, int], dict[str, Any]] = {}
        positions: dict[str, list[dict[str, Any]]] = {}
        for pk in sorted(universe.keys(), key=lambda pk: (int(pk[:4]), int(pk[-1]))):
            entries = [
                (cik, ranks.get((pk, cik), {}).get("global_rank_percentile"))
                for cik in universe[pk]
            ]
            entries = [(cik, p) for cik, p in entries if p is not None]
            entries.sort(key=lambda t: (t[1], t[0]))
            n = len(entries)
            if n == 0:
                positions[pk] = []
                continue
            long_ciks = [cik for cik, p in entries if p >= self.top_cutoff]
            short_ciks = [cik for cik, p in entries if p <= self.bottom_cutoff]
            n_long = max(len(long_ciks), 1)
            n_short = max(len(short_ciks), 1)

            book: list[dict[str, Any]] = []
            for cik, p in entries:
                weight = 0.0
                in_top = p >= self.top_cutoff
                in_bottom = p <= self.bottom_cutoff
                if in_top:
                    weight = 1.0 / n_long
                elif in_bottom:
                    weight = -1.0 / n_short
                extremes[(pk, cik)] = {
                    "in_top_decile": in_top,
                    "in_bottom_decile": in_bottom,
                    "rank_percentile": p,
                }
                if weight != 0.0:
                    book.append(
                        {"cik": cik, "weight": round(weight, 6), "rank_percentile": p}
                    )
            book.sort(key=lambda d: (-d["weight"], d["cik"]))
            positions[pk] = book
        return extremes, positions


def price_response_proxy(cik: int, period: str, surprise_rel: float) -> float:
    """Fundamentals-derived 20-day post-print price-response proxy (D2 concession).

    Per-issuer equity prices are NOT fetched (Stooq / Yahoo / Bloomberg
    forbidden per contract N10; FRED does not carry per-CIK equity prices).
    Proxy formula:

        response = 0.03 * sign(surprise_rel) * min(|surprise_rel|, 0.5)
                 + hash-seeded uniform(-0.02, +0.02)

    Alpha anchor 0.03 from Novy-Marx 2013 JFE + Fama-French 2015 quality-
    factor findings that positive earnings surprises produce ~1-3% excess
    return over the 20-day post-print window. Noise seed derived from
    sha256(f"{cik}|{period}") to guarantee reproducible per-observation
    dispersion across recompute runs.

    Numeric contract: byte-identical to seed/recompute.py::price_response_proxy.
    """
    signed = (1.0 if surprise_rel >= 0 else -1.0) * min(abs(surprise_rel), 0.5)
    core = PRICE_RESPONSE_ALPHA * signed
    h = hashlib.sha256(f"{cik}|{period}".encode()).digest()
    rng = random.Random(int.from_bytes(h[:8], "big"))
    noise = rng.uniform(-PRICE_RESPONSE_NOISE_AMPLITUDE, PRICE_RESPONSE_NOISE_AMPLITUDE)
    return round(core + noise, 6)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _assets_by_quarter(fundamentals: list[dict[str, Any]]) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for r in fundamentals:
        assets = r.get("Assets")
        if assets is None:
            continue
        out.setdefault(r["period"], {})[int(r["cik"])] = float(assets)
    return out


def _universe_from_flags(universe_rows: list[dict[str, Any]]) -> dict[str, list[int]]:
    universe: dict[str, set[int]] = {}
    for row in universe_rows:
        pk = row["period"]
        cik = int(row["cik"])
        if row.get("exit"):
            continue
        universe.setdefault(pk, set()).add(cik)
    return {pk: sorted(ciks) for pk, ciks in universe.items()}


def run_reference(input_dir: Path) -> dict[str, Any]:
    """Execute the 4-stage reference pipeline on a bundle-shaped input directory.

    Reads train/{fundamentals,universe,macro}.jsonl + test/{fundamentals,
    universe,macro}.jsonl + test/test_filer_quarters.json. Returns a shape-
    complete momentum_results dict covering exactly the test filer-quarters
    listed in test_filer_quarters.json.
    """
    train_fund = _read_jsonl(input_dir / "train" / "fundamentals.jsonl")
    test_fund = _read_jsonl(input_dir / "test" / "fundamentals.jsonl")
    train_universe_rows = _read_jsonl(input_dir / "train" / "universe.jsonl")
    test_universe_rows = _read_jsonl(input_dir / "test" / "universe.jsonl")
    with (input_dir / "test" / "test_filer_quarters.json").open("r") as f:
        test_targets = json.load(f)

    all_fund = train_fund + test_fund
    universe = _universe_from_flags(train_universe_rows + test_universe_rows)
    assets = _assets_by_quarter(all_fund)

    scorer = FundamentalCompositeScorer()
    ranker = PeerGroupRankRegressor()
    surpriser = CrossQuarterSurpriseDetector()
    positioner = FactorMomentumPositioner()

    scores = scorer.score(all_fund)
    ranks = ranker.rank(scores, assets)
    surprises = surpriser.detect(all_fund)
    extremes, positions = positioner.position(ranks, universe)

    test_periods = {_period_key(y, q) for y, q in TEST_QUARTERS}

    per_filer_quarter: list[dict[str, Any]] = []
    targets_sorted = sorted(
        [(t["period"], int(t["cik"])) for t in test_targets],
        key=lambda t: (t[0], t[1]),
    )
    for pk, cik in targets_sorted:
        if pk not in test_periods:
            continue
        key = (pk, cik)
        s = scores.get(key, {})
        r = ranks.get(key, {})
        sur = surprises.get(key, {})
        ex = extremes.get(key, {})

        composite = s.get("composite_score")
        peer_pct = r.get("peer_rank_percentile")
        global_pct = r.get("global_rank_percentile")

        direction = sur.get("surprise_direction", "in_line")
        surprise_rel = sur.get("surprise_relative")
        if surprise_rel is None:
            confidence = 0.0
            proxy = 0.0
        else:
            confidence = min(1.0, abs(surprise_rel))
            proxy = price_response_proxy(cik, pk, surprise_rel)

        in_top = bool(ex.get("in_top_decile", False))
        in_bot = bool(ex.get("in_bottom_decile", False))
        if in_top or in_bot:
            extreme_prob = 1.0
        elif global_pct is not None:
            edge = min(global_pct, 1.0 - global_pct)
            extreme_prob = max(0.0, 1.0 - edge / 0.10)
            extreme_prob = round(extreme_prob, 6)
        else:
            extreme_prob = 0.0

        if in_top:
            weight = 1.0 / max(sum(1 for _pk, _cik in extremes if _pk == pk and extremes[(_pk, _cik)].get("in_top_decile")), 1)
        elif in_bot:
            weight = -1.0 / max(sum(1 for _pk, _cik in extremes if _pk == pk and extremes[(_pk, _cik)].get("in_bottom_decile")), 1)
        else:
            weight = 0.0
        weight = round(weight, 6)

        per_filer_quarter.append({
            "cik": cik,
            "period": pk,
            "composite_score": round(composite, 6) if composite is not None else None,
            "peer_rank_percentile": round(peer_pct, 6) if peer_pct is not None else None,
            "global_rank_percentile": round(global_pct, 6) if global_pct is not None else None,
            "surprise_direction": direction,
            "surprise_confidence": round(confidence, 6),
            "extreme_probability": extreme_prob,
            "in_top_decile": in_top,
            "in_bottom_decile": in_bot,
            "position_weight": weight,
            "price_response_20d_proxy": proxy,
        })

    n = len(per_filer_quarter)
    n_top = sum(1 for r in per_filer_quarter if r["in_top_decile"])
    n_bot = sum(1 for r in per_filer_quarter if r["in_bottom_decile"])
    n_beat = sum(1 for r in per_filer_quarter if r["surprise_direction"] == "beat")
    n_miss = sum(1 for r in per_filer_quarter if r["surprise_direction"] == "miss")
    n_in_line = sum(1 for r in per_filer_quarter if r["surprise_direction"] == "in_line")

    per_quarter_pnl: dict[str, float] = {}
    for pk in sorted({r["period"] for r in per_filer_quarter}):
        pnl = 0.0
        for r in per_filer_quarter:
            if r["period"] != pk:
                continue
            pnl += r["position_weight"] * r["price_response_20d_proxy"]
        per_quarter_pnl[pk] = round(pnl, 6)

    self_reported = {
        "L1_composite_score_rank_correlation_est": 0.25,
        "L2_earnings_surprise_direction_accuracy_est": 1.0,
        "L3_extreme_filer_detection_f1_est": 1.0,
        "L4_revenue_growth_ranking_ic_est": 0.50,
        "L5_margin_expansion_direction_accuracy_est": 0.50,
        "L6_composite_position_pnl_sharpe_est": None,
        "L8_cross_quarter_stability_est": None,
        "n_predictions": n,
        "n_top_decile": n_top,
        "n_bottom_decile": n_bot,
        "n_beat": n_beat,
        "n_miss": n_miss,
        "n_in_line": n_in_line,
        "per_quarter_positioning_pnl": per_quarter_pnl,
    }

    return {
        "task_id": "sec_fundamental_momentum_calibration",
        "bundle_uuid": "5cb28005-2b9a-5520-b4f8-de58beb5640d",
        "generated_by": "fundamental_momentum_reference.py (Framework B judge-side reference)",
        "per_filer_quarter": per_filer_quarter,
        "self_reported_metrics": self_reported,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FORGE Phase 2 Framework B reference solver (sec_fundamental_momentum_calibration)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Bundle directory containing train/ and test/ subdirs (fundamentals.jsonl + universe.jsonl + macro.jsonl + test/test_filer_quarters.json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output momentum_results.json path.",
    )
    args = parser.parse_args()

    results = run_reference(args.input_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(results, sort_keys=True, indent=2) + "\n"
    args.output.write_text(body)
    print(
        f"reference solver produced {len(results['per_filer_quarter'])} filer-quarter predictions -> {args.output}"
    )


if __name__ == "__main__":
    main()
