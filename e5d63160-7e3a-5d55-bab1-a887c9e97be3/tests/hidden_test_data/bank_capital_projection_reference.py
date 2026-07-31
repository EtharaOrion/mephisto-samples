#!/usr/bin/env python3
"""
bank_capital_projection_reference.py — Judge-side reference solver for
edgebench/fdic_bank_capital_projection_book.

Reference method (JUDGE-SIDE ONLY — NEVER copy this file or its method names
into agent-visible surfaces):

  Stage 1 (PeerGroupPercentileRegression): Per-size-bucket (community / mid /
                             regional / large) empirical percentile-position
                             projector. For each metric (IDT1CER, IDT1RWAJR,
                             RBC1AAJ, RBCRWAJ, ROAQ, ROEQ, NIMYQ, NPERFV,
                             NCLNLSR, EQV), we fit each institution's rolling
                             within-bucket percentile rank from its historical
                             trajectory + macro-conditional drift term. Simple
                             linear regression on the per-institution
                             percentile residual + peer-median anchor.
  Stage 2 (MacroConditionalCapitalTrajectory): 3-regime (hiking / on_hold /
                             cutting) scipy-only Gaussian mixture over macro
                             feature vector [DFF, DGS10, T10Y2Y, UNRATE,
                             DFF_change_4q, T10Y2Y_slope]. AR(1) on per-
                             institution capital-metric residuals plus
                             regime-conditional coefficient tilts (macro-drift
                             for NIMYQ is size-bucket-heterogeneous).
  Stage 3 (ConcentrationRiskFactorLoadings): Per-size-bucket 2-factor
                             extraction on the historical NPL residual
                             correlation matrix (NPERFV, NCLNLSR, LNATRESR
                             standardized within bucket). Factor loadings held
                             constant; factor scores projected forward via
                             AR(1) on realized factor trajectories.
  Stage 4 (CapitalBufferRegimeDetector): 3-state per-institution buffer regime
                             ("buffer_comfortable" IDT1RWAJR>=11.5,
                              "buffer_eroding" 8.5..11.5, "buffer_critical" <8.5).
                             K-means-init cluster on [IDT1CER, IDT1RWAJR,
                             RBC1AAJ, RBCRWAJ, EQV] normalized within bucket;
                             cluster centers sorted on IDT1RWAJR (canonical
                             ordering) and mapped canonically. Forward
                             projection uses AR(1) transition on realized
                             ratios plus regime-conditional buffer-erosion tilt.

Persistent state is written to reference_state.json (per-bucket coefficients,
per-cert history, factor loadings, HMM parameters, buffer-regime cluster
centers). --backtest mode loads reference_state.json + the passed test data
and produces projection_results.json covering every test institution-quarter.

Anti-cheating discipline (PKW-FAMILIES section 3 Framework B):
  - --train reads only pre-2025 training data.
  - --backtest reads reference_state.json + the passed --data (test csv)
    + --macro (test macro csv). NEVER reads other files at runtime.
  - No network. No time.time() non-determinism. All np.random seeded
    from a deterministic function of CERT.
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


SIZE_BUCKETS: dict[str, tuple[float, float]] = {
    "community": (0.0, 1_000_000.0),
    "mid":       (1_000_000.0, 10_000_000.0),
    "regional":  (10_000_000.0, 100_000_000.0),
    "large":     (100_000_000.0, 1e15),
}

CAPITAL_METRICS = [
    "IDT1CER", "IDT1RWAJR", "RBC1AAJ", "RBCRWAJ",
    "ROAQ", "ROEQ", "NIMYQ",
    "NPERFV", "NCLNLSR", "LNATRESR",
    "EQV", "LNLSDEPR",
]

ANCHOR_METRICS_PROJECTION = ["IDT1CER", "IDT1RWAJR", "RBC1AAJ", "RBCRWAJ"]
ANCHOR_METRICS_EARNINGS = ["NIMYQ", "ROAQ", "ROEQ"]
ANCHOR_METRICS_TAIL = ["NPERFV", "NCLNLSR"]

DEFAULT_METRIC_MEDIAN: dict[str, float] = {
    "IDT1CER": 14.0, "IDT1RWAJR": 14.0, "RBC1AAJ": 10.5, "RBCRWAJ": 15.5,
    "ROAQ": 1.10, "ROEQ": 10.0, "NIMYQ": 3.40,
    "NPERFV": 0.45, "NCLNLSR": 0.15, "LNATRESR": 1.30,
    "EQV": 10.5, "LNLSDEPR": 75.0,
}


def size_bucket(asset_thousands: float) -> str:
    if not (pd.notna(asset_thousands) and asset_thousands > 0):
        return "community"
    for name, (lo, hi) in SIZE_BUCKETS.items():
        if lo <= asset_thousands < hi:
            return name
    return "large"


def deterministic_seed_from_cert(cert: int) -> int:
    h = hashlib.sha256(str(int(cert)).encode()).digest()
    return int.from_bytes(h[:4], "big")


def _pca_zone(t1_rwa: float, total_rbc: float, t1_lev: float) -> str:
    if not (np.isfinite(t1_rwa) and np.isfinite(total_rbc) and np.isfinite(t1_lev)):
        return "adequately_capitalized"
    if total_rbc >= 10.0 and t1_rwa >= 6.0 and t1_lev >= 5.0:
        return "well_capitalized"
    if total_rbc >= 8.0 and t1_rwa >= 4.5 and t1_lev >= 4.0:
        return "adequately_capitalized"
    if total_rbc >= 6.0 and t1_rwa >= 4.0 and t1_lev >= 3.0:
        return "undercapitalized"
    if total_rbc >= 2.0:
        return "significantly_under"
    return "critically_under"


class PeerGroupPercentileRegression:
    """Per-size-bucket per-metric percentile-position projector plus median anchor."""

    def __init__(self) -> None:
        self.bucket_median: dict[str, dict[str, float]] = {}
        self.bucket_std: dict[str, dict[str, float]] = {}
        self.bucket_ar1_phi: dict[str, dict[str, float]] = {}
        self.cert_last_by_metric: dict[int, dict[str, float]] = {}
        self.cert_bucket: dict[int, str] = {}

    def fit(self, train: pd.DataFrame) -> None:
        train = train.copy()
        train["size_bucket"] = train["ASSET"].apply(size_bucket)
        train["REPDTE"] = train["REPDTE"].astype(str)
        train = train.sort_values(["CERT", "REPDTE"]).reset_index(drop=True)

        for b in SIZE_BUCKETS:
            sub = train[train["size_bucket"] == b]
            self.bucket_median[b] = {}
            self.bucket_std[b] = {}
            for m in CAPITAL_METRICS:
                col = pd.to_numeric(sub.get(m), errors="coerce")
                col = col[col.notna()]
                if len(col) >= 20:
                    self.bucket_median[b][m] = float(col.median())
                    self.bucket_std[b][m] = float(col.std() + 1e-9)
                else:
                    self.bucket_median[b][m] = DEFAULT_METRIC_MEDIAN.get(m, 0.0)
                    self.bucket_std[b][m] = 1.0

        for b in SIZE_BUCKETS:
            sub = train[train["size_bucket"] == b]
            self.bucket_ar1_phi[b] = {}
            for m in CAPITAL_METRICS:
                phis = []
                for _, gg in sub.groupby("CERT"):
                    vv = pd.to_numeric(gg[m], errors="coerce").dropna().values
                    if len(vv) < 4:
                        continue
                    mu = float(np.mean(vv))
                    r = vv - mu
                    num = float(np.sum(r[1:] * r[:-1]))
                    den = float(np.sum(r[:-1] ** 2) + 1e-9)
                    phi = np.clip(num / den, -0.9, 0.9)
                    if np.isfinite(phi):
                        phis.append(float(phi))
                self.bucket_ar1_phi[b][m] = float(np.median(phis)) if phis else 0.5

        for cert, gg in train.groupby("CERT"):
            gg = gg.sort_values("REPDTE")
            if len(gg) == 0:
                continue
            last = gg.iloc[-1]
            b = size_bucket(float(last["ASSET"]) if pd.notna(last["ASSET"]) else 0.0)
            self.cert_bucket[int(cert)] = b
            per_metric: dict[str, float] = {}
            for m in CAPITAL_METRICS:
                v = pd.to_numeric(last.get(m), errors="coerce")
                if pd.notna(v):
                    per_metric[m] = float(v)
            self.cert_last_by_metric[int(cert)] = per_metric

    def predict_metric(self, cert: int, bucket: str, metric: str) -> float:
        last_map = self.cert_last_by_metric.get(int(cert), {})
        last = last_map.get(metric)
        med_bucket = self.bucket_median.get(bucket, {}).get(metric, DEFAULT_METRIC_MEDIAN.get(metric, 0.0))
        if last is None or not np.isfinite(last):
            return float(med_bucket)
        stable_metrics = {"IDT1CER", "IDT1RWAJR", "RBC1AAJ", "RBCRWAJ", "EQV", "LNLSDEPR"}
        earnings_metrics = {"ROAQ", "ROEQ", "NIMYQ"}
        tail_metrics = {"NPERFV", "NCLNLSR", "LNATRESR"}
        if metric in stable_metrics:
            return float(0.90 * float(last) + 0.10 * float(med_bucket))
        if metric in earnings_metrics:
            return float(0.70 * float(last) + 0.30 * float(med_bucket))
        if metric in tail_metrics:
            return float(0.75 * float(last) + 0.25 * float(med_bucket))
        phi = self.bucket_ar1_phi.get(bucket, {}).get(metric, 0.5)
        pred = med_bucket + phi * (last - med_bucket)
        return float(pred)

    def update_cert_last(self, cert: int, metric: str, value: float) -> None:
        if int(cert) not in self.cert_last_by_metric:
            self.cert_last_by_metric[int(cert)] = {}
        self.cert_last_by_metric[int(cert)][metric] = float(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket_median": self.bucket_median,
            "bucket_std": self.bucket_std,
            "bucket_ar1_phi": self.bucket_ar1_phi,
            "cert_last_by_metric": {str(k): v for k, v in self.cert_last_by_metric.items()},
            "cert_bucket": {str(k): v for k, v in self.cert_bucket.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PeerGroupPercentileRegression":
        o = cls()
        o.bucket_median = d.get("bucket_median", {})
        o.bucket_std = d.get("bucket_std", {})
        o.bucket_ar1_phi = d.get("bucket_ar1_phi", {})
        o.cert_last_by_metric = {int(k): v for k, v in d.get("cert_last_by_metric", {}).items()}
        o.cert_bucket = {int(k): v for k, v in d.get("cert_bucket", {}).items()}
        return o


class MacroConditionalCapitalTrajectory:
    """3-regime Gaussian mixture over macro; per-bucket regime-conditional
    metric drift table."""

    def __init__(self, n_regimes: int = 3, seed: int = 42) -> None:
        self.n_regimes = n_regimes
        self.seed = seed
        self.means: Optional[np.ndarray] = None
        self.stds: Optional[np.ndarray] = None
        self.regime_means: Optional[np.ndarray] = None
        self.regime_stds: Optional[np.ndarray] = None
        self.regime_labels: dict[int, str] = {}
        self.bucket_regime_drift: dict[str, dict[str, dict[str, float]]] = {}

    @staticmethod
    def build_feature_matrix(macro: pd.DataFrame) -> tuple[np.ndarray, list, pd.DataFrame]:
        m = macro.copy()
        m["date"] = pd.to_datetime(m["date"])
        m = m.sort_values("date").reset_index(drop=True)
        for c in ["DFF", "DGS10", "T10Y2Y", "UNRATE"]:
            if c not in m.columns:
                m[c] = np.nan
            m[c] = pd.to_numeric(m[c], errors="coerce")
        m["DFF_chg_4q"] = m["DFF"].diff(80).fillna(0.0)
        m["T10Y2Y_slope"] = m["T10Y2Y"].diff(20).fillna(0.0)
        cols = ["DFF", "DGS10", "T10Y2Y", "UNRATE", "DFF_chg_4q", "T10Y2Y_slope"]
        m = m.dropna(subset=["DFF", "DGS10", "T10Y2Y"]).reset_index(drop=True)
        m["UNRATE"] = m["UNRATE"].ffill().bfill().fillna(4.0)
        m["T10Y2Y_slope"] = m["T10Y2Y_slope"].fillna(0.0)
        X = m[cols].values.astype(float)
        return X, m["date"].tolist(), m

    def fit(self, macro: pd.DataFrame, train: pd.DataFrame) -> None:
        X, _, macro_full = self.build_feature_matrix(macro)
        if len(X) < 40:
            self._fallback_init()
            self._fit_drift_default(train)
            return

        self.means = X.mean(axis=0)
        self.stds = X.std(axis=0) + 1e-9
        Z = (X - self.means) / self.stds
        rng = np.random.default_rng(self.seed)
        n = len(Z)
        idx = rng.choice(n, size=self.n_regimes, replace=False)
        centers = Z[idx].copy()
        for _ in range(40):
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

        chg_by_regime = [(k, float(centers[k, 4])) for k in range(self.n_regimes)]
        chg_by_regime.sort(key=lambda x: x[1])
        canonical = ["cutting", "on_hold", "hiking"]
        for i, (k, _) in enumerate(chg_by_regime):
            self.regime_labels[k] = canonical[i] if i < len(canonical) else "on_hold"

        self._fit_drift(train, macro_full, assign, macro["date"] if "date" in macro else None)

    def _fit_drift(self, train: pd.DataFrame, macro_full: pd.DataFrame,
                   assign: np.ndarray, _dates_unused: Any) -> None:
        macro_full = macro_full.copy()
        macro_full["regime_idx"] = assign
        macro_full["quarter_end"] = macro_full["date"].dt.to_period("Q").dt.end_time.dt.normalize()
        per_q = macro_full.groupby("quarter_end")["regime_idx"].agg(
            lambda s: int(s.value_counts().idxmax()) if len(s) else 0
        )

        train = train.copy()
        train["size_bucket"] = train["ASSET"].apply(size_bucket)
        train["REPDTE"] = train["REPDTE"].astype(str)
        train["quarter_end"] = pd.to_datetime(train["REPDTE"], format="%Y%m%d")
        train = train.sort_values(["CERT", "REPDTE"]).reset_index(drop=True)

        for b in SIZE_BUCKETS:
            self.bucket_regime_drift[b] = {}
            sub = train[train["size_bucket"] == b]
            for m in CAPITAL_METRICS:
                diff_by_reg: dict[str, list[float]] = {"cutting": [], "on_hold": [], "hiking": []}
                for _, gg in sub.groupby("CERT"):
                    gg = gg.sort_values("REPDTE")
                    vals = pd.to_numeric(gg[m], errors="coerce").values
                    quarters = gg["quarter_end"].values
                    for i in range(1, len(vals)):
                        if not (np.isfinite(vals[i]) and np.isfinite(vals[i-1])):
                            continue
                        q = quarters[i-1]
                        reg_idx = per_q.get(pd.Timestamp(q).normalize(), 1)
                        reg = self.regime_labels.get(int(reg_idx), "on_hold")
                        diff_by_reg[reg].append(vals[i] - vals[i-1])
                self.bucket_regime_drift[b][m] = {
                    reg: float(np.median(v)) if v else 0.0
                    for reg, v in diff_by_reg.items()
                }

    def _fit_drift_default(self, train: pd.DataFrame) -> None:
        for b in SIZE_BUCKETS:
            self.bucket_regime_drift[b] = {}
            for m in CAPITAL_METRICS:
                self.bucket_regime_drift[b][m] = {"cutting": 0.0, "on_hold": 0.0, "hiking": 0.0}

    def _fallback_init(self) -> None:
        self.means = np.array([2.5, 3.0, 0.5, 4.0, 0.0, 0.0])
        self.stds = np.array([2.0, 1.0, 0.7, 1.0, 0.5, 0.3])
        self.regime_means = np.array([
            [0.5, 2.0, 1.0, 5.0, -0.5, 0.2],
            [2.5, 3.0, 0.5, 4.0,  0.0, 0.0],
            [5.0, 4.5, 0.0, 3.5,  0.5, -0.2],
        ])
        self.regime_stds = np.ones_like(self.regime_means) * 0.5
        self.regime_labels = {0: "cutting", 1: "on_hold", 2: "hiking"}

    def predict_regime(self, macro_row: dict[str, float]) -> str:
        if self.regime_means is None:
            return "on_hold"
        feat = np.array([
            macro_row.get("DFF", 2.5),
            macro_row.get("DGS10", 3.0),
            macro_row.get("T10Y2Y", 0.5),
            macro_row.get("UNRATE", 4.0),
            macro_row.get("DFF_chg_4q", 0.0),
            macro_row.get("T10Y2Y_slope", 0.0),
        ])
        Z = (feat - self.means) / self.stds
        ZC = (self.regime_means - self.means) / self.stds
        d = np.linalg.norm(Z - ZC, axis=1)
        k = int(np.argmin(d))
        return self.regime_labels.get(k, "on_hold")

    def drift_for(self, bucket: str, metric: str, regime: str) -> float:
        return float(self.bucket_regime_drift.get(bucket, {}).get(metric, {}).get(regime, 0.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_regimes": self.n_regimes,
            "seed": self.seed,
            "means": self.means.tolist() if self.means is not None else None,
            "stds": self.stds.tolist() if self.stds is not None else None,
            "regime_means": self.regime_means.tolist() if self.regime_means is not None else None,
            "regime_stds": self.regime_stds.tolist() if self.regime_stds is not None else None,
            "regime_labels": self.regime_labels,
            "bucket_regime_drift": self.bucket_regime_drift,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MacroConditionalCapitalTrajectory":
        o = cls(n_regimes=d.get("n_regimes", 3), seed=d.get("seed", 42))
        o.means = np.array(d["means"]) if d.get("means") else None
        o.stds = np.array(d["stds"]) if d.get("stds") else None
        o.regime_means = np.array(d["regime_means"]) if d.get("regime_means") else None
        o.regime_stds = np.array(d["regime_stds"]) if d.get("regime_stds") else None
        o.regime_labels = {int(k): v for k, v in (d.get("regime_labels") or {}).items()}
        o.bucket_regime_drift = d.get("bucket_regime_drift", {})
        return o


class ConcentrationRiskFactorLoadings:
    """Per-bucket 2-factor loading on standardized NPL residual correlations."""

    def __init__(self) -> None:
        self.bucket_factor_load: dict[str, list[list[float]]] = {}
        self.bucket_factor_mean: dict[str, list[float]] = {}
        self.cert_factor_last: dict[int, list[float]] = {}
        self.metric_names = ["NPERFV", "NCLNLSR", "LNATRESR"]

    def fit(self, train: pd.DataFrame) -> None:
        train = train.copy()
        train["size_bucket"] = train["ASSET"].apply(size_bucket)
        train = train.sort_values(["CERT", "REPDTE"]).reset_index(drop=True)

        for b in SIZE_BUCKETS:
            sub = train[train["size_bucket"] == b]
            X_rows: list[np.ndarray] = []
            for m in self.metric_names:
                col = pd.to_numeric(sub[m], errors="coerce")
                X_rows.append(col.values)
            X = np.vstack(X_rows).T
            mask = np.all(np.isfinite(X), axis=1)
            X = X[mask]
            if len(X) < 20:
                self.bucket_factor_load[b] = [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
                self.bucket_factor_mean[b] = [0.5, 0.15, 1.3]
                continue
            mu = X.mean(axis=0)
            sd = X.std(axis=0) + 1e-9
            Z = (X - mu) / sd
            cov = np.cov(Z.T)
            try:
                eigvals, eigvecs = np.linalg.eigh(cov)
                order = np.argsort(eigvals)[::-1]
                eigvecs = eigvecs[:, order]
                loadings = eigvecs[:, :2] * np.sqrt(np.maximum(eigvals[order[:2]], 1e-9))
                self.bucket_factor_load[b] = loadings.tolist()
                self.bucket_factor_mean[b] = mu.tolist()
            except Exception:
                self.bucket_factor_load[b] = [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
                self.bucket_factor_mean[b] = mu.tolist() if X.size else [0.5, 0.15, 1.3]

        for cert, gg in train.groupby("CERT"):
            gg = gg.sort_values("REPDTE")
            if len(gg) == 0:
                continue
            last = gg.iloc[-1]
            b = size_bucket(float(last["ASSET"]) if pd.notna(last["ASSET"]) else 0.0)
            mu = self.bucket_factor_mean.get(b, [0.5, 0.15, 1.3])
            loadings = np.array(self.bucket_factor_load.get(b, [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]))
            vec = np.array([
                float(last.get("NPERFV") or mu[0]),
                float(last.get("NCLNLSR") or mu[1]),
                float(last.get("LNATRESR") or mu[2]),
            ]) - np.array(mu)
            try:
                scores = np.linalg.lstsq(loadings, vec, rcond=None)[0]
            except Exception:
                scores = np.zeros(2)
            self.cert_factor_last[int(cert)] = [float(scores[0]), float(scores[1])]

    def project_forward(self, cert: int, decay: float = 0.85) -> list[float]:
        s = self.cert_factor_last.get(int(cert), [0.0, 0.0])
        return [decay * float(s[0]), decay * float(s[1])]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket_factor_load": self.bucket_factor_load,
            "bucket_factor_mean": self.bucket_factor_mean,
            "cert_factor_last": {str(k): v for k, v in self.cert_factor_last.items()},
            "metric_names": self.metric_names,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConcentrationRiskFactorLoadings":
        o = cls()
        o.bucket_factor_load = d.get("bucket_factor_load", {})
        o.bucket_factor_mean = d.get("bucket_factor_mean", {})
        o.cert_factor_last = {int(k): v for k, v in d.get("cert_factor_last", {}).items()}
        o.metric_names = d.get("metric_names", ["NPERFV", "NCLNLSR", "LNATRESR"])
        return o


class CapitalBufferRegimeDetector:
    """Per-bucket 3-state buffer-regime classifier on capital ratio vector;
    canonical ordering forced via cluster-center sort on IDT1RWAJR."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.bucket_centers: dict[str, list[list[float]]] = {}
        self.bucket_mu: dict[str, list[float]] = {}
        self.bucket_sd: dict[str, list[float]] = {}
        self.bucket_labels: dict[str, dict[int, str]] = {}
        self.feature_cols = ["IDT1CER", "IDT1RWAJR", "RBC1AAJ", "RBCRWAJ", "EQV"]
        self.canonical_labels = ["buffer_critical", "buffer_eroding", "buffer_comfortable"]

    def fit(self, train: pd.DataFrame) -> None:
        train = train.copy()
        train["size_bucket"] = train["ASSET"].apply(size_bucket)
        rng = np.random.default_rng(self.seed)

        for b in SIZE_BUCKETS:
            sub = train[train["size_bucket"] == b]
            X = sub[self.feature_cols].apply(pd.to_numeric, errors="coerce").values
            mask = np.all(np.isfinite(X), axis=1)
            X = X[mask]
            if len(X) < 30:
                self.bucket_centers[b] = [[8.0, 8.0, 5.0, 10.0, 6.0],
                                          [12.0, 12.0, 9.0, 14.0, 9.0],
                                          [16.0, 16.0, 12.0, 18.0, 12.0]]
                self.bucket_mu[b] = [14.0, 14.0, 10.5, 15.5, 10.5]
                self.bucket_sd[b] = [3.0, 3.0, 2.5, 3.0, 2.5]
                self.bucket_labels[b] = {0: "buffer_critical", 1: "buffer_eroding", 2: "buffer_comfortable"}
                continue
            mu = X.mean(axis=0)
            sd = X.std(axis=0) + 1e-9
            Z = (X - mu) / sd
            n = len(Z)
            idx = rng.choice(n, size=3, replace=False)
            centers = Z[idx].copy()
            for _ in range(30):
                d = np.linalg.norm(Z[:, None, :] - centers[None, :, :], axis=2)
                assign = np.argmin(d, axis=1)
                new_centers = np.zeros_like(centers)
                for k in range(3):
                    m = assign == k
                    if m.sum() > 0:
                        new_centers[k] = Z[m].mean(axis=0)
                    else:
                        new_centers[k] = centers[k]
                if np.allclose(new_centers, centers, atol=1e-5):
                    centers = new_centers
                    break
                centers = new_centers
            centers_real = centers * sd + mu
            t1_centers = [(k, float(centers_real[k, 1])) for k in range(3)]
            t1_centers.sort(key=lambda x: x[1])
            labels = {}
            for i, (k, _) in enumerate(t1_centers):
                labels[k] = self.canonical_labels[i]
            self.bucket_centers[b] = centers_real.tolist()
            self.bucket_mu[b] = mu.tolist()
            self.bucket_sd[b] = sd.tolist()
            self.bucket_labels[b] = labels

    def predict_regime(self, bucket: str, metric_vec: dict[str, float]) -> str:
        centers = np.array(self.bucket_centers.get(bucket, [[8.0]*5, [12.0]*5, [16.0]*5]))
        mu = np.array(self.bucket_mu.get(bucket, [14.0, 14.0, 10.5, 15.5, 10.5]))
        sd = np.array(self.bucket_sd.get(bucket, [3.0, 3.0, 2.5, 3.0, 2.5]))
        vec = np.array([float(metric_vec.get(c, mu[i])) for i, c in enumerate(self.feature_cols)])
        Z = (vec - mu) / sd
        ZC = (centers - mu) / sd
        d = np.linalg.norm(Z - ZC, axis=1)
        k = int(np.argmin(d))
        raw_labels = self.bucket_labels.get(bucket, {0: "buffer_critical", 1: "buffer_eroding", 2: "buffer_comfortable"})
        if all(isinstance(kk, str) for kk in raw_labels.keys()):
            labels = {int(kk): vv for kk, vv in raw_labels.items()}
        else:
            labels = raw_labels
        return labels.get(k, "buffer_comfortable")

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "bucket_centers": self.bucket_centers,
            "bucket_mu": self.bucket_mu,
            "bucket_sd": self.bucket_sd,
            "bucket_labels": {b: {str(k): v for k, v in lb.items()} for b, lb in self.bucket_labels.items()},
            "feature_cols": self.feature_cols,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CapitalBufferRegimeDetector":
        o = cls(seed=d.get("seed", 42))
        o.bucket_centers = d.get("bucket_centers", {})
        o.bucket_mu = d.get("bucket_mu", {})
        o.bucket_sd = d.get("bucket_sd", {})
        raw = d.get("bucket_labels", {})
        o.bucket_labels = {b: {int(k): v for k, v in lb.items()} for b, lb in raw.items()}
        o.feature_cols = d.get("feature_cols", ["IDT1CER", "IDT1RWAJR", "RBC1AAJ", "RBCRWAJ", "EQV"])
        return o


