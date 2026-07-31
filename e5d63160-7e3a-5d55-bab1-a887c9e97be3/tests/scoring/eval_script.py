#!/usr/bin/env python3
"""
eval_script.py — judge-side per-cycle scoring runner for bank capital
projection. Invokes the agent's --backtest once against the hidden 2025
quarterly panel, parses projection_results.json, per-observation recomputes
the metric-space errors, calls score.py per observation, aggregates with
cross-size-bucket stability and PCA-zone-transition bonus.

Emits: TOTAL_SCORE <N> on stdout for the Harbor scorer_manifest parser.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import (
    score_observation, score_L7_anti_fabrication,
    cross_size_bucket_stability_score, pca_zone_transition_bonus,
    LANE_WEIGHTS, LANE_TOTAL,
    CAPITAL_METRICS_ANCHOR, EARNINGS_METRICS_ANCHOR, TAIL_METRICS_ANCHOR,
    _pca_zone,
)

WORKSPACE = Path("/home/workspace")
SCORING = WORKSPACE / "scoring"
AGENT_SCRIPT = WORKSPACE / "bank_capital_projection.py"
STATE_JSON = WORKSPACE / "reference_state.json"

BACKTEST_TIMEOUT_SEC = 2700


def _find(*rel: str) -> Path:
    for base in (WORKSPACE, SCORING):
        p = base / rel[0]
        if p.exists():
            return p
    return WORKSPACE / rel[0]


def _load_test_institutions() -> list[dict]:
    p = _find("test_institutions.json")
    return json.loads(p.read_text()).get("institutions", [])


def _load_true_pca_events() -> list[dict]:
    p = _find("true_pca_zone_events.json")
    if not p.exists():
        return []
    return json.loads(p.read_text()).get("events", [])


def _load_test_financials() -> pd.DataFrame:
    p = _find("financials_test.csv")
    df = pd.read_csv(p)
    df["REPDTE"] = df["REPDTE"].astype(str)
    df = df.sort_values(["CERT", "REPDTE"]).reset_index(drop=True)
    return df


def _load_train_financials_for_prior() -> pd.DataFrame:
    for name in ("financials_train.csv",):
        p = _find(name)
        if p.exists():
            df = pd.read_csv(p)
            df["REPDTE"] = df["REPDTE"].astype(str)
            df = df.sort_values(["CERT", "REPDTE"]).reset_index(drop=True)
            return df
    return pd.DataFrame()


def _invoke_agent_backtest() -> tuple[bool, str, dict | None]:
    output_path = WORKSPACE / "projection_results.json"
    if not AGENT_SCRIPT.exists():
        return False, f"agent script not found at {AGENT_SCRIPT}", None
    data_p = _find("financials_test.csv")
    macro_p = _find("macro_indicators_test.csv")
    inst_p = _find("test_institutions.json")
    cmd = [
        sys.executable, str(AGENT_SCRIPT),
        "--backtest",
        f"--data={data_p}",
        f"--macro={macro_p}",
        f"--institutions={inst_p}",
        f"--state={STATE_JSON}",
        f"--output={output_path}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=BACKTEST_TIMEOUT_SEC)
        if r.returncode != 0:
            return False, f"agent returncode={r.returncode}: {r.stderr[-1000:]}", None
        if not output_path.exists():
            return False, "projection_results.json not produced", None
        d = json.loads(output_path.read_text())
        return True, "ok", d
    except subprocess.TimeoutExpired:
        return False, "agent timeout", None
    except Exception as e:
        return False, f"agent invocation failed: {e}", None


def main() -> None:
    print("=" * 70)
    print(f"eval_script.py started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    manifest = _load_test_institutions()
    true_events = _load_true_pca_events()
    hist = _load_test_financials()
    prior_hist = _load_train_financials_for_prior()
    print(f"Loaded {len(manifest)} test institutions, {len(true_events)} true PCA-zone events, "
          f"{len(hist)} realized rows, prior-train rows={len(prior_hist)}")

    ok, msg, br = _invoke_agent_backtest()
    if not ok:
        print(f"FAIL: {msg}")
        print(f"TOTAL_SCORE 0.00")
        report = {"error": msg, "final_total": 0.0}
        try:
            (WORKSPACE / "score_report.json").write_text(json.dumps(report, indent=2))
        except Exception:
            pass
        sys.exit(1)
    assert br is not None
    pred_by_key: dict[tuple[int, str], dict] = {}
    for p in br.get("observations", []):
        cert = int(p.get("cert") or 0)
        rep = str(p.get("repdte") or "")
        pred_by_key[(cert, rep)] = p
    detected_events = br.get("detected_pca_zone_events", [])
    self_reported = br.get("self_reported_metrics", {})

    per_obs_scores: list[dict] = []
    judge_bucket = {
        "capital_mae_pp": [],
        "earnings_mape": [],
        "tail_mae_pp": [],
        "asset_growth_mae": [],
        "deposit_growth_mae": [],
        "zone_correct": 0,
        "zone_total": 0,
    }

    last_asset_by_cert: dict[int, float] = {}
    last_dep_by_cert: dict[int, float] = {}
    if len(prior_hist):
        prior_2024q4 = prior_hist[prior_hist["REPDTE"] == "20241231"]
        for _, r in prior_2024q4.iterrows():
            cert = int(r["CERT"]) if pd.notna(r["CERT"]) else 0
            last_asset_by_cert[cert] = float(r.get("ASSET") or 0.0)
            last_dep_by_cert[cert] = float(r.get("DEPDOM") or 0.0)

    for _, r in hist.iterrows():
        cert = int(r["CERT"]) if pd.notna(r["CERT"]) else 0
        repdte = str(r["REPDTE"])
        pred = pred_by_key.get((cert, repdte))
        if pred is None:
            per_obs_scores.append({
                "cert": cert, "repdte": repdte,
                "size_bucket": "community",
                "lanes": {k: 0.0 for k in LANE_WEIGHTS if k not in ("L7_anti_fabrication", "L8_cross_size_bucket_stability")},
                "sub_total": 0.0,
                "missing_prediction": True,
            })
            continue

        prior_asset = last_asset_by_cert.get(cert, 0.0)
        prior_dep = last_dep_by_cert.get(cert, 0.0)
        s = score_observation(pred, dict(r), prior_asset, prior_dep)
        per_obs_scores.append(s)

        capital_errs = []
        for m in CAPITAL_METRICS_ANCHOR:
            p = pred.get("predicted_metrics", {}).get(m)
            rv = r.get(m)
            try:
                fv = float(rv)
                if p is not None and np.isfinite(fv):
                    capital_errs.append(abs(float(p) - fv))
            except Exception:
                pass
        if capital_errs:
            judge_bucket["capital_mae_pp"].extend(capital_errs)

        earnings_errs = []
        for m in EARNINGS_METRICS_ANCHOR:
            p = pred.get("predicted_metrics", {}).get(m)
            rv = r.get(m)
            try:
                fv = float(rv)
                if p is not None and np.isfinite(fv) and abs(fv) > 0.01:
                    earnings_errs.append(abs(float(p) - fv) / max(abs(fv), 0.1))
            except Exception:
                pass
        if earnings_errs:
            judge_bucket["earnings_mape"].extend(earnings_errs)

        tail_errs = []
        for m in TAIL_METRICS_ANCHOR:
            p = pred.get("predicted_metrics", {}).get(m)
            rv = r.get(m)
            try:
                fv = float(rv)
                if p is not None and np.isfinite(fv):
                    tail_errs.append(abs(float(p) - fv))
            except Exception:
                pass
        if tail_errs:
            judge_bucket["tail_mae_pp"].extend(tail_errs)

        current_asset = float(r.get("ASSET") or 0.0)
        if prior_asset > 0 and current_asset > 0:
            realized_ag = (current_asset - prior_asset) / prior_asset
            judge_bucket["asset_growth_mae"].append(abs(float(pred.get("predicted_asset_growth_rate") or 0.0) - realized_ag))
        current_dep = float(r.get("DEPDOM") or 0.0)
        if prior_dep > 0 and current_dep > 0:
            realized_dg = (current_dep - prior_dep) / prior_dep
            judge_bucket["deposit_growth_mae"].append(abs(float(pred.get("predicted_deposit_growth_rate") or 0.0) - realized_dg))

        try:
            rt1 = float(r.get("IDT1RWAJR"))
            rrb = float(r.get("RBCRWAJ"))
            rlev = float(r.get("RBC1AAJ"))
            if all(np.isfinite(x) for x in (rt1, rrb, rlev)):
                real_zone = _pca_zone(rt1, rrb, rlev)
                judge_bucket["zone_total"] += 1
                if str(pred.get("predicted_pca_zone")) == real_zone:
                    judge_bucket["zone_correct"] += 1
        except Exception:
            pass

        last_asset_by_cert[cert] = current_asset
        last_dep_by_cert[cert] = current_dep

    judge_metrics = {
        "mean_capital_ratio_mae_pp": float(np.mean(judge_bucket["capital_mae_pp"])) if judge_bucket["capital_mae_pp"] else 0.0,
        "mean_earnings_mape": float(np.mean(judge_bucket["earnings_mape"])) if judge_bucket["earnings_mape"] else 0.0,
        "mean_tail_bound_mae_pp": float(np.mean(judge_bucket["tail_mae_pp"])) if judge_bucket["tail_mae_pp"] else 0.0,
        "mean_asset_growth_mae": float(np.mean(judge_bucket["asset_growth_mae"])) if judge_bucket["asset_growth_mae"] else 0.0,
        "mean_deposit_growth_mae": float(np.mean(judge_bucket["deposit_growth_mae"])) if judge_bucket["deposit_growth_mae"] else 0.0,
        "pca_zone_accuracy": float(judge_bucket["zone_correct"] / max(judge_bucket["zone_total"], 1)),
    }

    l7_pts, l7_veto, l7_notes = score_L7_anti_fabrication(self_reported, judge_metrics)
    if l7_veto:
        for row in per_obs_scores:
            row["lanes"]["L1_capital_ratio_projection"] = 0.0
            row["lanes"]["L2_earnings_projection"] = 0.0
            row["sub_total"] = sum(row["lanes"].values())

    n = max(len(per_obs_scores), 1)
    lane_avg: dict[str, float] = {}
    for k in ["L1_capital_ratio_projection", "L2_earnings_projection", "L3_tail_risk_control",
              "L4_pca_zone_classification", "L5_asset_growth_projection", "L6_deposit_stability"]:
        vals = [row["lanes"].get(k, 0.0) for row in per_obs_scores]
        lane_avg[k] = float(np.mean(vals)) if vals else 0.0
    lane_avg["L7_anti_fabrication"] = l7_pts
    lane_avg["L8_cross_size_bucket_stability"] = cross_size_bucket_stability_score(per_obs_scores)

    bonus, hits, total_evts = pca_zone_transition_bonus(detected_events, true_events, tolerance_quarters=1)
    print(f"detected PCA-zone events: {len(detected_events)}; matched {hits}/{total_evts} true events; bonus={bonus:.2f}")

    base_total = sum(lane_avg.values())

    print(f"\n=== Per-Lane Averages Across {n} Observations ===")
    for k, v in lane_avg.items():
        print(f"  {k:36s} {v:6.2f} / {LANE_WEIGHTS[k]}")
    print(f"  {'Base total':36s} {base_total:6.2f} / {LANE_TOTAL}")
    print(f"  {'PCA-zone-transition bonus':36s} {bonus:6.2f} / 10")

    total = base_total + bonus
    total = max(0.0, min(total, 110.0))

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_observations": n,
        "lane_averages": lane_avg,
        "l7_veto": l7_veto,
        "l7_notes": l7_notes,
        "judge_metrics": judge_metrics,
        "self_reported_metrics": self_reported,
        "pca_zone_transition_bonus": bonus,
        "detected_pca_events": len(detected_events),
        "true_pca_events_matched": hits,
        "true_pca_events_total": total_evts,
        "base_total": base_total,
        "final_total": total,
        "per_observation_sample": per_obs_scores[:50],
    }
    try:
        (WORKSPACE / "score_report.json").write_text(json.dumps(report, indent=2, default=float))
        print(f"\nScore report written to {WORKSPACE / 'score_report.json'}")
    except Exception as e:
        print(f"WARN could not write score_report.json: {e}")

    print(f"\nFinal total score: {total:.2f} / 110")
    print(f"TOTAL_SCORE {total:.2f}")


if __name__ == "__main__":
    main()
