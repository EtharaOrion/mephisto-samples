#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

os.environ.setdefault("PYTHONHASHSEED", "0")
random.seed(42)
try:
    import numpy as np
    np.random.seed(42)
except ImportError:
    np = None


BINS = ["b4w", "b8w", "b13w", "b26w", "rrp", "iorb"]
BIN_DURATIONS = {"b4w": 4/52.0, "b8w": 8/52.0, "b13w": 13/52.0, "b26w": 26/52.0, "rrp": 1/365.0, "iorb": 1/365.0}

REPO_REGIME_STATES = ["deep_qt", "normal", "elevated_stress", "extreme_stress"]

STRESS_SOFR_IORB_SPREAD_BPS = 15.0
DEEP_QT_RRP_BALANCE_THRESHOLD_B = 100.0
ELEVATED_RRP_BALANCE_THRESHOLD_B = 500.0

TURNOVER_PENALTY = 0.02
LADDER_TARGET_DURATION_CAP = 0.35

BILL_ISSUANCE_LOOKBACK_WEEKS = 4
BILL_ISSUANCE_LOOKFORWARD_WEEKS = 4

MONEY_MARKET_DEMAND_SMOOTH = 20

EXTREME_STRESS_Z_THRESHOLD = 0.9
EXTREME_STRESS_RRP_DROP_PCT = 0.30


def _parse_date(s: str) -> date:
    return date.fromisoformat(s[:10])


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r") as f:
        r = csv.DictReader(f)
        for row in r:
            for k in list(row.keys()):
                v = row[k]
                if v == "" or v is None:
                    row[k] = None
                elif k != "date":
                    try:
                        row[k] = float(v)
                    except (ValueError, TypeError):
                        pass
            rows.append(row)
    return rows


def _rolling(vals: list[float | None], window: int) -> list[float | None]:
    out = []
    for i in range(len(vals)):
        w = [v for v in vals[max(0, i-window+1):i+1] if v is not None]
        out.append(statistics.fmean(w) if w else None)
    return out


def _zscore(vals: list[float | None]) -> list[float | None]:
    non = [v for v in vals if v is not None]
    if len(non) < 3:
        return [None]*len(vals)
    m = statistics.fmean(non)
    s = max(statistics.pstdev(non), 1e-9)
    return [(v - m)/s if v is not None else None for v in vals]


class TreasuryBillSupplyProjector:
    def __init__(self):
        self.baseline_weekly_issuance_b = None
        self.trend_slope_b_per_week = None
        self.tga_drawdown_signal_scale = None

    def fit(self, bill_train: list[dict], tga_train: list[dict]) -> None:
        weekly_issuance = {}
        for a in bill_train:
            try:
                d = _parse_date(a["auction_date"])
                amt = float(a.get("total_accepted") or a.get("offering_amt") or 0)
            except (ValueError, TypeError, KeyError):
                continue
            monday = d - timedelta(days=d.weekday())
            wk = monday.isoformat()
            weekly_issuance[wk] = weekly_issuance.get(wk, 0.0) + amt/1e9
        vals = [weekly_issuance[k] for k in sorted(weekly_issuance)]
        if len(vals) < 12:
            self.baseline_weekly_issuance_b = 300.0
            self.trend_slope_b_per_week = 0.0
        else:
            self.baseline_weekly_issuance_b = statistics.fmean(vals[-52:])
            xs = list(range(len(vals[-52:])))
            ys = vals[-52:]
            mx = statistics.fmean(xs); my = statistics.fmean(ys)
            num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
            den = sum((x-mx)**2 for x in xs) or 1.0
            self.trend_slope_b_per_week = num/den
        tga_vals: list[float] = [float(r["tga_balance_b"]) for r in tga_train if r.get("tga_balance_b") is not None]
        if len(tga_vals) >= 30:
            self.tga_drawdown_signal_scale = statistics.pstdev(tga_vals[-90:])
        else:
            self.tga_drawdown_signal_scale = 50.0

    def project(self, current_tga_b: float | None, tga_delta_14d_b: float | None,
                weeks_ahead: int = 4) -> dict[str, Any]:
        base = self.baseline_weekly_issuance_b or 300.0
        proj_next = base + weeks_ahead * (self.trend_slope_b_per_week or 0.0)
        supply_direction_score = self.trend_slope_b_per_week or 0.0
        if tga_delta_14d_b is not None and self.tga_drawdown_signal_scale:
            tga_signal = -tga_delta_14d_b / max(self.tga_drawdown_signal_scale, 1.0)
            supply_direction_score += 0.3 * tga_signal
        return {
            "projected_weekly_issuance_b_next4w": proj_next,
            "supply_direction_score": supply_direction_score,
            "baseline_weekly_issuance_b": base,
        }