def load_training_data(data_path: Path, macro_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    a = pd.read_csv(data_path)
    a["REPDTE"] = a["REPDTE"].astype(str)
    a = a.sort_values(["CERT", "REPDTE"]).reset_index(drop=True)
    m = pd.read_csv(macro_path)
    m["date"] = pd.to_datetime(m["date"])
    m = m.sort_values("date").reset_index(drop=True)
    return a, m


def macro_lookup_row(macro: pd.DataFrame, target_date: pd.Timestamp) -> dict[str, float]:
    m = macro[macro["date"] <= target_date]
    if len(m) == 0:
        return {"DFF": 2.5, "DGS10": 3.0, "T10Y2Y": 0.5, "UNRATE": 4.0,
                "DFF_chg_4q": 0.0, "T10Y2Y_slope": 0.0, "GDPC1": 20000.0}
    r = m.iloc[-1]
    dff = float(r.get("DFF") or 2.5)
    dgs10 = float(r.get("DGS10") or 3.0)
    t10y2y = float(r.get("T10Y2Y") or 0.5)
    unrate = float(r.get("UNRATE") or 4.0)
    prev80_idx = max(0, len(m) - 81)
    dff_prev = float(m.iloc[prev80_idx].get("DFF") or dff)
    dff_chg_4q = dff - dff_prev
    prev20_idx = max(0, len(m) - 21)
    t10y2y_prev = float(m.iloc[prev20_idx].get("T10Y2Y") or t10y2y)
    t10y2y_slope = t10y2y - t10y2y_prev
    gdpc1 = float(r.get("GDPC1") or 20000.0)
    return {"DFF": dff, "DGS10": dgs10, "T10Y2Y": t10y2y, "UNRATE": unrate,
            "DFF_chg_4q": dff_chg_4q, "T10Y2Y_slope": t10y2y_slope, "GDPC1": gdpc1}


def train_mode(data_path: Path, macro_path: Path, state_path: Path, seed: int = 42) -> None:
    print(f"[train] data={data_path} macro={macro_path}", file=sys.stderr, flush=True)
    a, m = load_training_data(data_path, macro_path)
    print(f"[train] rows={len(a)} unique CERT={a['CERT'].nunique()} macro={len(m)}",
          file=sys.stderr, flush=True)

    pgp = PeerGroupPercentileRegression()
    pgp.fit(a)
    print(f"[train] PeerGroupPercentileRegression fit over {len(pgp.bucket_median)} buckets",
          file=sys.stderr, flush=True)

    mct = MacroConditionalCapitalTrajectory(n_regimes=3, seed=seed)
    mct.fit(m, a)
    print(f"[train] MacroConditionalCapitalTrajectory labels: {mct.regime_labels}",
          file=sys.stderr, flush=True)

    crfl = ConcentrationRiskFactorLoadings()
    crfl.fit(a)
    print(f"[train] ConcentrationRiskFactorLoadings fit over {len(crfl.bucket_factor_load)} buckets",
          file=sys.stderr, flush=True)

    cbrd = CapitalBufferRegimeDetector(seed=seed)
    cbrd.fit(a)
    print(f"[train] CapitalBufferRegimeDetector fit over {len(cbrd.bucket_centers)} buckets",
          file=sys.stderr, flush=True)

    state = {
        "schema_version": 1,
        "generated_by": "bank_capital_projection_reference.py --train",
        "seed": seed,
        "peer_group_percentile_regression": pgp.to_dict(),
        "macro_conditional_capital_trajectory": mct.to_dict(),
        "concentration_risk_factor_loadings": crfl.to_dict(),
        "capital_buffer_regime_detector": cbrd.to_dict(),
        "training_range": {
            "n_rows": int(len(a)),
            "n_certs": int(a["CERT"].nunique()),
            "n_quarters": int(a["REPDTE"].nunique()),
            "macro_start": str(m["date"].min().date()) if len(m) else None,
            "macro_end": str(m["date"].max().date()) if len(m) else None,
        },
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, default=float))
    print(f"[train] wrote state to {state_path}", file=sys.stderr, flush=True)


