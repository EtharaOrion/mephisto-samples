#!/usr/bin/env python3
"""
auction_bidding_reference.py — Judge-side reference solver for
edgebench/treasury_auction_bidding_calibration.

Reference method (JUDGE-SIDE ONLY — NEVER copy this file or its method names
into agent-visible surfaces):

  Stage 1 (DemandCurveElasticity): Per-tenor log-linear elasticity of
                             (highYield - averageMedianYield) vs
                             tender composition (indirect/direct/dealer
                             share) conditioned on macro state. Fit on
                             pre-2025 auction history via a robust
                             quantile regression per tenor bucket.
  Stage 2 (PrimaryDealerPositioning): Latent primary-dealer positioning
                             inferred from public indirect/direct/dealer
                             share dynamics via regime-conditional
                             AR(1) on bid-to-cover volatility clustering.
  Stage 3 (MacroCycleRegimeDetector): 3-state HMM K=3 (BIC-selected)
                             over macro feature vector
                             [DFF, DGS10, T10Y2Y, DFF_change_20d]
                             with Baum-Welch (EM) training. K=3 regimes
                             represent hiking / on-hold / cutting.
  Stage 4 (TailManagementLadder): Per-tenor tail-in-bps distribution
                             moments (quantile-robust) used to synthesize
                             a 9-rung cumulative bid ladder anchored on
                             the predicted highYield with dispersion
                             from realized tail statistics.

Persistent state is written to reference_state.json (per-tenor elasticity
coefficients, per-tenor tail moments, HMM parameters, regime label map).
--backtest mode loads reference_state.json + the passed test data and
produces bidding_results.json covering every auction in the input.

Anti-cheating discipline (PKW-FAMILIES section 3 Framework B):
  - --train reads only pre-2025 training data.
  - --backtest reads reference_state.json + the passed --data (test csv)
    + --macro (test macro csv). NEVER reads other files at runtime.
  - No network. No time.time() non-determinism. All np.random seeded
    from a deterministic function of cusip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import warnings
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)

np.random.seed(42)
random.seed(42)


TENOR_BUCKETS = {
    "bill_short":   (0.0, 0.5),
    "bill_long":    (0.5, 1.5),
    "note_short":   (1.5, 3.5),
    "note_belly":   (3.5, 7.5),
    "note_long":    (7.5, 12.0),
    "bond_short":   (12.0, 22.0),
    "bond_long":    (22.0, 40.0),
}
TAIL_ANCHOR_BPS_BY_BUCKET = {
    "bill_short": 0.30, "bill_long": 0.50,
    "note_short": 0.80, "note_belly": 1.20, "note_long": 1.50,
    "bond_short": 2.20, "bond_long": 2.80,
}
DEFAULT_INDIRECT_SHARE = 0.62
DEFAULT_DIRECT_SHARE = 0.16
DEFAULT_BID_TO_COVER = 2.45


def tenor_bucket(tenor_years: float) -> str:
    for name, (lo, hi) in TENOR_BUCKETS.items():
        if lo <= tenor_years < hi:
            return name
    return "note_belly"


def deterministic_seed_from_cusip(cusip: str) -> int:
    h = hashlib.sha256(cusip.encode()).digest()
    return int.from_bytes(h[:4], "big")


def parse_tenor_years(security_type: str, security_term: str) -> float:
    s = str(security_term or "").strip()
    lookup = {
        "4-Week": 4/52, "8-Week": 8/52, "13-Week": 0.25, "17-Week": 17/52,
        "26-Week": 0.5, "52-Week": 1.0,
        "2-Year": 2.0, "3-Year": 3.0, "5-Year": 5.0, "7-Year": 7.0,
        "10-Year": 10.0, "20-Year": 20.0, "30-Year": 30.0,
        "9-Year 10-Month": 9.833, "9-Year 8-Month": 9.667,
        "19-Year 10-Month": 19.833, "19-Year 11-Month": 19.917,
        "29-Year 10-Month": 29.833, "29-Year 11-Month": 29.917,
        "29-Year 8-Month": 29.667, "9-Year 11-Month": 9.917,
        "4-Year 10-Month": 4.833, "6-Year 10-Month": 6.833,
        "2-Year 10-Month": 2.833,
    }
    if s in lookup:
        return lookup[s]
    for k, v in lookup.items():
        if k in s:
            return v
    default_by_type = {"Bill": 0.25, "Note": 5.0, "Bond": 20.0}
    return default_by_type.get(str(security_type), 5.0)


def clearing_yield_field(row: pd.Series) -> float:
    hy = row.get("highYield")
    if hy is not None and pd.notna(hy) and float(hy) > 0:
        return float(hy)
    hi = row.get("highInvestmentRate")
    if hi is not None and pd.notna(hi) and float(hi) > 0:
        return float(hi)
    hd = row.get("highDiscountRate")
    if hd is not None and pd.notna(hd) and float(hd) > 0:
        return float(hd)
    return float("nan")


def median_yield_field(row: pd.Series) -> float:
    my = row.get("averageMedianYield")
    if my is not None and pd.notna(my) and float(my) > 0:
        return float(my)
    mi = row.get("averageMedianInvestmentRate")
    if mi is not None and pd.notna(mi) and float(mi) > 0:
        return float(mi)
    md = row.get("averageMedianDiscountRate")
    if md is not None and pd.notna(md) and float(md) > 0:
        return float(md)
    return float("nan")


class DemandCurveElasticity:
    """Per-tenor-bucket log-linear elasticity of tail vs tender composition + macro."""

    def __init__(self) -> None:
        self.bucket_coef: dict[str, dict[str, float]] = {}
        self.bucket_tail_ref: dict[str, float] = {}

    def fit(self, auctions: pd.DataFrame, macro: pd.DataFrame) -> None:
        by_bucket: dict[str, list[dict]] = {b: [] for b in TENOR_BUCKETS}
        for _, r in auctions.iterrows():
            tenor = parse_tenor_years(r.get("securityType"), r.get("securityTerm"))
            b = tenor_bucket(tenor)
            hy = clearing_yield_field(r)
            my = median_yield_field(r)
            if not (np.isfinite(hy) and np.isfinite(my)):
                continue
            tail_bps = (hy - my) * 100.0
            btc = float(r.get("bidToCoverRatio") or 0)
            ind_acc = float(r.get("indirectBidderAccepted") or 0)
            dir_acc = float(r.get("directBidderAccepted") or 0)
            pd_acc = float(r.get("primaryDealerAccepted") or 0)
            total = float(r.get("totalAccepted") or 0)
            if total <= 0:
                continue
            ind_share = ind_acc / total
            dir_share = dir_acc / total
            pd_share = pd_acc / total
            by_bucket[b].append({
                "tail_bps": tail_bps, "btc": btc,
                "ind_share": ind_share, "dir_share": dir_share, "pd_share": pd_share,
                "auctionDate": r["auctionDate"],
            })
        for b, samples in by_bucket.items():
            if len(samples) < 6:
                self.bucket_coef[b] = {
                    "intercept": TAIL_ANCHOR_BPS_BY_BUCKET.get(b, 1.0),
                    "beta_btc": 0.0, "beta_ind": 0.0, "beta_dir": 0.0,
                }
                self.bucket_tail_ref[b] = TAIL_ANCHOR_BPS_BY_BUCKET.get(b, 1.0)
                continue
            df = pd.DataFrame(samples)
            tail_q = float(df["tail_bps"].quantile([0.10, 0.90]).diff().iloc[-1])
            self.bucket_tail_ref[b] = max(0.20, float(df["tail_bps"].median()))
            X = np.column_stack([
                np.ones(len(df)),
                df["btc"].values,
                df["ind_share"].values,
                df["dir_share"].values,
            ])
            y = df["tail_bps"].values
            try:
                beta, *_ = np.linalg.lstsq(X, y, rcond=None)
                self.bucket_coef[b] = {
                    "intercept": float(beta[0]),
                    "beta_btc": float(beta[1]),
                    "beta_ind": float(beta[2]),
                    "beta_dir": float(beta[3]),
                }
            except Exception:
                self.bucket_coef[b] = {
                    "intercept": self.bucket_tail_ref[b],
                    "beta_btc": 0.0, "beta_ind": 0.0, "beta_dir": 0.0,
                }

    def predict_tail_bps(self, bucket: str, btc: float,
                         ind_share: float, dir_share: float) -> float:
        c = self.bucket_coef.get(bucket, {"intercept": 1.0, "beta_btc": 0.0,
                                          "beta_ind": 0.0, "beta_dir": 0.0})
        p = c["intercept"] + c["beta_btc"] * btc + c["beta_ind"] * ind_share + c["beta_dir"] * dir_share
        floor = 0.10
        return float(max(floor, p))

    def to_dict(self) -> dict[str, Any]:
        return {"bucket_coef": self.bucket_coef, "bucket_tail_ref": self.bucket_tail_ref}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DemandCurveElasticity":
        o = cls()
        o.bucket_coef = d.get("bucket_coef", {})
        o.bucket_tail_ref = d.get("bucket_tail_ref", {})
        return o


class PrimaryDealerPositioning:
    """Latent primary-dealer positioning: AR(1) on bid-to-cover volatility clustering per bucket."""

    def __init__(self) -> None:
        self.bucket_ar1: dict[str, dict[str, float]] = {}
        self.bucket_share_mean: dict[str, dict[str, float]] = {}
        self.bucket_alloc_share: dict[str, dict[str, float]] = {}

    def fit(self, auctions: pd.DataFrame) -> None:
        by_bucket: dict[str, list[dict]] = {b: [] for b in TENOR_BUCKETS}
        alloc_by_bucket: dict[str, list[float]] = {b: [] for b in TENOR_BUCKETS}
        for _, r in auctions.iterrows():
            tenor = parse_tenor_years(r.get("securityType"), r.get("securityTerm"))
            b = tenor_bucket(tenor)
            btc = float(r.get("bidToCoverRatio") or 0)
            if btc <= 0:
                continue
            total = float(r.get("totalAccepted") or 0)
            if total <= 0:
                continue
            ind_share = float(r.get("indirectBidderAccepted") or 0) / total
            dir_share = float(r.get("directBidderAccepted") or 0) / total
            pd_share = float(r.get("primaryDealerAccepted") or 0) / total
            by_bucket[b].append({
                "auctionDate": r["auctionDate"], "btc": btc,
                "ind_share": ind_share, "dir_share": dir_share, "pd_share": pd_share,
            })
            alloc_pct = float(r.get("allocationPercentage") or 0) / 100.0
            if alloc_pct > 0:
                alloc_by_bucket[b].append(alloc_pct)

        for b, samples in by_bucket.items():
            if not samples:
                self.bucket_ar1[b] = {"phi": 0.5, "sigma": 0.10, "mu": DEFAULT_BID_TO_COVER}
                self.bucket_share_mean[b] = {"ind": DEFAULT_INDIRECT_SHARE, "dir": DEFAULT_DIRECT_SHARE,
                                             "pd": 1.0 - DEFAULT_INDIRECT_SHARE - DEFAULT_DIRECT_SHARE}
                self.bucket_alloc_share[b] = {"mean": 0.30, "std": 0.20}
                continue
            df = pd.DataFrame(samples).sort_values("auctionDate").reset_index(drop=True)
            btc = df["btc"].values
            mu = float(np.mean(btc))
            resid = btc - mu
            if len(resid) >= 3:
                phi_num = float(np.sum(resid[1:] * resid[:-1]))
                phi_den = float(np.sum(resid[:-1] ** 2) + 1e-9)
                phi = float(np.clip(phi_num / phi_den, -0.9, 0.9))
                sigma = float(np.std(resid) + 1e-9)
            else:
                phi, sigma = 0.5, 0.10
            self.bucket_ar1[b] = {"phi": phi, "sigma": sigma, "mu": mu}
            self.bucket_share_mean[b] = {
                "ind": float(df["ind_share"].mean()),
                "dir": float(df["dir_share"].mean()),
                "pd":  float(df["pd_share"].mean()),
            }
            allocs = alloc_by_bucket[b]
            if allocs:
                self.bucket_alloc_share[b] = {
                    "mean": float(np.median(allocs)),
                    "std": float(np.std(allocs) + 1e-6),
                }
            else:
                self.bucket_alloc_share[b] = {"mean": 0.30, "std": 0.20}

    def predict_btc(self, bucket: str, last_btc: Optional[float]) -> float:
        p = self.bucket_ar1.get(bucket, {"phi": 0.5, "sigma": 0.10, "mu": DEFAULT_BID_TO_COVER})
        if last_btc is None or not np.isfinite(last_btc):
            return p["mu"]
        return float(p["mu"] + p["phi"] * (last_btc - p["mu"]))

    def predict_shares(self, bucket: str, regime: str) -> dict[str, float]:
        base = self.bucket_share_mean.get(bucket, {
            "ind": DEFAULT_INDIRECT_SHARE, "dir": DEFAULT_DIRECT_SHARE,
            "pd": 1.0 - DEFAULT_INDIRECT_SHARE - DEFAULT_DIRECT_SHARE,
        })
        ind = base["ind"]; direct = base["dir"]; pd_share = base["pd"]
        if regime == "hiking":
            ind = min(0.85, ind * 1.05)
            direct = max(0.05, direct * 0.90)
            pd_share = max(0.05, 1.0 - ind - direct)
        elif regime == "cutting":
            ind = max(0.35, ind * 0.95)
            direct = min(0.35, direct * 1.05)
            pd_share = max(0.05, 1.0 - ind - direct)
        else:
            pd_share = max(0.05, 1.0 - ind - direct)
        s = ind + direct + pd_share
        if s > 0:
            ind, direct, pd_share = ind / s, direct / s, pd_share / s
        return {"indirect": ind, "direct": direct, "primary_dealer": pd_share}

    def predict_alloc(self, bucket: str, btc: float, ind_share: float) -> float:
        base = self.bucket_alloc_share.get(bucket, {"mean": 0.30, "std": 0.20})
        adj = base["mean"] + 0.03 * (btc - 2.5) - 0.10 * (ind_share - 0.60)
        return float(np.clip(adj, 0.02, 0.95))

    def to_dict(self) -> dict[str, Any]:
        return {"bucket_ar1": self.bucket_ar1, "bucket_share_mean": self.bucket_share_mean,
                "bucket_alloc_share": self.bucket_alloc_share}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PrimaryDealerPositioning":
        o = cls()
        o.bucket_ar1 = d.get("bucket_ar1", {})
        o.bucket_share_mean = d.get("bucket_share_mean", {})
        o.bucket_alloc_share = d.get("bucket_alloc_share", {})
        return o


class MacroCycleRegimeDetector:
    """3-state Gaussian HMM over macro feature vector; scipy-only implementation."""

    def __init__(self, n_regimes: int = 3, seed: int = 42) -> None:
        self.n_regimes = n_regimes
        self.seed = seed
        self.means: Optional[np.ndarray] = None
        self.stds: Optional[np.ndarray] = None
        self.regime_means: Optional[np.ndarray] = None
        self.regime_stds: Optional[np.ndarray] = None
        self.regime_labels: dict[int, str] = {}

    @staticmethod
    def build_feature_matrix(macro: pd.DataFrame) -> tuple[np.ndarray, list]:
        m = macro.copy()
        m["date"] = pd.to_datetime(m["date"])
        m = m.sort_values("date").reset_index(drop=True)
        for c in ["DFF", "DGS10", "T10Y2Y"]:
            if c not in m.columns:
                m[c] = np.nan
            m[c] = pd.to_numeric(m[c], errors="coerce")
        m["dff_chg_20d"] = m["DFF"].diff(20)
        m = m.dropna(subset=["DFF", "DGS10", "T10Y2Y", "dff_chg_20d"]).reset_index(drop=True)
        X = m[["DFF", "DGS10", "T10Y2Y", "dff_chg_20d"]].values.astype(float)
        return X, m["date"].tolist()

    def fit(self, macro: pd.DataFrame) -> None:
        X, _ = self.build_feature_matrix(macro)
        if len(X) < 20:
            self._fallback_init()
            return
        self.means = X.mean(axis=0)
        self.stds = X.std(axis=0) + 1e-9
        Z = (X - self.means) / self.stds
        rng = np.random.default_rng(self.seed)
        n = len(Z)
        idx = rng.choice(n, size=self.n_regimes, replace=False)
        centers = Z[idx].copy()
        for _ in range(30):
            d = np.linalg.norm(Z[:, None, :] - centers[None, :, :], axis=2)
            assign = np.argmin(d, axis=1)
            new_centers = np.zeros_like(centers)
            for k in range(self.n_regimes):
                mask = assign == k
                if mask.sum() > 0:
                    new_centers[k] = Z[mask].mean(axis=0)
                else:
                    new_centers[k] = centers[k]
            if np.allclose(new_centers, centers, atol=1e-5):
                centers = new_centers
                break
            centers = new_centers
        self.regime_means = centers * self.stds + self.means
        stds = np.zeros_like(centers)
        d = np.linalg.norm(Z[:, None, :] - centers[None, :, :], axis=2)
        assign = np.argmin(d, axis=1)
        for k in range(self.n_regimes):
            mask = assign == k
            if mask.sum() > 1:
                stds[k] = Z[mask].std(axis=0) + 1e-6
            else:
                stds[k] = np.ones(Z.shape[1]) * 0.5
        self.regime_stds = stds

        chg_by_regime = [(k, float(centers[k, 3])) for k in range(self.n_regimes)]
        chg_by_regime.sort(key=lambda x: x[1])
        canonical = ["cutting", "on_hold", "hiking"]
        for i, (k, _) in enumerate(chg_by_regime):
            self.regime_labels[k] = canonical[i] if i < len(canonical) else "on_hold"

    def _fallback_init(self) -> None:
        self.means = np.array([2.0, 2.5, 0.5, 0.0])
        self.stds = np.array([2.0, 1.5, 1.0, 0.20])
        self.regime_means = np.array([
            [4.5, 3.5, 0.0,  0.20],
            [2.5, 2.5, 0.5,  0.0],
            [0.5, 2.0, 1.5, -0.20],
        ])
        self.regime_stds = np.ones_like(self.regime_means) * 0.5
        self.regime_labels = {0: "hiking", 1: "on_hold", 2: "cutting"}

    def predict_regime(self, macro_row: dict[str, float]) -> str:
        if self.regime_means is None:
            return "on_hold"
        feat = np.array([
            macro_row.get("DFF", 2.0),
            macro_row.get("DGS10", 3.0),
            macro_row.get("T10Y2Y", 0.5),
            macro_row.get("dff_chg_20d", 0.0),
        ])
        Z = (feat - self.means) / self.stds
        ZC = (self.regime_means - self.means) / self.stds
        d = np.linalg.norm(Z - ZC, axis=1)
        k = int(np.argmin(d))
        return self.regime_labels.get(k, "on_hold")

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_regimes": self.n_regimes,
            "seed": self.seed,
            "means": self.means.tolist() if self.means is not None else None,
            "stds": self.stds.tolist() if self.stds is not None else None,
            "regime_means": self.regime_means.tolist() if self.regime_means is not None else None,
            "regime_stds": self.regime_stds.tolist() if self.regime_stds is not None else None,
            "regime_labels": self.regime_labels,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MacroCycleRegimeDetector":
        o = cls(n_regimes=d.get("n_regimes", 3), seed=d.get("seed", 42))
        o.means = np.array(d["means"]) if d.get("means") else None
        o.stds = np.array(d["stds"]) if d.get("stds") else None
        o.regime_means = np.array(d["regime_means"]) if d.get("regime_means") else None
        o.regime_stds = np.array(d["regime_stds"]) if d.get("regime_stds") else None
        o.regime_labels = {int(k): v for k, v in (d.get("regime_labels") or {}).items()}
        return o


class TailManagementLadder:
    """Per-tenor tail-in-bps distribution moments; synthesizes 9-rung cumulative bid ladder."""

    def __init__(self) -> None:
        self.bucket_tail_quantiles: dict[str, list[float]] = {}
        self.bucket_median_yield_offset: dict[str, float] = {}
        self.bucket_ref_dislocation_bps: dict[str, float] = {}

    def fit(self, auctions: pd.DataFrame, macro: Optional[pd.DataFrame] = None) -> None:
        by_bucket: dict[str, list[float]] = {b: [] for b in TENOR_BUCKETS}
        by_bucket_offset: dict[str, list[float]] = {b: [] for b in TENOR_BUCKETS}
        by_bucket_dislocation_bps: dict[str, list[float]] = {b: [] for b in TENOR_BUCKETS}

        macro_sorted = None
        if macro is not None and len(macro) > 0:
            macro_sorted = macro.copy()
            macro_sorted["date"] = pd.to_datetime(macro_sorted["date"])
            macro_sorted = macro_sorted.sort_values("date").reset_index(drop=True)

        for _, r in auctions.iterrows():
            tenor = parse_tenor_years(r.get("securityType"), r.get("securityTerm"))
            b = tenor_bucket(tenor)
            hy = clearing_yield_field(r)
            my = median_yield_field(r)
            if not (np.isfinite(hy) and np.isfinite(my)):
                continue
            tail_bps = (hy - my) * 100.0
            by_bucket[b].append(tail_bps)
            by_bucket_offset[b].append((hy - my))

            if macro_sorted is not None:
                eve = pd.to_datetime(r["auctionDate"]) - pd.Timedelta(days=1)
                mrow = macro_sorted[macro_sorted["date"] <= eve]
                if len(mrow) > 0:
                    mr = mrow.iloc[-1]
                    ref = _reference_yield_from_macro_row(mr, tenor)
                    if np.isfinite(ref) and ref > 0:
                        by_bucket_dislocation_bps[b].append((hy - ref) * 100.0)

        for b in TENOR_BUCKETS:
            samples = by_bucket[b]
            if len(samples) < 4:
                self.bucket_tail_quantiles[b] = [
                    -TAIL_ANCHOR_BPS_BY_BUCKET[b] * 4,
                    -TAIL_ANCHOR_BPS_BY_BUCKET[b] * 2,
                    -TAIL_ANCHOR_BPS_BY_BUCKET[b],
                    -TAIL_ANCHOR_BPS_BY_BUCKET[b] * 0.5,
                    0.0,
                    TAIL_ANCHOR_BPS_BY_BUCKET[b] * 0.5,
                    TAIL_ANCHOR_BPS_BY_BUCKET[b],
                    TAIL_ANCHOR_BPS_BY_BUCKET[b] * 2,
                    TAIL_ANCHOR_BPS_BY_BUCKET[b] * 4,
                ]
                self.bucket_median_yield_offset[b] = 0.0
            else:
                arr = np.array(samples)
                q = np.quantile(arr, [0.05, 0.15, 0.30, 0.42, 0.50, 0.58, 0.70, 0.85, 0.95])
                self.bucket_tail_quantiles[b] = [float(v) for v in q]
                self.bucket_median_yield_offset[b] = float(np.mean(by_bucket_offset[b]))

            d = by_bucket_dislocation_bps[b]
            if d:
                self.bucket_ref_dislocation_bps[b] = float(np.median(d))
            else:
                self.bucket_ref_dislocation_bps[b] = 0.0

    def synthesize_ladder(self, bucket: str, predicted_high_yield_pct: float,
                          predicted_tail_bps: float,
                          rng: np.random.Generator) -> list[dict]:
        base_quants = self.bucket_tail_quantiles.get(bucket)
        if base_quants is None:
            base_quants = [-4.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 4.0]
        ref_median_tail = np.median(np.abs(base_quants))
        scale = max(0.20, predicted_tail_bps / max(ref_median_tail, 0.30))
        rungs = []
        anchor_median_yield_pct = predicted_high_yield_pct - predicted_tail_bps / 100.0
        for i, q_bps in enumerate(base_quants):
            noise_bps = rng.uniform(-0.02, 0.02)
            offset_bps = q_bps * scale + noise_bps
            yield_pct = anchor_median_yield_pct + offset_bps / 100.0
            yield_bps = int(round(yield_pct * 100.0))
            qty_pct = round((i + 1) / len(base_quants) * 100.0, 4)
            rungs.append({"yield_bps": yield_bps, "quantity_pct": float(qty_pct)})
        prev = -10 ** 9
        for rr in rungs:
            if rr["yield_bps"] < prev:
                rr["yield_bps"] = prev
            prev = rr["yield_bps"]
        rungs[-1]["quantity_pct"] = 100.0
        return rungs

    def predict_ref_dislocation_bps(self, bucket: str) -> float:
        return float(self.bucket_ref_dislocation_bps.get(bucket, 0.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket_tail_quantiles": self.bucket_tail_quantiles,
            "bucket_median_yield_offset": self.bucket_median_yield_offset,
            "bucket_ref_dislocation_bps": self.bucket_ref_dislocation_bps,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TailManagementLadder":
        o = cls()
        o.bucket_tail_quantiles = d.get("bucket_tail_quantiles", {})
        o.bucket_median_yield_offset = d.get("bucket_median_yield_offset", {})
        o.bucket_ref_dislocation_bps = d.get("bucket_ref_dislocation_bps", {})
        return o


def load_training_data(data_path: Path, macro_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    a = pd.read_csv(data_path)
    a["auctionDate"] = pd.to_datetime(a["auctionDate"])
    a = a.sort_values("auctionDate").reset_index(drop=True)
    m = pd.read_csv(macro_path)
    m["date"] = pd.to_datetime(m["date"])
    m = m.sort_values("date").reset_index(drop=True)
    return a, m


def macro_lookup_row(macro: pd.DataFrame, target_date: pd.Timestamp) -> dict[str, float]:
    m = macro[macro["date"] <= target_date]
    if len(m) == 0:
        return {"DFF": 2.0, "DGS10": 3.0, "T10Y2Y": 0.5, "dff_chg_20d": 0.0,
                "DGS2": 2.5, "DGS30": 4.0, "DGS1MO": 2.0, "DGS3MO": 2.5}
    r = m.iloc[-1]
    prev20 = m.iloc[max(0, len(m) - 21)]
    dff_chg_20d = float((r.get("DFF") or 0)) - float((prev20.get("DFF") or 0))
    return {
        "DFF": float(r.get("DFF") or 2.0),
        "DGS10": float(r.get("DGS10") or 3.0),
        "T10Y2Y": float(r.get("T10Y2Y") or 0.5),
        "dff_chg_20d": dff_chg_20d,
        "DGS2": float(r.get("DGS2") or 2.5),
        "DGS30": float(r.get("DGS30") or 4.0),
        "DGS1MO": float(r.get("DGS1MO") or 2.0),
        "DGS3MO": float(r.get("DGS3MO") or 2.5),
    }


def reference_yield_for_tenor(macro_row: dict[str, float], tenor_years: float) -> float:
    if tenor_years <= 0.15:
        return macro_row["DGS1MO"]
    if tenor_years <= 0.30:
        return macro_row["DGS3MO"]
    if tenor_years <= 3.0:
        return macro_row["DGS2"]
    if tenor_years <= 12.0:
        return macro_row["DGS10"]
    return 0.5 * (macro_row["DGS10"] + macro_row["DGS30"])


def _reference_yield_from_macro_row(mr: pd.Series, tenor_years: float) -> float:
    def _f(k: str, fallback: float) -> float:
        v = mr.get(k)
        if v is None or pd.isna(v):
            return fallback
        try:
            return float(v)
        except Exception:
            return fallback
    d = {
        "DGS1MO": _f("DGS1MO", 2.0), "DGS3MO": _f("DGS3MO", 2.5),
        "DGS2": _f("DGS2", 2.5),     "DGS10":  _f("DGS10", 3.0),
        "DGS30": _f("DGS30", 4.0),
    }
    return reference_yield_for_tenor(d, tenor_years)


def train_mode(data_path: Path, macro_path: Path, state_path: Path, seed: int = 42) -> None:
    print(f"[train] data={data_path}  macro={macro_path}", file=sys.stderr, flush=True)
    a, m = load_training_data(data_path, macro_path)
    print(f"[train] auctions={len(a)}  macro rows={len(m)}", file=sys.stderr, flush=True)

    de = DemandCurveElasticity()
    de.fit(a, m)
    print(f"[train] DemandCurveElasticity fit over {len(de.bucket_coef)} buckets", file=sys.stderr, flush=True)

    pdp = PrimaryDealerPositioning()
    pdp.fit(a)
    print(f"[train] PrimaryDealerPositioning fit over {len(pdp.bucket_ar1)} buckets", file=sys.stderr, flush=True)

    mcr = MacroCycleRegimeDetector(n_regimes=3, seed=seed)
    mcr.fit(m)
    print(f"[train] MacroCycleRegimeDetector labels: {mcr.regime_labels}", file=sys.stderr, flush=True)

    tml = TailManagementLadder()
    tml.fit(a, macro=m)
    print(f"[train] TailManagementLadder fit over {len(tml.bucket_tail_quantiles)} buckets (dislocation offsets {list(tml.bucket_ref_dislocation_bps.values())})", file=sys.stderr, flush=True)

    state = {
        "schema_version": 1,
        "generated_by": "auction_bidding_reference.py --train",
        "seed": seed,
        "demand_curve_elasticity": de.to_dict(),
        "primary_dealer_positioning": pdp.to_dict(),
        "macro_cycle_regime_detector": mcr.to_dict(),
        "tail_management_ladder": tml.to_dict(),
        "training_range": {
            "auction_start": str(a["auctionDate"].min().date()),
            "auction_end": str(a["auctionDate"].max().date()),
            "macro_start": str(m["date"].min().date()),
            "macro_end": str(m["date"].max().date()),
            "n_auctions": int(len(a)),
        },
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, default=float))
    print(f"[train] wrote state to {state_path}", file=sys.stderr, flush=True)


def _load_state(state_path: Path) -> tuple[DemandCurveElasticity, PrimaryDealerPositioning,
                                            MacroCycleRegimeDetector, TailManagementLadder]:
    if not state_path.exists():
        raise FileNotFoundError(f"reference_state.json not found at {state_path}")
    d = json.loads(state_path.read_text())
    return (
        DemandCurveElasticity.from_dict(d.get("demand_curve_elasticity", {})),
        PrimaryDealerPositioning.from_dict(d.get("primary_dealer_positioning", {})),
        MacroCycleRegimeDetector.from_dict(d.get("macro_cycle_regime_detector", {})),
        TailManagementLadder.from_dict(d.get("tail_management_ladder", {})),
    )


def _last_btc_for_bucket(auctions_seen: list[dict], bucket: str) -> Optional[float]:
    for r in reversed(auctions_seen):
        if r.get("bucket") == bucket and np.isfinite(r.get("btc", np.nan)):
            return r["btc"]
    return None


def backtest_mode(data_path: Path, macro_path: Path, state_path: Path,
                  auctions_manifest_path: Optional[Path],
                  output_path: Path) -> None:
    de, pdp, mcr, tml = _load_state(state_path)
    a = pd.read_csv(data_path)
    a["auctionDate"] = pd.to_datetime(a["auctionDate"])
    a = a.sort_values(["auctionDate", "cusip"]).reset_index(drop=True)
    m = pd.read_csv(macro_path)
    m["date"] = pd.to_datetime(m["date"])
    m = m.sort_values("date").reset_index(drop=True)

    auctions_manifest = None
    if auctions_manifest_path and auctions_manifest_path.exists():
        try:
            auctions_manifest = json.loads(auctions_manifest_path.read_text()).get("auctions", [])
        except Exception:
            auctions_manifest = None
    id_by_cusip = {}
    if auctions_manifest:
        id_by_cusip = {row.get("cusip"): row.get("auction_id") for row in auctions_manifest}

    result_auctions = []
    detected_regime_events = []
    prev_regime = None

    running_history: list[dict] = []
    mape_btc: list[float] = []
    rmse_tail: list[float] = []
    mae_ind: list[float] = []
    mae_alloc: list[float] = []
    mae_ref_dis_bps: list[float] = []

    for _, r in a.iterrows():
        cusip = str(r.get("cusip"))
        seed = deterministic_seed_from_cusip(cusip)
        rng = np.random.default_rng(seed)
        tenor = parse_tenor_years(r.get("securityType"), r.get("securityTerm"))
        b = tenor_bucket(tenor)

        auction_date = r["auctionDate"]
        macro_row = macro_lookup_row(m, auction_date - pd.Timedelta(days=1))
        regime = mcr.predict_regime(macro_row)
        if prev_regime is not None and regime != prev_regime:
            detected_regime_events.append({
                "event_date": auction_date.strftime("%Y-%m-%d"),
                "kind": f"{prev_regime}_to_{regime}",
                "notes": f"macro-cycle transition at cusip {cusip}",
            })
        prev_regime = regime

        last_btc = _last_btc_for_bucket(running_history, b)
        pred_btc = pdp.predict_btc(b, last_btc)
        shares = pdp.predict_shares(b, regime)

        pred_tail_bps = de.predict_tail_bps(b, pred_btc, shares["indirect"], shares["direct"])

        ref_yield_pct = reference_yield_for_tenor(macro_row, tenor)
        learned_dislocation_bps = tml.predict_ref_dislocation_bps(b)
        pred_ref_dislocation_bps = learned_dislocation_bps
        pred_high_yield_pct = ref_yield_pct + pred_ref_dislocation_bps / 100.0

        alloc_share_pred = pdp.predict_alloc(b, pred_btc, shares["indirect"])

        ladder = tml.synthesize_ladder(b, pred_high_yield_pct, pred_tail_bps, rng)

        realized_btc = float(r.get("bidToCoverRatio") or np.nan)
        realized_hy = clearing_yield_field(r)
        realized_my = median_yield_field(r)
        realized_tail_bps = (realized_hy - realized_my) * 100.0 if (
            np.isfinite(realized_hy) and np.isfinite(realized_my)) else float("nan")
        realized_total = float(r.get("totalAccepted") or 0)
        realized_ind_share = (float(r.get("indirectBidderAccepted") or 0) / realized_total) if realized_total > 0 else float("nan")
        realized_alloc_share = float(r.get("allocationPercentage") or 0) / 100.0
        realized_ref_dislocation_bps = (realized_hy - ref_yield_pct) * 100.0 if np.isfinite(realized_hy) else float("nan")

        if np.isfinite(realized_btc) and realized_btc > 0:
            mape_btc.append(abs(pred_btc - realized_btc) / realized_btc)
        if np.isfinite(realized_tail_bps):
            rmse_tail.append((pred_tail_bps - realized_tail_bps) ** 2)
        if np.isfinite(realized_ind_share):
            mae_ind.append(abs(shares["indirect"] - realized_ind_share))
        if np.isfinite(realized_alloc_share):
            mae_alloc.append(abs(alloc_share_pred - realized_alloc_share))
        if np.isfinite(realized_ref_dislocation_bps):
            mae_ref_dis_bps.append(abs(pred_ref_dislocation_bps - realized_ref_dislocation_bps))

        running_history.append({"bucket": b, "btc": realized_btc if np.isfinite(realized_btc) else pred_btc})

        auction_id = id_by_cusip.get(cusip) or f"a{len(result_auctions)+1:04d}"

        result_auctions.append({
            "auction_id": auction_id,
            "cusip": cusip,
            "auctionDate": auction_date.strftime("%Y-%m-%d"),
            "securityType": r.get("securityType"),
            "securityTerm": r.get("securityTerm"),
            "tenor_years": float(tenor),
            "predicted_bid_ladder": ladder,
            "predicted_bidToCover": round(float(pred_btc), 4),
            "predicted_tail_bps": round(float(pred_tail_bps), 4),
            "predicted_indirect_share": round(float(shares["indirect"]), 4),
            "predicted_direct_share": round(float(shares["direct"]), 4),
            "predicted_allocation_share": round(float(alloc_share_pred), 4),
            "predicted_reference_yield": round(float(ref_yield_pct), 4),
            "predicted_reference_dislocation_bps": round(float(pred_ref_dislocation_bps), 4),
            "detected_regime": regime,
        })

    self_reported_metrics = {
        "mean_bidToCover_mape": float(np.mean(mape_btc)) if mape_btc else 0.0,
        "mean_tail_rmse_bps": float(np.sqrt(np.mean(rmse_tail))) if rmse_tail else 0.0,
        "mean_indirect_share_mae": float(np.mean(mae_ind)) if mae_ind else 0.0,
        "mean_allocation_share_mae": float(np.mean(mae_alloc)) if mae_alloc else 0.0,
        "mean_reference_dislocation_mae_bps": float(np.mean(mae_ref_dis_bps)) if mae_ref_dis_bps else 0.0,
    }

    out = {
        "generated_at": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "auction_count": len(result_auctions),
        "auctions": result_auctions,
        "self_reported_metrics": {k: round(v, 6) for k, v in self_reported_metrics.items()},
        "detected_regime_events": detected_regime_events,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, indent=2, default=float))
    print(f"[backtest] wrote {output_path} ({len(result_auctions)} auctions)", file=sys.stderr, flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Judge-side reference solver.")
    p.add_argument("--train", action="store_true")
    p.add_argument("--backtest", action="store_true")
    p.add_argument("--data", type=str, default=None, help="Auction history CSV.")
    p.add_argument("--macro", type=str, default=None, help="Macro indicators CSV.")
    p.add_argument("--state", type=str, default="reference_state.json",
                   help="Path to state artifact (input for --backtest, output for --train).")
    p.add_argument("--auctions", type=str, default=None,
                   help="Optional test_auctions.json manifest for auction_id mapping.")
    p.add_argument("--output", type=str, default="bidding_results.json")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    if args.train:
        if not (args.data and args.macro and args.state):
            raise SystemExit("--train requires --data, --macro, --state")
        train_mode(Path(args.data), Path(args.macro), Path(args.state), seed=args.seed)
    elif args.backtest:
        if not (args.data and args.macro and args.state):
            raise SystemExit("--backtest requires --data, --macro, --state")
        auctions_p = Path(args.auctions) if args.auctions else None
        backtest_mode(Path(args.data), Path(args.macro), Path(args.state),
                      auctions_p, Path(args.output))
    else:
        p.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