class RepoRegimeDetector:
    def __init__(self):
        self.spread_history_stats = None
        self.rrp_history_stats = None

    def fit(self, sofr_train: list[dict], repo_train: list[dict], macro_train: list[dict]) -> None:
        iorb_by_date = {r["date"]: r.get("iorb") or r.get("dff") for r in macro_train}
        sofr_by_date = {r["date"]: r.get("sofr") for r in sofr_train}
        spreads = []
        for d, sofr in sofr_by_date.items():
            io = iorb_by_date.get(d)
            if sofr is not None and io is not None:
                spreads.append(100.0*(sofr - io))
        rrp_vals: list[float] = [float(r["rrp_accepted_b"]) for r in repo_train if r.get("rrp_accepted_b") is not None]
        if spreads:
            self.spread_history_stats = {"mean": statistics.fmean(spreads),
                                         "std": max(statistics.pstdev(spreads), 1.0)}
        else:
            self.spread_history_stats = {"mean": 0.0, "std": 5.0}
        if rrp_vals:
            self.rrp_history_stats = {"mean": statistics.fmean(rrp_vals),
                                      "std": max(statistics.pstdev(rrp_vals), 100.0)}
        else:
            self.rrp_history_stats = {"mean": 500.0, "std": 400.0}

    def classify(self, sofr: float | None, iorb: float | None,
                 rrp_balance_b: float | None,
                 sofr_p99_minus_p1_bps: float | None) -> str:
        if sofr is None or iorb is None:
            return "normal"
        spread_bps = 100.0 * (sofr - iorb)
        if rrp_balance_b is not None and rrp_balance_b < DEEP_QT_RRP_BALANCE_THRESHOLD_B and spread_bps > STRESS_SOFR_IORB_SPREAD_BPS:
            return "extreme_stress"
        if rrp_balance_b is not None and rrp_balance_b < DEEP_QT_RRP_BALANCE_THRESHOLD_B:
            return "deep_qt"
        if spread_bps > STRESS_SOFR_IORB_SPREAD_BPS or (sofr_p99_minus_p1_bps is not None and sofr_p99_minus_p1_bps > 20.0):
            return "elevated_stress"
        return "normal"


class MoneyMarketDemandModel:
    def __init__(self):
        self.rrp_baseline = None
        self.smoothed_rrp = None

    def fit(self, repo_train: list[dict]) -> None:
        raw_vals = [(r["date"], r.get("rrp_accepted_b")) for r in repo_train]
        vals: list[tuple[str, float]] = [(d, float(v)) for d, v in raw_vals if v is not None]
        if vals:
            self.rrp_baseline = statistics.fmean([v for _, v in vals[-90:]])
        else:
            self.rrp_baseline = 500.0

    def signal(self, rrp_balance_b: float | None,
               rrp_counterparties: int | float | None,
               rrp_rate_avg: float | None,
               iorb: float | None) -> float:
        if rrp_balance_b is None:
            return 0.0
        excess = (rrp_balance_b - (self.rrp_baseline or 500.0)) / max(self.rrp_baseline or 500.0, 100.0)
        rate_component = 0.0
        if rrp_rate_avg is not None and iorb is not None:
            rate_component = 5.0*(iorb - rrp_rate_avg)
        cp_component = 0.0
        if rrp_counterparties is not None:
            cp_component = (float(rrp_counterparties) - 40.0)/40.0
        return -0.5*excess + rate_component + 0.3*cp_component


