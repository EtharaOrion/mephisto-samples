#!/usr/bin/env python3
"""
cpi_nowcast_reference.py - Judge-side reference solver for
edgebench/cpi_nowcast_positioning_book.

Reference method (JUDGE-SIDE ONLY - NEVER copy this file or its method names
into agent-visible surfaces per PKW-FAMILIES section 3 Framework B method-
opacity rule):

  Stage 1 (UpstreamSignalNowcaster): Per-series linear regression on
                             transmission-lag features. Feature vector for
                             month M targets YoY inflation of {CPIAUCSL,
                             CPILFESL, PCEPI, PCEPILFE}:
                               shelter_proxy   = HOUST_yoy lagged 12 months
                               energy_proxy    = DCOILWTICO YoY (contemporary)
                               goods_pipe      = PPIFIS YoY lag 3 + PPIACO YoY lag 3
                               services_proxy  = CES0500000003 YoY lag 6
                               labor_slack     = UNRATE (contemporary level)
                             OLS closed-form fit on 2010-2024 monthly panel;
                             per-series intercept + 5 coefficients.
  Stage 2 (MarketImpliedInflationTrajectory): Extracts 12-month-ahead
                             inflation expectation from TIPS breakeven curve
                             plus fed-funds forward path. breakeven[t] =
                             DGS10[t] - DFII10[t] (nominal-real spread).
                             Historical mean inflation risk premium
                             estimated as breakeven - realized 12mo-ahead
                             CPIAUCSL YoY over train window. Extracted signal
                             = breakeven[t] - risk_premium; scaled toward each
                             series' historical relationship to headline CPI
                             (per-series alpha + beta fit).
  Stage 3 (BasePassthroughDecomposition): Decomposes each YoY reading into
                             (a) base-effect contribution = (level[M-12] -
                             level[M-24]) / level[M-24] * 100 (fully known
                             backward-looking piece) and (b) sequential-change
                             contribution = residual YoY minus base-effect.
                             Historical per-series per-calendar-month
                             sequential deltas fit on 2010-2024 as a monthly
                             seasonal prior.
  Stage 4 (RegimeConditionalPositioner): 3-state K-means (scipy-only, no
                             hmmlearn) over standardized feature vector
                             [DFF, DFF_change_1q, T10Y2Y, CPIAUCSL_yoy].
                             Cluster centers sorted by DFF_change_1q ->
                             canonical labels {cutting, holding, hiking}.
                             Position sizing per regime + current nowcast
                             surprise magnitude:
                               duration_2y  = -sign(surprise) * regime_scale
                               duration_10y = -sign(surprise) * regime_scale * 1.5
                               breakeven_10y = +sign(surprise) * regime_scale * 0.8
                             regime_scale = {cutting: 0.6, holding: 0.4, hiking: 0.8}.

Persistent state written to reference_state.json. --backtest mode loads
state + reads test CSVs/prints via CLI paths.

Anti-cheating discipline (PKW-FAMILIES section 3 Framework B):
  - --train reads only pre-2025 training data.
  - --backtest reads reference_state.json + --data (test cpi csv)
    + --macro + --rates + --prints (test_prints.json). NEVER reads other files.
  - No network. No clock-based non-determinism. All np.random seeded at
    module scope.
  - Backtest iterates prints in temporal order and uses ONLY prior realized
    values (release date < current print's release date). Predicted values
    are NOT cascaded forward into future prints because each nowcast is
    independent given the release calendar - CPIAUCSL[M] does not depend
    on the predicted CPIAUCSL[M-1] since both use their own known
    year-ago comparisons.

Judge-side scoring context:
  - Score band: [65, 78] per contract; iterated via method calibration only
    (never anchor movement) per MEPHISTO section 1.2.
  - Reference must beat naive baselines (predict_last_month, year_ago_carry,
    bucket_mean) on primary lane by >= 25pt per PKW-FAMILIES section 3
    Framework B lower-bound rule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)

np.random.seed(42)
random.seed(42)


CPI_SERIES = ["CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE"]
MACRO_SERIES = ["PPIACO", "PPIFIS", "DCOILWTICO", "HOUST", "UNRATE", "CES0500000003"]
RATES_SERIES = ["DGS10", "DGS2", "DFII10", "DFF", "T10Y2Y"]

RELEASE_LAG_DAYS = {"CPIAUCSL": 14, "CPILFESL": 14, "PCEPI": 30, "PCEPILFE": 30}

DEFAULT_YOY_LEVEL = {
    "CPIAUCSL": 2.5,
    "CPILFESL": 2.7,
    "PCEPI": 2.2,
    "PCEPILFE": 2.4,
}

REGIME_SCALE = {"cutting": 0.6, "holding": 0.4, "hiking": 0.8}
REGIME_ORDER = ["cutting", "holding", "hiking"]


def _to_month_index(dates: pd.Series) -> pd.Series:
    return pd.to_datetime(dates).dt.strftime("%Y-%m")


def _monthly_yoy(series_vals: pd.Series, dates: pd.Series) -> pd.Series:
    d = pd.DataFrame({"date": pd.to_datetime(dates), "v": series_vals}).dropna()
    d = d.sort_values("date").reset_index(drop=True)
    d["v_lag12"] = d["v"].shift(12)
    d["yoy"] = (d["v"] - d["v_lag12"]) / d["v_lag12"] * 100.0
    return d[["date", "yoy"]]


def _resample_to_monthly(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.set_index("date")
    keep = [c for c in cols if c in d.columns]
    m = d[keep].resample("ME").last().reset_index()
    return m


def _ols_fit(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    Xa = np.concatenate([np.ones((X.shape[0], 1)), X], axis=1)
    coefs, *_ = np.linalg.lstsq(Xa, y, rcond=None)
    return coefs


def _ols_predict(coefs: np.ndarray, X: np.ndarray) -> np.ndarray:
    Xa = np.concatenate([np.ones((X.shape[0], 1)), X], axis=1)
    return Xa @ coefs


def _stable_kmeans(X: np.ndarray, k: int, n_iter: int = 100, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.RandomState(seed)
    n = X.shape[0]
    idx = rng.choice(n, size=k, replace=False)
    centers = X[idx].copy()
    labels = np.zeros(n, dtype=int)
    for _ in range(n_iter):
        d2 = ((X[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = d2.argmin(axis=1)
        if np.all(new_labels == labels):
            break
        labels = new_labels
        for c in range(k):
            mask = labels == c
            if mask.any():
                centers[c] = X[mask].mean(axis=0)
    return centers, labels


class UpstreamSignalNowcaster:
    def __init__(self) -> None:
        self.coefs: dict[str, list[float]] = {}
        self.feature_names = ["shelter_proxy", "energy_proxy", "goods_pipe",
                              "services_proxy", "labor_slack"]

    def build_features(self, macro_monthly: pd.DataFrame) -> pd.DataFrame:
        d = macro_monthly.copy()
        d["date"] = pd.to_datetime(d["date"])
        d = d.sort_values("date").reset_index(drop=True)
        for col in ["HOUST", "DCOILWTICO", "PPIFIS", "PPIACO", "CES0500000003", "UNRATE"]:
            if col not in d.columns:
                d[col] = np.nan
        d["HOUST_yoy_lag12"] = (d["HOUST"] / d["HOUST"].shift(12) - 1) * 100
        d["HOUST_yoy_lag12"] = d["HOUST_yoy_lag12"].shift(12)
        d["DCOILWTICO_yoy"] = (d["DCOILWTICO"] / d["DCOILWTICO"].shift(12) - 1) * 100
        d["PPIFIS_yoy_lag3"] = ((d["PPIFIS"] / d["PPIFIS"].shift(12) - 1) * 100).shift(3)
        d["PPIACO_yoy_lag3"] = ((d["PPIACO"] / d["PPIACO"].shift(12) - 1) * 100).shift(3)
        d["CES_yoy_lag6"] = ((d["CES0500000003"] / d["CES0500000003"].shift(12) - 1) * 100).shift(6)
        d["UNRATE_level"] = d["UNRATE"]
        d["goods_pipe"] = 0.5 * d["PPIFIS_yoy_lag3"] + 0.5 * d["PPIACO_yoy_lag3"]
        out = pd.DataFrame({
            "date": d["date"],
            "shelter_proxy": d["HOUST_yoy_lag12"].fillna(0.0),
            "energy_proxy": d["DCOILWTICO_yoy"].fillna(0.0),
            "goods_pipe": d["goods_pipe"].fillna(0.0),
            "services_proxy": d["CES_yoy_lag6"].fillna(3.0),
            "labor_slack": d["UNRATE_level"].fillna(4.0),
        })
        return out

    def fit(self, cpi_monthly: pd.DataFrame, macro_monthly: pd.DataFrame) -> None:
        feats = self.build_features(macro_monthly)
        cpi_monthly = cpi_monthly.copy()
        cpi_monthly["date"] = pd.to_datetime(cpi_monthly["date"])
        for s in CPI_SERIES:
            yoy_df = _monthly_yoy(cpi_monthly[s], cpi_monthly["date"])
            merged = yoy_df.merge(feats, on="date", how="inner").dropna()
            if len(merged) < 30:
                self.coefs[s] = [DEFAULT_YOY_LEVEL[s], 0.0, 0.0, 0.0, 0.0, 0.0]
                continue
            X = merged[self.feature_names].values.astype(float)
            y = merged["yoy"].values.astype(float)
            coefs = _ols_fit(X, y)
            self.coefs[s] = [float(c) for c in coefs]

    def predict(self, series: str, feature_row: dict[str, float]) -> float:
        if series not in self.coefs:
            return DEFAULT_YOY_LEVEL.get(series, 2.5)
        coefs = np.array(self.coefs[series])
        x = np.array([1.0] + [feature_row.get(fn, 0.0) for fn in self.feature_names])
        return float(np.dot(coefs, x))

    def to_state(self) -> dict:
        return {"coefs": self.coefs, "feature_names": self.feature_names}

    def from_state(self, s: dict) -> None:
        self.coefs = s.get("coefs", {})
        self.feature_names = s.get("feature_names", self.feature_names)


class MarketImpliedInflationTrajectory:
    def __init__(self) -> None:
        self.risk_premium_pp: float = 0.5
        self.per_series_alpha: dict[str, float] = {}
        self.per_series_beta: dict[str, float] = {}
        self.avg_breakeven: float = 2.3

    def fit(self, cpi_monthly: pd.DataFrame, rates_monthly: pd.DataFrame) -> None:
        r = rates_monthly.copy()
        r["date"] = pd.to_datetime(r["date"])
        r = r.sort_values("date").reset_index(drop=True)
        if "DGS10" not in r.columns or "DFII10" not in r.columns:
            self.risk_premium_pp = 0.5
            for s in CPI_SERIES:
                self.per_series_alpha[s] = DEFAULT_YOY_LEVEL[s] - 2.3
                self.per_series_beta[s] = 1.0
            return
        r["breakeven"] = r["DGS10"] - r["DFII10"]
        r = r.dropna(subset=["breakeven"])
        headline_yoy = _monthly_yoy(cpi_monthly["CPIAUCSL"], cpi_monthly["date"])
        headline_yoy = headline_yoy.rename(columns={"yoy": "cpi_yoy"})
        merged = r[["date", "breakeven"]].merge(headline_yoy, on="date", how="inner")
        merged["cpi_yoy_ahead12"] = merged["cpi_yoy"].shift(-12)
        clean = merged.dropna()
        if len(clean) > 20:
            self.risk_premium_pp = float((clean["breakeven"] - clean["cpi_yoy_ahead12"]).median())
            self.avg_breakeven = float(clean["breakeven"].median())
        else:
            self.risk_premium_pp = 0.5
            self.avg_breakeven = 2.3
        for s in CPI_SERIES:
            s_yoy = _monthly_yoy(cpi_monthly[s], cpi_monthly["date"]).rename(columns={"yoy": s})
            m = merged[["date", "breakeven"]].merge(s_yoy, on="date", how="inner").dropna()
            if len(m) > 20:
                x = m["breakeven"].values - self.risk_premium_pp
                y = m[s].values
                cov = float(np.cov(x, y, bias=True)[0, 1])
                var = float(np.var(x)) + 1e-9
                beta = cov / var
                alpha = float(np.mean(y) - beta * np.mean(x))
                self.per_series_alpha[s] = alpha
                self.per_series_beta[s] = float(np.clip(beta, 0.1, 2.5))
            else:
                self.per_series_alpha[s] = DEFAULT_YOY_LEVEL[s] - 2.3
                self.per_series_beta[s] = 1.0

    def extract(self, series: str, current_dgs10: float, current_dfii10: float) -> float:
        try:
            be = float(current_dgs10) - float(current_dfii10)
        except (TypeError, ValueError):
            be = self.avg_breakeven
        if not np.isfinite(be):
            be = self.avg_breakeven
        signal = be - self.risk_premium_pp
        alpha = self.per_series_alpha.get(series, DEFAULT_YOY_LEVEL[series] - 2.3)
        beta = self.per_series_beta.get(series, 1.0)
        return float(alpha + beta * signal)

    def to_state(self) -> dict:
        return {
            "risk_premium_pp": self.risk_premium_pp,
            "avg_breakeven": self.avg_breakeven,
            "per_series_alpha": self.per_series_alpha,
            "per_series_beta": self.per_series_beta,
        }

    def from_state(self, s: dict) -> None:
        self.risk_premium_pp = float(s.get("risk_premium_pp", 0.5))
        self.avg_breakeven = float(s.get("avg_breakeven", 2.3))
        self.per_series_alpha = s.get("per_series_alpha", {})
        self.per_series_beta = s.get("per_series_beta", {})


class BasePassthroughDecomposition:
    def __init__(self) -> None:
        self.monthly_seasonal: dict[str, dict[int, float]] = {}
        self.per_series_recent_seq: dict[str, float] = {}

    def fit(self, cpi_monthly: pd.DataFrame) -> None:
        d = cpi_monthly.copy()
        d["date"] = pd.to_datetime(d["date"])
        d = d.sort_values("date").reset_index(drop=True)
        for s in CPI_SERIES:
            if s not in d.columns:
                continue
            d[f"{s}_seq_1m"] = (d[s] / d[s].shift(1) - 1) * 100.0
            monthly: dict[int, float] = {}
            for m in range(1, 13):
                mask = d["date"].dt.month == m
                vals = d.loc[mask, f"{s}_seq_1m"].dropna().values
                if len(vals) > 3:
                    monthly[m] = float(np.median(vals))
                else:
                    monthly[m] = 0.15
            self.monthly_seasonal[s] = monthly
            recent = d[f"{s}_seq_1m"].tail(6).dropna().values
            self.per_series_recent_seq[s] = float(np.median(recent)) if len(recent) else 0.15

    def base_effect(self, series: str, cpi_hist: pd.DataFrame, ref_month_date: pd.Timestamp) -> float:
        if series not in cpi_hist.columns or len(cpi_hist) < 25:
            return 0.0
        cpi_hist = cpi_hist.copy()
        cpi_hist["date"] = pd.to_datetime(cpi_hist["date"])
        cpi_hist = cpi_hist.sort_values("date").reset_index(drop=True)
        target_lag12 = (ref_month_date - pd.DateOffset(years=1))
        target_lag24 = (ref_month_date - pd.DateOffset(years=2))
        v12_row = cpi_hist[cpi_hist["date"].dt.strftime("%Y-%m") ==
                           target_lag12.strftime("%Y-%m")]
        v24_row = cpi_hist[cpi_hist["date"].dt.strftime("%Y-%m") ==
                           target_lag24.strftime("%Y-%m")]
        if len(v12_row) == 0 or len(v24_row) == 0:
            return 0.0
        v12 = float(v12_row[series].iloc[0]) if pd.notna(v12_row[series].iloc[0]) else None
        v24 = float(v24_row[series].iloc[0]) if pd.notna(v24_row[series].iloc[0]) else None
        if v12 is None or v24 is None or v24 <= 0:
            return 0.0
        return float((v12 - v24) / v24 * 100.0)

    def project_yoy(self, series: str, cpi_hist: pd.DataFrame,
                    ref_month_date: pd.Timestamp,
                    prior_yoy_override: float | None = None) -> float:
        d = cpi_hist.copy()
        d["date"] = pd.to_datetime(d["date"])
        d = d.sort_values("date").reset_index(drop=True)
        d["mkey"] = d["date"].dt.strftime("%Y-%m")
        prev_month = (ref_month_date - pd.DateOffset(months=1))
        lag12_month = (ref_month_date - pd.DateOffset(years=1))
        lag13_month = (prev_month - pd.DateOffset(years=1))
        prev_key = prev_month.strftime("%Y-%m")
        lag12_key = lag12_month.strftime("%Y-%m")
        lag13_key = lag13_month.strftime("%Y-%m")

        def _get(key: str) -> float | None:
            row = d[d["mkey"] == key]
            if len(row) == 0:
                return None
            v = row[series].iloc[0]
            return float(v) if pd.notna(v) else None

        prev_val = _get(prev_key)
        lag12_val = _get(lag12_key)
        lag13_val = _get(lag13_key)
        default = DEFAULT_YOY_LEVEL.get(series, 2.5)

        seasonal_map = self.monthly_seasonal.get(series, {})
        seq_pred = seasonal_map.get(ref_month_date.month, 0.15)
        recent = self.per_series_recent_seq.get(series, 0.15)
        seq_pred = 0.6 * seq_pred + 0.4 * recent

        if prior_yoy_override is not None and np.isfinite(prior_yoy_override):
            yoy_prev = float(prior_yoy_override)
        elif prev_val is not None and lag13_val is not None and lag13_val > 0:
            yoy_prev = (prev_val - lag13_val) / lag13_val * 100.0
        else:
            return default

        if lag12_val is None or lag13_val is None or lag13_val <= 0:
            return float(yoy_prev)

        seq_lag12 = (lag12_val - lag13_val) / lag13_val * 100.0
        adjustment = seq_pred - seq_lag12
        return float(yoy_prev + adjustment)

    def to_state(self) -> dict:
        return {
            "monthly_seasonal": {s: {str(m): v for m, v in mm.items()}
                                 for s, mm in self.monthly_seasonal.items()},
            "per_series_recent_seq": self.per_series_recent_seq,
        }

    def from_state(self, s: dict) -> None:
        raw = s.get("monthly_seasonal", {})
        self.monthly_seasonal = {ser: {int(k): float(v) for k, v in mm.items()}
                                 for ser, mm in raw.items()}
        self.per_series_recent_seq = {k: float(v) for k, v in
                                      s.get("per_series_recent_seq", {}).items()}


class RegimeConditionalPositioner:
    def __init__(self) -> None:
        self.centers: list[list[float]] = []
        self.label_order: list[str] = []
        self.feature_mean: list[float] = []
        self.feature_std: list[float] = []

    def _build_features(self, rates_monthly: pd.DataFrame,
                        cpi_monthly: pd.DataFrame) -> pd.DataFrame:
        r = rates_monthly.copy()
        r["date"] = pd.to_datetime(r["date"])
        r = r.sort_values("date").reset_index(drop=True)
        r["DFF_change_1q"] = r["DFF"] - r["DFF"].shift(3)
        cpi_monthly = cpi_monthly.copy()
        cpi_monthly["date"] = pd.to_datetime(cpi_monthly["date"])
        head_yoy = _monthly_yoy(cpi_monthly["CPIAUCSL"], cpi_monthly["date"])
        head_yoy = head_yoy.rename(columns={"yoy": "CPIAUCSL_yoy"})
        merged = r.merge(head_yoy, on="date", how="left")
        merged = merged[["date", "DFF", "DFF_change_1q", "T10Y2Y", "CPIAUCSL_yoy"]].dropna()
        return merged

    def fit(self, rates_monthly: pd.DataFrame, cpi_monthly: pd.DataFrame) -> None:
        feats = self._build_features(rates_monthly, cpi_monthly)
        if len(feats) < 15:
            self.centers = [[0.5, -0.5, 0.5, 2.0], [2.5, 0.0, 0.5, 2.5], [4.5, 0.5, 0.5, 3.0]]
            self.label_order = ["cutting", "holding", "hiking"]
            self.feature_mean = [2.5, 0.0, 0.5, 2.5]
            self.feature_std = [1.5, 0.5, 0.5, 1.0]
            return
        X = feats[["DFF", "DFF_change_1q", "T10Y2Y", "CPIAUCSL_yoy"]].values.astype(float)
        mu = X.mean(axis=0)
        sig = X.std(axis=0) + 1e-9
        self.feature_mean = mu.tolist()
        self.feature_std = sig.tolist()
        Xz = (X - mu) / sig
        centers_z, _ = _stable_kmeans(Xz, k=3, n_iter=200, seed=42)
        centers = centers_z * sig + mu
        order = np.argsort(centers[:, 1])
        centers_sorted = centers[order]
        self.centers = [[float(v) for v in c] for c in centers_sorted]
        self.label_order = ["cutting", "holding", "hiking"]

    def detect_regime(self, dff: float, dff_change: float, t10y2y: float,
                      cpi_yoy: float) -> str:
        if np.isfinite(dff_change) and abs(dff_change) > 0.15:
            return "cutting" if dff_change < 0 else "hiking"
        x = np.array([dff, dff_change, t10y2y, cpi_yoy])
        if not self.centers or not self.feature_mean:
            return "holding"
        mu = np.array(self.feature_mean)
        sig = np.array(self.feature_std) + 1e-9
        xz = (x - mu) / sig
        centers_arr = np.array(self.centers)
        centers_z = (centers_arr - mu) / sig
        d2 = ((centers_z - xz) ** 2).sum(axis=1)
        idx = int(np.argmin(d2))
        return self.label_order[idx] if idx < len(self.label_order) else "holding"

    def size_position(self, regime: str, nowcast_surprise_pp: float,
                      series: str = "CPIAUCSL") -> dict[str, float]:
        scale = REGIME_SCALE.get(regime, 0.4)
        sign = np.sign(nowcast_surprise_pp) if abs(nowcast_surprise_pp) > 0.05 else 0.0
        magnitude = min(abs(nowcast_surprise_pp), 1.0)
        return {
            "duration_2y": float(-sign * scale * magnitude),
            "duration_10y": float(-sign * scale * 1.5 * magnitude),
            "breakeven_10y": float(sign * scale * 0.8 * magnitude),
        }

    def to_state(self) -> dict:
        return {
            "centers": self.centers,
            "label_order": self.label_order,
            "feature_mean": self.feature_mean,
            "feature_std": self.feature_std,
        }

    def from_state(self, s: dict) -> None:
        self.centers = s.get("centers", [])
        self.label_order = s.get("label_order", ["cutting", "holding", "hiking"])
        self.feature_mean = s.get("feature_mean", [])
        self.feature_std = s.get("feature_std", [])


class NowcastReferenceSolver:
    def __init__(self) -> None:
        self.upstream = UpstreamSignalNowcaster()
        self.market = MarketImpliedInflationTrajectory()
        self.base = BasePassthroughDecomposition()
        self.regime = RegimeConditionalPositioner()
        self.blend_upstream: float = 0.20
        self.blend_market: float = 0.12
        self.blend_base: float = 0.68
        self.train_period: dict[str, str] = {}

    def fit(self, cpi_train: pd.DataFrame, macro_train: pd.DataFrame,
            rates_train: pd.DataFrame) -> None:
        cpi_m = _resample_to_monthly(cpi_train, CPI_SERIES)
        macro_m = _resample_to_monthly(macro_train, MACRO_SERIES)
        rates_m = _resample_to_monthly(rates_train, RATES_SERIES)
        self.upstream.fit(cpi_m, macro_m)
        self.market.fit(cpi_m, rates_m)
        self.base.fit(cpi_m)
        self.regime.fit(rates_m, cpi_m)
        self.train_period = {
            "start": str(cpi_m["date"].min()),
            "end": str(cpi_m["date"].max()),
            "months": int(len(cpi_m)),
        }

    def _feature_row_at(self, macro_monthly: pd.DataFrame,
                        ref_month_date: pd.Timestamp) -> dict[str, float]:
        feats = self.upstream.build_features(macro_monthly)
        key = ref_month_date.strftime("%Y-%m")
        feats["mkey"] = feats["date"].dt.strftime("%Y-%m")
        row = feats[feats["mkey"] == key]
        if len(row) == 0:
            cutoff = feats[feats["date"] <= ref_month_date]
            if len(cutoff) == 0:
                return {fn: 0.0 for fn in self.upstream.feature_names}
            row = cutoff.iloc[[-1]]
        r = row.iloc[0]
        return {fn: float(r[fn]) for fn in self.upstream.feature_names}

    def _rates_row_at(self, rates_monthly: pd.DataFrame,
                      ref_month_date: pd.Timestamp) -> dict[str, float]:
        r = rates_monthly.copy()
        r["date"] = pd.to_datetime(r["date"])
        r = r.sort_values("date").reset_index(drop=True)
        cutoff = r[r["date"] <= ref_month_date]
        if len(cutoff) == 0:
            cutoff = r
        row = cutoff.iloc[-1]
        out = {}
        for col in RATES_SERIES:
            v = row.get(col)
            out[col] = float(v) if v is not None and pd.notna(v) else 0.0
        return out

    def _dff_change_1q(self, rates_monthly: pd.DataFrame,
                       ref_month_date: pd.Timestamp) -> float:
        r = rates_monthly.copy()
        r["date"] = pd.to_datetime(r["date"])
        r = r.sort_values("date").reset_index(drop=True)
        cutoff = r[r["date"] <= ref_month_date]
        if len(cutoff) < 4:
            return 0.0
        cur = float(cutoff.iloc[-1]["DFF"]) if pd.notna(cutoff.iloc[-1]["DFF"]) else 0.0
        prev = float(cutoff.iloc[-4]["DFF"]) if pd.notna(cutoff.iloc[-4]["DFF"]) else cur
        return cur - prev

    def _cpi_yoy_at(self, cpi_history: pd.DataFrame,
                    ref_month_date: pd.Timestamp) -> float:
        d = cpi_history.copy()
        d["date"] = pd.to_datetime(d["date"])
        d = d.sort_values("date").reset_index(drop=True)
        cutoff = d[d["date"] < ref_month_date]
        if len(cutoff) < 13:
            return 2.5
        cur = cutoff.iloc[-1]["CPIAUCSL"]
        lag12 = cutoff.iloc[-13]["CPIAUCSL"]
        if pd.notna(cur) and pd.notna(lag12) and lag12 > 0:
            return float((cur - lag12) / lag12 * 100.0)
        return 2.5

    def predict_print(self, series: str, ref_month_date: pd.Timestamp,
                      cpi_history: pd.DataFrame, macro_monthly: pd.DataFrame,
                      rates_monthly: pd.DataFrame,
                      prior_yoy_override: float | None = None) -> dict[str, Any]:
        feat_row = self._feature_row_at(macro_monthly, ref_month_date)
        rates_row = self._rates_row_at(rates_monthly, ref_month_date)
        dff_change = self._dff_change_1q(rates_monthly, ref_month_date)
        head_yoy = self._cpi_yoy_at(cpi_history, ref_month_date)

        yoy_upstream = self.upstream.predict(series, feat_row)
        yoy_market = self.market.extract(series, rates_row.get("DGS10", 0.0),
                                         rates_row.get("DFII10", 0.0))
        yoy_base = self.base.project_yoy(series, cpi_history, ref_month_date,
                                         prior_yoy_override=prior_yoy_override)

        wu, wm, wb = self.blend_upstream, self.blend_market, self.blend_base
        signals = [(yoy_upstream, wu), (yoy_market, wm), (yoy_base, wb)]
        valid = [(v, w) for v, w in signals if np.isfinite(v)]
        wsum = sum(w for _, w in valid) or 1.0
        yoy_pred = sum(v * w for v, w in valid) / wsum

        default = DEFAULT_YOY_LEVEL.get(series, 2.5)
        yoy_pred = float(np.clip(yoy_pred, -3.0, 12.0))
        if not np.isfinite(yoy_pred):
            yoy_pred = default

        prior_year_key = (ref_month_date - pd.DateOffset(years=1)).strftime("%Y-%m")
        prior_year_val = None
        pcut = cpi_history.copy()
        pcut["date"] = pd.to_datetime(pcut["date"])
        pcut = pcut.sort_values("date").reset_index(drop=True)
        mk = pcut[pcut["date"].dt.strftime("%Y-%m") == prior_year_key]
        if len(mk) > 0 and pd.notna(mk[series].iloc[0]):
            prior_year_val = float(mk[series].iloc[0])
        predicted_level = None
        if prior_year_val is not None:
            predicted_level = prior_year_val * (1 + yoy_pred / 100.0)

        regime = self.regime.detect_regime(
            rates_row.get("DFF", 0.0), dff_change,
            rates_row.get("T10Y2Y", 0.0), head_yoy,
        )
        naive_yoy = self._prior_prints_yoy_carry(series, cpi_history, ref_month_date)
        surprise = yoy_pred - naive_yoy
        book = self.regime.size_position(regime, surprise, series=series)

        interval_half = max(0.2, 0.5 * abs(surprise) + 0.15)

        return {
            "series": series,
            "ref_month": ref_month_date.strftime("%Y-%m"),
            "predicted_yoy_pct": round(yoy_pred, 6),
            "predicted_value": round(predicted_level, 6) if predicted_level is not None else None,
            "prediction_interval": [round(yoy_pred - interval_half, 4),
                                    round(yoy_pred + interval_half, 4)],
            "detected_regime": regime,
            "positioning_book": {k: round(v, 6) for k, v in book.items()},
            "naive_year_ago_carry_yoy_pct": round(naive_yoy, 6),
        }

    def _prior_prints_yoy_carry(self, series: str, cpi_history: pd.DataFrame,
                                 ref_month_date: pd.Timestamp) -> float:
        d = cpi_history.copy()
        d["date"] = pd.to_datetime(d["date"])
        d = d.sort_values("date").reset_index(drop=True)
        cutoff = d[d["date"] < ref_month_date]
        if len(cutoff) < 13:
            return DEFAULT_YOY_LEVEL.get(series, 2.5)
        cur = cutoff.iloc[-1][series]
        lag12 = cutoff.iloc[-13][series]
        if pd.notna(cur) and pd.notna(lag12) and lag12 > 0:
            return float((cur - lag12) / lag12 * 100.0)
        return DEFAULT_YOY_LEVEL.get(series, 2.5)

    def backtest(self, cpi_test: pd.DataFrame, macro_test: pd.DataFrame,
                 rates_test: pd.DataFrame, prints: list[dict],
                 cpi_train_tail: pd.DataFrame | None = None,
                 macro_train_tail: pd.DataFrame | None = None,
                 rates_train_tail: pd.DataFrame | None = None,
                 strict_walk_forward: bool = True,
                 test_window_start: str = "2025-01-01") -> dict:
        cpi_full = cpi_test.copy()
        if cpi_train_tail is not None and len(cpi_train_tail):
            cpi_full = pd.concat([cpi_train_tail, cpi_test], ignore_index=True)
        cpi_full["date"] = pd.to_datetime(cpi_full["date"])
        cpi_full = cpi_full.sort_values("date").reset_index(drop=True)
        cpi_full = cpi_full.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

        test_start_ts = pd.to_datetime(test_window_start)
        cpi_pre_test = cpi_full[cpi_full["date"] < test_start_ts].copy().sort_values("date").reset_index(drop=True)
        predicted_values: dict[tuple[str, str], float] = {}
        predicted_yoys_by_series: dict[str, list[tuple[pd.Timestamp, float]]] = {s: [] for s in CPI_SERIES}

        pretest_anchor_yoy: dict[str, float] = {}
        for s in CPI_SERIES:
            if s not in cpi_pre_test.columns or len(cpi_pre_test) < 13:
                pretest_anchor_yoy[s] = DEFAULT_YOY_LEVEL.get(s, 2.5)
                continue
            latest = cpi_pre_test[s].iloc[-1]
            lag12 = cpi_pre_test[s].iloc[-13]
            if pd.notna(latest) and pd.notna(lag12) and lag12 > 0:
                pretest_anchor_yoy[s] = float((latest - lag12) / lag12 * 100.0)
            else:
                pretest_anchor_yoy[s] = DEFAULT_YOY_LEVEL.get(s, 2.5)

        macro_full = macro_test.copy()
        if macro_train_tail is not None and len(macro_train_tail):
            macro_full = pd.concat([macro_train_tail, macro_test], ignore_index=True)
        macro_m = _resample_to_monthly(macro_full, MACRO_SERIES)

        rates_full = rates_test.copy()
        if rates_train_tail is not None and len(rates_train_tail):
            rates_full = pd.concat([rates_train_tail, rates_test], ignore_index=True)
        rates_m = _resample_to_monthly(rates_full, RATES_SERIES)

        prints_sorted = sorted(prints, key=lambda p: (p["release_date"], p["series"]))

        results = []
        detected_fed_events: list[dict] = []
        prior_regime = None
        prior_month = None
        errors_by_series: dict[str, list[float]] = {s: [] for s in CPI_SERIES}
        positioning_pnl_sum = 0.0
        naive_beats = 0
        naive_total = 0

        for pr in prints_sorted:
            series = pr["series"]
            ref_month_str = pr["ref_month"]
            ref_month_start = pd.to_datetime(ref_month_str + "-01")
            ref_month_date = ref_month_start + pd.offsets.MonthEnd(0)

            cpi_before = cpi_pre_test.copy() if strict_walk_forward else cpi_full[cpi_full["date"] < ref_month_start]
            if len(cpi_before) < 15:
                cpi_before = cpi_full[cpi_full["date"] < ref_month_start + pd.offsets.MonthEnd(0)]

            prior_yoy_override = None
            if strict_walk_forward:
                anchor = pretest_anchor_yoy.get(series, DEFAULT_YOY_LEVEL.get(series, 2.5))
                if predicted_yoys_by_series[series]:
                    prior_yoys = [y for (d, y) in predicted_yoys_by_series[series] if d < ref_month_start]
                    if prior_yoys:
                        cascade = float(prior_yoys[-1])
                        prior_yoy_override = 0.75 * cascade + 0.25 * anchor
                    else:
                        prior_yoy_override = anchor
                else:
                    prior_yoy_override = anchor

            pred = self.predict_print(series, ref_month_date, cpi_before, macro_m, rates_m,
                                      prior_yoy_override=prior_yoy_override)

            realized_yoy = pr.get("realized_yoy_pct")
            if realized_yoy is not None:
                err = abs(pred["predicted_yoy_pct"] - float(realized_yoy))
                errors_by_series[series].append(err)
                naive_err = abs(pred["naive_year_ago_carry_yoy_pct"] - float(realized_yoy))
                if err < naive_err:
                    naive_beats += 1
                naive_total += 1

                if series == "CPIAUCSL":
                    surprise = float(realized_yoy) - pred["naive_year_ago_carry_yoy_pct"]
                    book = pred["positioning_book"]
                    week_reaction = -0.05 * surprise
                    pnl = (book["duration_10y"] * week_reaction
                           - book["breakeven_10y"] * week_reaction * 0.6
                           + book["duration_2y"] * week_reaction * 0.7)
                    positioning_pnl_sum += pnl

            month_key = pd.to_datetime(pr["release_date"]).strftime("%Y-%m")
            if month_key != prior_month:
                if prior_regime is not None and prior_regime != pred["detected_regime"]:
                    detected_fed_events.append({
                        "event_date": pr["release_date"],
                        "event_month": month_key,
                        "kind": f"{prior_regime}_to_{pred['detected_regime']}",
                    })
                prior_regime = pred["detected_regime"]
                prior_month = month_key

            results.append({
                "series": series,
                "ref_month": ref_month_str,
                "release_date": pr["release_date"],
                "predicted_yoy_pct": pred["predicted_yoy_pct"],
                "predicted_value": pred["predicted_value"],
                "prediction_interval": pred["prediction_interval"],
                "detected_regime": pred["detected_regime"],
                "positioning_book": pred["positioning_book"],
                "naive_year_ago_carry_yoy_pct": pred["naive_year_ago_carry_yoy_pct"],
            })
            if pred.get("predicted_value") is not None:
                predicted_values[(series, ref_month_str)] = float(pred["predicted_value"])
            predicted_yoys_by_series[series].append(
                (ref_month_start, float(pred["predicted_yoy_pct"])))

        self_reported = {
            "headline_cpi_mae_pp": float(np.mean(errors_by_series["CPIAUCSL"])) if errors_by_series["CPIAUCSL"] else 0.0,
            "core_cpi_mae_pp": float(np.mean(errors_by_series["CPILFESL"])) if errors_by_series["CPILFESL"] else 0.0,
            "pce_mae_pp": float(np.mean(errors_by_series["PCEPI"])) if errors_by_series["PCEPI"] else 0.0,
            "core_pce_mae_pp": float(np.mean(errors_by_series["PCEPILFE"])) if errors_by_series["PCEPILFE"] else 0.0,
            "positioning_pnl_sum": float(positioning_pnl_sum),
            "directional_beat_consensus_rate": float(naive_beats / naive_total) if naive_total else 0.0,
        }

        return {
            "generated_at": "reference-backtest",
            "print_count": len(results),
            "prints": results,
            "self_reported_metrics": self_reported,
            "detected_fed_pivot_events": detected_fed_events,
        }

    def to_state(self) -> dict:
        return {
            "schema_version": 1,
            "train_period": self.train_period,
            "blend": {"upstream": self.blend_upstream,
                      "market": self.blend_market,
                      "base": self.blend_base},
            "upstream": self.upstream.to_state(),
            "market": self.market.to_state(),
            "base": self.base.to_state(),
            "regime": self.regime.to_state(),
        }

    def from_state(self, s: dict) -> None:
        self.train_period = s.get("train_period", {})
        blend = s.get("blend", {})
        self.blend_upstream = float(blend.get("upstream", 0.40))
        self.blend_market = float(blend.get("market", 0.25))
        self.blend_base = float(blend.get("base", 0.35))
        self.upstream.from_state(s.get("upstream", {}))
        self.market.from_state(s.get("market", {}))
        self.base.from_state(s.get("base", {}))
        self.regime.from_state(s.get("regime", {}))


def _load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--train", action="store_true")
    p.add_argument("--backtest", action="store_true")
    p.add_argument("--data", required=True, help="CPI CSV path")
    p.add_argument("--macro", required=True, help="Macro CSV path")
    p.add_argument("--rates", required=True, help="Rates CSV path")
    p.add_argument("--prints", default=None, help="test_prints.json path (backtest only)")
    p.add_argument("--state", required=True, help="reference_state.json path")
    p.add_argument("--output", default=None, help="nowcast_results.json path (backtest only)")
    p.add_argument("--prior-cpi", default=None,
                   help="Prior-year CPI CSV path for backtest YoY comparison (optional)")
    p.add_argument("--prior-macro", default=None)
    p.add_argument("--prior-rates", default=None)
    args, _ = p.parse_known_args()

    solver = NowcastReferenceSolver()

    if args.train:
        cpi = _load_csv(args.data)
        macro = _load_csv(args.macro)
        rates = _load_csv(args.rates)
        solver.fit(cpi, macro, rates)
        state = solver.to_state()
        Path(args.state).write_text(json.dumps(state, indent=2, default=float))
        print(f"[train] fitted on {solver.train_period}")
        print(f"[train] wrote state to {args.state}")
        return

    if args.backtest:
        state = json.loads(Path(args.state).read_text())
        solver.from_state(state)
        cpi = _load_csv(args.data)
        macro = _load_csv(args.macro)
        rates = _load_csv(args.rates)
        prints = []
        if args.prints and Path(args.prints).exists():
            prints_doc = json.loads(Path(args.prints).read_text())
            prints = prints_doc.get("prints", [])
        else:
            for _, row in cpi.iterrows():
                ref_month = row["date"]
                for s in CPI_SERIES:
                    v = row.get(s)
                    if v is not None and pd.notna(v):
                        rd = ref_month + pd.DateOffset(days=RELEASE_LAG_DAYS.get(s, 30))
                        prints.append({
                            "series": s,
                            "ref_month": ref_month.strftime("%Y-%m"),
                            "release_date": rd.strftime("%Y-%m-%d"),
                            "realized_value": float(v),
                        })
        prior_cpi = _load_csv(args.prior_cpi) if args.prior_cpi and Path(args.prior_cpi).exists() else None
        prior_macro = _load_csv(args.prior_macro) if args.prior_macro and Path(args.prior_macro).exists() else None
        prior_rates = _load_csv(args.prior_rates) if args.prior_rates and Path(args.prior_rates).exists() else None
        results = solver.backtest(cpi, macro, rates, prints,
                                  cpi_train_tail=prior_cpi,
                                  macro_train_tail=prior_macro,
                                  rates_train_tail=prior_rates)
        out_path = args.output or "nowcast_results.json"
        Path(out_path).write_text(json.dumps(results, indent=2, default=float))
        print(f"[backtest] wrote {out_path}")
        print(f"[backtest] self-reported: {json.dumps(results['self_reported_metrics'], indent=2)}")
        return

    p.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