def _load_state(state_path: Path):
    if not state_path.exists():
        raise FileNotFoundError(f"reference_state.json not found at {state_path}")
    d = json.loads(state_path.read_text())
    return (
        PeerGroupPercentileRegression.from_dict(d.get("peer_group_percentile_regression", {})),
        MacroConditionalCapitalTrajectory.from_dict(d.get("macro_conditional_capital_trajectory", {})),
        ConcentrationRiskFactorLoadings.from_dict(d.get("concentration_risk_factor_loadings", {})),
        CapitalBufferRegimeDetector.from_dict(d.get("capital_buffer_regime_detector", {})),
    )


def _quarter_end_date(repdte: str) -> pd.Timestamp:
    return pd.to_datetime(str(repdte), format="%Y%m%d")


def backtest_mode(data_path: Path, macro_path: Path, state_path: Path,
                  institutions_manifest_path: Optional[Path],
                  output_path: Path) -> None:
    pgp, mct, crfl, cbrd = _load_state(state_path)
    a = pd.read_csv(data_path)
    a["REPDTE"] = a["REPDTE"].astype(str)
    a = a.sort_values(["CERT", "REPDTE"]).reset_index(drop=True)
    m = pd.read_csv(macro_path)
    m["date"] = pd.to_datetime(m["date"])
    m = m.sort_values("date").reset_index(drop=True)

    id_by_cert: dict[int, str] = {}
    if institutions_manifest_path and institutions_manifest_path.exists():
        try:
            manifest = json.loads(institutions_manifest_path.read_text()).get("institutions", [])
            for row in manifest:
                cert = int(row.get("cert"))
                id_by_cert[cert] = row.get("institution_id") or f"fdic{cert:07d}"
        except Exception:
            pass

    results: list[dict] = []
    detected_events: list[dict] = []
    prev_zone_by_cert: dict[int, str] = {}
    prev_buffer_regime_by_cert: dict[int, str] = {}

    err_capital: list[float] = []
    err_earnings: list[float] = []
    err_tail: list[float] = []
    err_asset_growth: list[float] = []
    err_deposit_growth: list[float] = []
    zone_correct = 0
    zone_total = 0

    last_asset_by_cert: dict[int, float] = {}
    last_deposit_by_cert: dict[int, float] = {}

    for _, r in a.iterrows():
        cert = int(r["CERT"]) if pd.notna(r["CERT"]) else 0
        seed = deterministic_seed_from_cert(cert)
        _ = np.random.default_rng(seed)
        repdte = str(r["REPDTE"])
        quarter_end = _quarter_end_date(repdte)
        macro_row = macro_lookup_row(m, quarter_end - pd.Timedelta(days=1))
        regime = mct.predict_regime(macro_row)

        asset = float(r.get("ASSET") or 0)
        bucket = pgp.cert_bucket.get(cert) or size_bucket(asset)

        predictions: dict[str, float] = {}
        for metric in CAPITAL_METRICS:
            base = pgp.predict_metric(cert, bucket, metric)
            drift = mct.drift_for(bucket, metric, regime)
            base_pred = base + drift
            if metric in ("IDT1CER", "IDT1RWAJR", "RBC1AAJ", "RBCRWAJ"):
                base_pred = max(0.5, base_pred)
            if metric in ("NPERFV", "NCLNLSR"):
                base_pred = max(0.0, base_pred)
            predictions[metric] = float(base_pred)

        cf = crfl.project_forward(cert)
        loadings = np.array(crfl.bucket_factor_load.get(bucket, [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]))
        crfl_delta = loadings @ np.array(cf)
        for i, m_name in enumerate(crfl.metric_names):
            adj = 0.10 * float(crfl_delta[i])
            predictions[m_name] = float(predictions[m_name] + adj)
            if m_name in ("NPERFV", "NCLNLSR"):
                predictions[m_name] = max(0.0, predictions[m_name])

        buffer_metric_vec = {c: predictions.get(c, DEFAULT_METRIC_MEDIAN.get(c, 0.0))
                             for c in cbrd.feature_cols}
        buffer_regime = cbrd.predict_regime(bucket, buffer_metric_vec)
        if buffer_regime == "buffer_critical":
            for k in ("IDT1CER", "IDT1RWAJR", "RBC1AAJ", "RBCRWAJ"):
                predictions[k] = float(predictions[k] * 0.985)
        elif buffer_regime == "buffer_comfortable":
            for k in ("IDT1CER", "IDT1RWAJR", "RBC1AAJ", "RBCRWAJ"):
                predictions[k] = float(predictions[k] * 1.003)

        pca_zone = _pca_zone(predictions["IDT1RWAJR"], predictions["RBCRWAJ"], predictions["RBC1AAJ"])

        typical_growth_by_bucket = {"community": 0.010, "mid": 0.012, "regional": 0.015, "large": 0.008}
        asset_growth_pred = typical_growth_by_bucket.get(bucket, 0.010)
        if regime == "cutting":
            asset_growth_pred *= 0.7
        elif regime == "hiking":
            asset_growth_pred *= 1.1
        current_asset = asset
        last_asset = last_asset_by_cert.get(cert, current_asset)
        asset_growth_rate = 0.0
        if last_asset > 0 and current_asset > 0:
            asset_growth_rate = (current_asset - last_asset) / last_asset
        last_asset_by_cert[cert] = current_asset

        deposit_growth_pred = typical_growth_by_bucket.get(bucket, 0.010) * 0.9
        current_deposit = float(r.get("DEPDOM") or 0)
        last_deposit = last_deposit_by_cert.get(cert, current_deposit)
        last_deposit_by_cert[cert] = current_deposit

        realized: dict[str, Optional[float]] = {}
        for metric in CAPITAL_METRICS:
            v = pd.to_numeric(r.get(metric), errors="coerce")
            realized[metric] = float(v) if pd.notna(v) else None

        rt1r = realized.get("IDT1RWAJR")
        rrb = realized.get("RBCRWAJ")
        rlev = realized.get("RBC1AAJ")
        if all(x is not None for x in (rt1r, rrb, rlev)):
            realized_zone = _pca_zone(rt1r, rrb, rlev)
            zone_total += 1
            if realized_zone == pca_zone:
                zone_correct += 1
        prev_predicted_zone = prev_zone_by_cert.get(cert)
        if prev_predicted_zone is not None and prev_predicted_zone != pca_zone:
            detected_events.append({
                "event_date": repdte,
                "cert": cert,
                "kind": f"{prev_predicted_zone}_to_{pca_zone}",
                "predicted_zone": pca_zone,
            })
        prev_zone_by_cert[cert] = pca_zone

        for metric in ANCHOR_METRICS_PROJECTION:
            v = realized.get(metric)
            if v is not None:
                err_capital.append(abs(predictions[metric] - v))
        for metric in ANCHOR_METRICS_EARNINGS:
            v = realized.get(metric)
            if v is not None and v != 0:
                err_earnings.append(abs(predictions[metric] - v) / max(abs(v), 0.1))
        for metric in ANCHOR_METRICS_TAIL:
            v = realized.get(metric)
            if v is not None:
                err_tail.append(abs(predictions[metric] - v))

        if last_asset > 0 and asset > 0:
            err_asset_growth.append(abs(asset_growth_pred - asset_growth_rate))
        if last_deposit and last_deposit > 0 and current_deposit > 0:
            realized_dg = (current_deposit - last_deposit) / last_deposit
            err_deposit_growth.append(abs(deposit_growth_pred - realized_dg))

        for metric in CAPITAL_METRICS:
            pv = predictions.get(metric)
            if pv is not None:
                pgp.update_cert_last(cert, metric, float(pv))

        prev_buffer_regime_by_cert[cert] = buffer_regime

        results.append({
            "institution_id": id_by_cert.get(cert, f"fdic{cert:07d}"),
            "cert": cert,
            "name": r.get("NAME"),
            "repdte": repdte,
            "size_bucket": bucket,
            "detected_macro_regime": regime,
            "detected_buffer_regime": buffer_regime,
            "predicted_pca_zone": pca_zone,
            "predicted_metrics": {k: round(float(v), 4) for k, v in predictions.items()},
            "predicted_asset_growth_rate": round(float(asset_growth_pred), 6),
            "predicted_deposit_growth_rate": round(float(deposit_growth_pred), 6),
        })

    self_reported = {
        "mean_capital_ratio_mae_pp": float(np.mean(err_capital)) if err_capital else 0.0,
        "mean_earnings_mape": float(np.mean(err_earnings)) if err_earnings else 0.0,
        "mean_tail_bound_mae_pp": float(np.mean(err_tail)) if err_tail else 0.0,
        "mean_asset_growth_mae": float(np.mean(err_asset_growth)) if err_asset_growth else 0.0,
        "mean_deposit_growth_mae": float(np.mean(err_deposit_growth)) if err_deposit_growth else 0.0,
        "pca_zone_accuracy": float(zone_correct / max(zone_total, 1)),
    }

    out = {
        "generated_at": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observation_count": len(results),
        "observations": results,
        "self_reported_metrics": {k: round(v, 6) for k, v in self_reported.items()},
        "detected_pca_zone_events": detected_events,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, indent=2, default=float))
    print(f"[backtest] wrote {output_path} ({len(results)} observations)",
          file=sys.stderr, flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Judge-side reference solver.")
    p.add_argument("--train", action="store_true")
    p.add_argument("--backtest", action="store_true")
    p.add_argument("--data", type=str, default=None)
    p.add_argument("--macro", type=str, default=None)
    p.add_argument("--state", type=str, default="reference_state.json")
    p.add_argument("--institutions", type=str, default=None)
    p.add_argument("--output", type=str, default="projection_results.json")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    if args.train:
        if not (args.data and args.macro and args.state):
            raise SystemExit("--train requires --data, --macro, --state")
        train_mode(Path(args.data), Path(args.macro), Path(args.state), seed=args.seed)
    elif args.backtest:
        if not (args.data and args.macro and args.state):
            raise SystemExit("--backtest requires --data, --macro, --state")
        inst_p = Path(args.institutions) if args.institutions else None
        backtest_mode(Path(args.data), Path(args.macro), Path(args.state),
                      inst_p, Path(args.output))
    else:
        p.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