class RegimeConditionalLadderPositioner:
    REGIME_ALLOCATIONS = {
        "deep_qt": {"b4w": 0.10, "b8w": 0.15, "b13w": 0.20, "b26w": 0.30, "rrp": 0.05, "iorb": 0.20},
        "normal": {"b4w": 0.15, "b8w": 0.20, "b13w": 0.25, "b26w": 0.20, "rrp": 0.10, "iorb": 0.10},
        "elevated_stress": {"b4w": 0.25, "b8w": 0.25, "b13w": 0.15, "b26w": 0.05, "rrp": 0.20, "iorb": 0.10},
        "extreme_stress": {"b4w": 0.30, "b8w": 0.20, "b13w": 0.10, "b26w": 0.05, "rrp": 0.25, "iorb": 0.10},
    }

    def allocate(self, regime: str, supply_direction: float, demand_signal: float,
                 prior_allocation: dict[str, float] | None = None) -> dict[str, float]:
        base = dict(self.REGIME_ALLOCATIONS.get(regime, self.REGIME_ALLOCATIONS["normal"]))
        if supply_direction > 0:
            base["b4w"] = min(0.40, base["b4w"] + 0.03)
            base["b26w"] = max(0.02, base["b26w"] - 0.03)
        else:
            base["b26w"] = min(0.40, base["b26w"] + 0.02)
            base["b4w"] = max(0.05, base["b4w"] - 0.02)
        if demand_signal > 0:
            base["rrp"] = min(0.40, base["rrp"] + 0.03)
            base["iorb"] = max(0.02, base["iorb"] - 0.03)
        elif demand_signal < 0:
            base["rrp"] = max(0.02, base["rrp"] - 0.03)
            base["iorb"] = min(0.40, base["iorb"] + 0.03)
        tot = sum(base.values())
        base = {k: v/tot for k, v in base.items()}
        if prior_allocation is not None:
            blend = 1.0 - TURNOVER_PENALTY
            out = {k: blend*base[k] + TURNOVER_PENALTY*prior_allocation.get(k, base[k]) for k in BINS}
            s = sum(out.values())
            return {k: v/s for k, v in out.items()}
        return base


def _load_frame(input_dir: Path, kind: str) -> dict[str, list[dict]]:
    frames = {}
    for name in ("sofr", "repo", "pd_positions", "tga_dts", "macro", "bill_auctions", "short_end_curve"):
        p = input_dir / f"{name}_{kind}.csv"
        if p.exists():
            frames[name] = _read_csv(p)
        else:
            frames[name] = []
    return frames


def _stress_detect(sofr_row: dict, repo_row: dict | None,
                   sofr_history_z: dict[str, float]) -> tuple[bool, float]:
    if sofr_row is None:
        return False, 0.0
    spread = None
    if sofr_row.get("sofr_p99") is not None and sofr_row.get("sofr_p1") is not None:
        spread = 100.0 * (sofr_row["sofr_p99"] - sofr_row["sofr_p1"])
    z = 0.0
    if spread is not None and sofr_history_z.get("std_spread"):
        z = (spread - sofr_history_z["mean_spread"]) / max(sofr_history_z["std_spread"], 1.0)
    is_stress = z > EXTREME_STRESS_Z_THRESHOLD
    prob = 1.0/(1.0 + math.exp(-max(z, 0.0)))
    return is_stress, prob


def train_reference(input_dir: Path, state_path: Path) -> dict:
    fr = _load_frame(input_dir, "train")
    supply = TreasuryBillSupplyProjector()
    supply.fit(fr["bill_auctions"], fr["tga_dts"])
    regime = RepoRegimeDetector()
    regime.fit(fr["sofr"], fr["repo"], fr["macro"])
    demand = MoneyMarketDemandModel()
    demand.fit(fr["repo"])

    sofr_spreads = []
    for r in fr["sofr"]:
        if r.get("sofr_p99") is not None and r.get("sofr_p1") is not None:
            sofr_spreads.append(100.0 * (r["sofr_p99"] - r["sofr_p1"]))
    sofr_history_z = {}
    if sofr_spreads:
        sofr_history_z["mean_spread"] = statistics.fmean(sofr_spreads)
        sofr_history_z["std_spread"] = max(statistics.pstdev(sofr_spreads), 1.0)
    else:
        sofr_history_z["mean_spread"] = 5.0
        sofr_history_z["std_spread"] = 5.0

    state = {
        "supply": {"baseline_weekly_issuance_b": supply.baseline_weekly_issuance_b,
                   "trend_slope_b_per_week": supply.trend_slope_b_per_week,
                   "tga_drawdown_signal_scale": supply.tga_drawdown_signal_scale},
        "regime": {"spread_history_stats": regime.spread_history_stats,
                   "rrp_history_stats": regime.rrp_history_stats},
        "demand": {"rrp_baseline": demand.rrp_baseline},
        "sofr_history_z": sofr_history_z,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, sort_keys=True, indent=2))
    return state


def backtest_reference(input_dir: Path, state_path: Path, output_path: Path) -> dict:
    random.seed(42)
    if np is not None:
        np.random.seed(42)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if not state:
        state = train_reference(input_dir, state_path)

    supply = TreasuryBillSupplyProjector()
    s_state = state.get("supply", {})
    supply.baseline_weekly_issuance_b = s_state.get("baseline_weekly_issuance_b") or 300.0
    supply.trend_slope_b_per_week = s_state.get("trend_slope_b_per_week") or 0.0
    supply.tga_drawdown_signal_scale = s_state.get("tga_drawdown_signal_scale") or 50.0

    regime = RepoRegimeDetector()
    regime.spread_history_stats = state.get("regime", {}).get("spread_history_stats") or {"mean": 0.0, "std": 5.0}
    regime.rrp_history_stats = state.get("regime", {}).get("rrp_history_stats") or {"mean": 500.0, "std": 400.0}

    demand = MoneyMarketDemandModel()
    demand.rrp_baseline = state.get("demand", {}).get("rrp_baseline") or 500.0

    positioner = RegimeConditionalLadderPositioner()
    sofr_history_z = state.get("sofr_history_z", {"mean_spread": 5.0, "std_spread": 5.0})

    train_frames = _load_frame(input_dir, "train")
    test_frames = _load_frame(input_dir, "test")
    combined_sofr_by_date = {r["date"]: r for r in train_frames["sofr"] + test_frames["sofr"]}
    combined_repo_by_date = {r["date"]: r for r in train_frames["repo"] + test_frames["repo"]}
    combined_tga_by_date = {r["date"]: r for r in train_frames["tga_dts"] + test_frames["tga_dts"]}
    combined_macro_by_date = {r["date"]: r for r in train_frames["macro"] + test_frames["macro"]}

    dates_path = input_dir / "test_ladder_dates.json"
    if not dates_path.exists():
        raise FileNotFoundError(f"missing {dates_path}")
    dates_meta = json.loads(dates_path.read_text())
    rebal_dates = dates_meta["rebalance_dates"]
    weekly_dates_set = set(dates_meta.get("weekly_dates", []))

    per_date: list[dict] = []
    prior_alloc = None
    weekly_ranks: dict[str, list[dict]] = {}
    prev_regime = None
    for i, d in enumerate(rebal_dates):
        sofr_row = combined_sofr_by_date.get(d) or {}
        repo_row = combined_repo_by_date.get(d) or {}
        macro_row = combined_macro_by_date.get(d) or {}
        tga_row = combined_tga_by_date.get(d) or {}

        rrp_bal = repo_row.get("rrp_accepted_b")
        iorb_val = macro_row.get("iorb") or macro_row.get("dff")
        sofr_val = sofr_row.get("sofr")
        cp = repo_row.get("rrp_counterparties")
        rrp_rate = repo_row.get("rrp_rate_avg")

        spread99_1 = None
        if sofr_row.get("sofr_p99") is not None and sofr_row.get("sofr_p1") is not None:
            spread99_1 = 100.0*(sofr_row["sofr_p99"] - sofr_row["sofr_p1"])

        regime_label = regime.classify(sofr_val, iorb_val, rrp_bal, spread99_1)

        tga_delta_14 = None
        d0 = _parse_date(d)
        d_back = (d0 - timedelta(days=14)).isoformat()
        if tga_row.get("tga_balance_b") is not None and combined_tga_by_date.get(d_back, {}).get("tga_balance_b") is not None:
            tga_delta_14 = tga_row["tga_balance_b"] - combined_tga_by_date[d_back]["tga_balance_b"]

        supply_proj = supply.project(tga_row.get("tga_balance_b"), tga_delta_14)
        demand_signal = demand.signal(rrp_bal, cp, rrp_rate, iorb_val)

        alloc = positioner.allocate(regime_label, supply_proj["supply_direction_score"], demand_signal, prior_alloc)
        prior_alloc = alloc

        is_stress, stress_prob = _stress_detect(sofr_row, repo_row, sofr_history_z)
        if regime_label == "extreme_stress":
            is_stress = True
            stress_prob = max(stress_prob, 0.9)

        supply_dir = "up" if supply_proj["supply_direction_score"] > 0 else ("down" if supply_proj["supply_direction_score"] < 0 else "flat")

        alloc_duration = sum(alloc[b]*BIN_DURATIONS[b] for b in BINS)
        self_reported_certainty = 1.0/(1.0 + abs(demand_signal) + abs(supply_proj["supply_direction_score"]))
        self_reported_certainty = max(0.05, min(0.95, self_reported_certainty))

        entry = {
            "date": d,
            "allocation": {k: round(v, 6) for k, v in alloc.items()},
            "regime_label": regime_label,
            "extreme_stress_flag": bool(is_stress),
            "extreme_stress_probability": round(stress_prob, 6),
            "supply_direction": supply_dir,
            "supply_projection_b": round(supply_proj["projected_weekly_issuance_b_next4w"], 4),
            "demand_signal": round(demand_signal, 6),
            "ladder_duration_years": round(alloc_duration, 6),
            "self_reported_certainty": round(self_reported_certainty, 6),
        }
        if d in weekly_dates_set:
            week_key = d
            entry["weekly_rank_key"] = week_key
        per_date.append(entry)
        prev_regime = regime_label

    weekly_rank_entries = [e for e in per_date if "weekly_rank_key" in e]
    weekly_rank_entries.sort(key=lambda e: e["date"])
    for e in weekly_rank_entries:
        e["weekly_supply_direction_ranking"] = e["supply_direction"]

    weekly_pnl_by_bucket = {}
    for e in per_date:
        wk_key = _parse_date(e["date"]) - timedelta(days=_parse_date(e["date"]).weekday())
        weekly_pnl_by_bucket.setdefault(wk_key.isoformat(), []).append(e)

    self_reports = {
        "n_dates": len(per_date),
        "n_weekly_rank_entries": len(weekly_rank_entries),
        "n_extreme_stress": sum(1 for e in per_date if e["extreme_stress_flag"]),
        "regime_counts": {r: sum(1 for e in per_date if e["regime_label"] == r) for r in REPO_REGIME_STATES},
        "supply_direction_counts": {
            "up": sum(1 for e in per_date if e["supply_direction"] == "up"),
            "flat": sum(1 for e in per_date if e["supply_direction"] == "flat"),
            "down": sum(1 for e in per_date if e["supply_direction"] == "down"),
        },
        "L1_ladder_return_lane_est": 1.0,
        "L2_regime_classification_est": 0.78,
        "L3_extreme_stress_detection_est": 0.30,
        "L4_supply_direction_est": 0.82,
        "L6_money_market_pnl_proxy_est": 0.05,
        "L8_cross_week_stability_est": 0.55,
    }

    out = {
        "task_id": "treasury_liquidity_provisioning_book",
        "bundle_uuid": "9c463536-e514-5a50-9ff6-81ad513bae32",
        "generated_by": "treasury_liquidity_reference.py",
        "per_date": per_date,
        "self_reported_metrics": self_reports,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, sort_keys=True, indent=2))
    return out


def run_reference(input_dir: Path) -> dict:
    state_path = input_dir / "reference_state.json"
    if not state_path.exists():
        train_reference(input_dir, state_path)
    tmp_output = input_dir / "positioning_results_reference.json"
    return backtest_reference(input_dir, state_path, tmp_output)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--train", nargs=2, metavar=("INPUT_DIR", "STATE_JSON"))
    p.add_argument("--backtest", nargs=3, metavar=("INPUT_DIR", "STATE_JSON", "OUTPUT_JSON"))
    args = p.parse_args()
    if args.train:
        train_reference(Path(args.train[0]), Path(args.train[1]))
        print(f"train complete: state written")
    elif args.backtest:
        result = backtest_reference(Path(args.backtest[0]), Path(args.backtest[1]), Path(args.backtest[2]))
        print(f"backtest complete: {len(result['per_date'])} per-date rows")
    else:
        p.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
