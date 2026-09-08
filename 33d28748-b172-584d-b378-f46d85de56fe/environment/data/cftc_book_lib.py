"""Scoring constants and helpers for cftc_futures_positioning_book.

PUBLIC ON PURPOSE. The agent receives this file byte-identical to the judge's
copy. Nothing here is secret. The only private information the judge holds is
the realized next-week commercial net position for every graded (market, week)
row, which is stripped from the agent-visible history file and lives only in
the judge container.

WHAT IS GRADED
--------------
For every graded (market_id, week_ending) pair in the hidden 2025-01-07 to
2026-07-22 window, the agent produces:

  commercial_net_direction   : "up" | "down"
  magnitude_bucket           : "large_increase" | "small_increase" |
                               "small_decrease" | "large_decrease"
  crowding_regime            : "crowded_long" | "neutral" |
                               "crowded_short" | "extreme"
  extreme_positioning_flag   : True | False
  direction_probability      : float in [0, 1]
  self_reported_certainty    : float in [0, 1]

Plus a self_reported_metrics block that the judge independently recomputes
from the raw per-market per-week predictions to detect fabrication (L7).

PERSISTENCE-DISEASE TRAP
------------------------
The commercial net position for any given market has weekly autocorrelation
above 0.90. Copying last week's direction earns approximately 0.527 on L1
direction accuracy. Because scoring is on REALIZED next-week direction rather
than on level-forecast accuracy, copy-yesterday cannot exploit persistence at
inflection points, but it is not trivially beaten either.

THE PAYOFF IS REALITY'S, NOT THE AUTHOR'S
------------------------------------------
There is no authored key. The ground truth is assembled at grade time from the
realized CFTC Commitments of Traders publication for the following week. Nobody
wrote down which direction commercial net will move; it cannot be looked up on
the agent-visible surface, memorised, or transcribed.
"""

# ---- market universe -------------------------------------------------------
# 25 CFTC-regulated futures contracts with continuous weekly coverage.
# Keys are 2-letter ticker IDs; values are CFTC contract_market_codes.
MARKETS = {
    "CL": "067651",   # WTI Crude Oil, NYMEX
    "NG": "023651",   # Natural Gas, NYMEX
    "RB": "111659",   # RBOB Gasoline, NYMEX
    "HO": "022651",   # Heating Oil (#2 ULSD), NYMEX
    "GC": "088691",   # Gold, COMEX
    "SI": "084691",   # Silver, COMEX
    "HG": "085692",   # Copper-Grade #1, COMEX
    "PL": "076651",   # Platinum, NYMEX
    "C":  "002602",   # Corn, CBOT
    "S":  "005602",   # Soybeans, CBOT
    "W":  "001602",   # Wheat-SRW, CBOT
    "KW": "001612",   # Wheat-HRW, CBOT
    "LC": "057642",   # Live Cattle, CME
    "LH": "054642",   # Lean Hogs, CME
    "ZB": "020601",   # US Treasury Bonds 30Y, CBOT
    "ZN": "043607",   # Ultra 10-Year US T-Notes, CBOT
    "ZF": "044601",   # 5-Year US T-Notes, CBOT
    "ZT": "042601",   # 2-Year US T-Notes, CBOT
    "EC": "099741",   # Euro FX, CME
    "JY": "097741",   # Japanese Yen, CME
    "BP": "096742",   # British Pound Sterling, CME
    "AD": "232741",   # Australian Dollar, CME
    "CD": "090741",   # Canadian Dollar, CME
    "ES": "13874A",   # E-Mini S&P 500, CME
    "NQ": "209742",   # NASDAQ-100 Mini, CME
}

MARKET_IDS = sorted(MARKETS.keys())
CODE_TO_MID = {v: k for k, v in MARKETS.items()}

# ---- window definition -----------------------------------------------------
BOUNDARY = "2024-12-31"       # last date in agent-visible training history
GRADED_START = "2025-01-07"   # first graded week_ending date
GRADED_END = "2026-07-22"     # last graded week_ending date

# ---- scoring constants -----------------------------------------------------
# L1: commercial net direction accuracy
L1_FLOOR = 0.45    # below copy-last-week baseline (measured 0.527)
L1_FULL  = 0.65    # full 20 pts
L1_POINTS = 20.0

# L2: magnitude bucket accuracy
L2_FLOOR = 0.28    # random 4-class baseline
L2_FULL  = 0.55
L2_POINTS = 15.0

# L3: crowding regime accuracy
L3_FLOOR = 0.35    # random 4-class baseline
L3_FULL  = 0.70
L3_POINTS = 15.0

# L4: extreme positioning flag F1
L4_FLOOR = 0.20
L4_FULL  = 0.70
L4_POINTS = 10.0

# L5: cross-market Spearman rank correlation
L5_FLOOR = 0.00
L5_FULL  = 0.40
L5_POINTS = 10.0

# L6: rate-regime adaptive direction accuracy (FOMC + CPI weeks)
L6_FLOOR  = 0.45
L6_FULL   = 0.65
L6_POINTS = 10.0
L6_DEFAULT_FRAC = 0.50  # awarded when < L6_MIN_WEEKS eligible
L6_MIN_WEEKS = 10

# L7: confidence calibration (Brier score over per-item direction confidence)
L7_POINTS = 5.0

# L8: cross-quarter stability
L8_POINTS = 15.0
L8_VARIANCE_CAP = 0.04  # quarterly L1 variance above this -> 0 pts

TOTAL_MAX = 100.0

# ---- valid label values ----------------------------------------------------
VALID_DIRECTIONS  = {"up", "down"}
VALID_MAGNITUDES  = {"large_increase", "small_increase",
                     "small_decrease", "large_decrease"}
VALID_REGIMES     = {"crowded_long", "neutral", "crowded_short", "extreme"}

# ---- data field names (same as CFTC SoDA 6dca-aqww) -----------------------
COMM_LONG_FIELD  = "comm_positions_long_all"
COMM_SHORT_FIELD = "comm_positions_short_all"
DATE_FIELD       = "report_date_as_yyyy_mm_dd"
CODE_FIELD       = "cftc_contract_market_code"


# ---- numeric helpers -------------------------------------------------------
def _num(v):
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return 0.0


def comm_net(rec):
    """Commercial net position for a COT record."""
    return _num(rec.get(COMM_LONG_FIELD)) - _num(rec.get(COMM_SHORT_FIELD))


def sign(x):
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


# ---- boundary-anchored statistics ------------------------------------------
# These are computable from the training data alone. The agent can reproduce
# every value here; the judge uses the identical computation. Neither the
# boundary stats nor the ground truth direction labels are the same thing.

def compute_boundary_stats(train_rows):
    """Compute per-market statistics from training rows (date <= BOUNDARY).

    Returns a dict: {market_id: {mag_q1, mag_q3, p10_3yr, p90_3yr, last_net}}

    mag_q1 / mag_q3: 25th and 75th percentile of week-over-week commercial
        net changes over the last 52 weeks before boundary. Define the
        magnitude bucket thresholds for L2.
    p10_3yr / p90_3yr: 10th and 90th percentile of commercial net over the
        last 156 weeks (3 years) before boundary. Define extreme flag for L4
        and crowding regime for L3.
    last_net: the commercial net on the last training date, for copy-last-week
        baseline construction.
    """
    by_mid = {}
    for r in train_rows:
        code = r.get(CODE_FIELD, "")
        if code not in CODE_TO_MID:
            continue
        mid = CODE_TO_MID[code]
        date = str(r.get(DATE_FIELD, ""))[:10]
        if date > BOUNDARY:
            continue
        by_mid.setdefault(mid, []).append((date, comm_net(r)))

    stats = {}
    for mid, pairs in by_mid.items():
        pairs.sort()
        nets = [n for _, n in pairs]
        changes = [nets[i] - nets[i-1] for i in range(1, len(nets))]
        last52 = sorted(changes[-52:]) if len(changes) >= 52 else sorted(changes)
        n52 = len(last52)
        q1 = last52[max(0, int(n52 * 0.25))] if n52 else 0.0
        q3 = last52[min(n52-1, int(n52 * 0.75))] if n52 else 0.0
        last156 = sorted(nets[-156:]) if len(nets) >= 156 else sorted(nets)
        n3 = len(last156)
        p10 = last156[max(0, int(n3 * 0.10))] if n3 else 0.0
        p90 = last156[min(n3-1, int(n3 * 0.90))] if n3 else 0.0
        stats[mid] = {
            "mag_q1":   q1,
            "mag_q3":   q3,
            "p10_3yr":  p10,
            "p90_3yr":  p90,
            "last_net": nets[-1] if nets else 0.0,
            "last_date": pairs[-1][0] if pairs else "",
        }
    return stats


def magnitude_bucket(change, q1, q3):
    """Classify a week-over-week change into a magnitude bucket."""
    if change >= q3:
        return "large_increase"
    if change >= 0:
        return "small_increase"
    if change >= q1:
        return "small_decrease"
    return "large_decrease"


def crowding_regime(current_net, p10, p90):
    """Classify crowding regime from current commercial net position."""
    if current_net >= p90 or current_net <= p10:
        return "extreme"
    mid_point = (p10 + p90) / 2.0
    if current_net > mid_point:
        return "crowded_long"
    if current_net < mid_point:
        return "crowded_short"
    return "neutral"


def extreme_flag(current_net, p10, p90):
    """True iff commercial net is at or beyond 10th or 90th percentile."""
    return current_net >= p90 or current_net <= p10


# ---- pure statistics (stdlib only) -----------------------------------------
def percentile(xs, p):
    """Linear-interpolation percentile, numpy 'linear' convention."""
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    rank = (p / 100.0) * (n - 1)
    lo = int(rank)
    frac = rank - lo
    if lo + 1 >= n:
        return s[-1]
    return s[lo] + frac * (s[lo + 1] - s[lo])


def spearman_rho(xs, ys):
    """Spearman rank correlation in pure Python."""
    n = len(xs)
    if n < 2:
        return 0.0
    def rank(lst):
        order = sorted(range(n), key=lambda i: lst[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n and lst[order[j]] == lst[order[i]]:
                j += 1
            avg = (i + j - 1) / 2.0
            for k in range(i, j):
                r[order[k]] = avg
            i = j
        return r
    rx, ry = rank(xs), rank(ys)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = (sum((rx[i] - mx)**2 for i in range(n)))**0.5
    dy = (sum((ry[i] - my)**2 for i in range(n)))**0.5
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def f1_binary(predicted, actual):
    """F1 for binary classification. predicted and actual are lists of bool."""
    tp = sum(1 for p, a in zip(predicted, actual) if p and a)
    fp = sum(1 for p, a in zip(predicted, actual) if p and not a)
    fn = sum(1 for p, a in zip(predicted, actual) if not p and a)
    prec = tp / (tp + fp) if tp + fp > 0 else 0.0
    rec  = tp / (tp + fn) if tp + fn > 0 else 0.0
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def _frac(x, lo, hi):
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


# ---- per-metric scorer (called from both gate.py and the judge) ------------
def score_L1(pred_dir, true_dir):
    """Returns (raw_accuracy, L1_points)."""
    pairs = [(p, t) for p, t in zip(pred_dir, true_dir) if p and t]
    if not pairs:
        return 0.0, 0.0
    acc = sum(1 for p, t in pairs if p == t) / len(pairs)
    return acc, L1_POINTS * _frac(acc, L1_FLOOR, L1_FULL)


def score_L2(pred_mag, true_mag):
    pairs = [(p, t) for p, t in zip(pred_mag, true_mag) if p and t]
    if not pairs:
        return 0.0, 0.0
    acc = sum(1 for p, t in pairs if p == t) / len(pairs)
    return acc, L2_POINTS * _frac(acc, L2_FLOOR, L2_FULL)


def score_L3(pred_reg, true_reg):
    pairs = [(p, t) for p, t in zip(pred_reg, true_reg) if p and t]
    if not pairs:
        return 0.0, 0.0
    acc = sum(1 for p, t in pairs if p == t) / len(pairs)
    return acc, L3_POINTS * _frac(acc, L3_FLOOR, L3_FULL)


def score_L4(pred_flags, true_flags):
    if not pred_flags:
        return 0.0, 0.0
    f1 = f1_binary(pred_flags, true_flags)
    return f1, L4_POINTS * _frac(f1, L4_FLOOR, L4_FULL)


def score_L5(prob_by_week, true_dir_by_week):
    """Cross-market Spearman rho averaged over weeks.

    prob_by_week: {week: {mid: direction_probability}}
    true_dir_by_week: {week: {mid: "up"/"down"}}
    """
    rhos = []
    for week in sorted(prob_by_week):
        true_week = true_dir_by_week.get(week, {})
        mids = sorted(set(prob_by_week[week]) & set(true_week))
        if len(mids) < 5:
            continue
        probs = [prob_by_week[week][m] for m in mids]
        true_vals = [1.0 if true_week[m] == "up" else 0.0 for m in mids]
        rhos.append(spearman_rho(probs, true_vals))
    if not rhos:
        return 0.0, 0.0
    mean_rho = sum(rhos) / len(rhos)
    return mean_rho, L5_POINTS * _frac(mean_rho, L5_FLOOR, L5_FULL)


def score_L6(pred_dir_by_key, true_dir_by_key, fomc_cpi_dates):
    """L1 accuracy restricted to FOMC/CPI weeks.

    pred_dir_by_key: {(mid, week): "up"/"down"}
    true_dir_by_key: same schema
    fomc_cpi_dates: set of week_ending date strings (or nearby dates)
    """
    eligible = [(p, true_dir_by_key[k])
                for k, p in pred_dir_by_key.items()
                if k[1] in fomc_cpi_dates and k in true_dir_by_key]
    if len(eligible) < L6_MIN_WEEKS:
        return None, L6_POINTS * L6_DEFAULT_FRAC
    acc = sum(1 for p, t in eligible if p == t) / len(eligible)
    return acc, L6_POINTS * _frac(acc, L6_FLOOR, L6_FULL)


def score_L7(per_item_confidence, pred_dir_by_key, true_dir_by_key):
    """Brier calibration over the agent's per-item L1 direction confidence.

    per_item_confidence: dict mapping "<mid>:<week_ending>" -> float in [0, 1].
    Returns (brier, points). Missing/malformed field -> (None, 0.0).
    """
    if not isinstance(per_item_confidence, dict) or not per_item_confidence:
        return None, 0.0
    pairs = []
    for key, pred in pred_dir_by_key.items():
        if key not in true_dir_by_key:
            continue
        conf_raw = per_item_confidence.get(f"{key[0]}:{key[1]}")
        if conf_raw is None:
            continue
        try:
            conf = float(conf_raw)
        except (TypeError, ValueError):
            continue
        if not (0.0 <= conf <= 1.0):
            continue
        correct = 1.0 if pred == true_dir_by_key[key] else 0.0
        pairs.append((conf, correct))
    if not pairs:
        return None, 0.0
    brier = sum((c - r) ** 2 for c, r in pairs) / len(pairs)
    return brier, L7_POINTS * max(0.0, 1.0 - 2.0 * brier)


def score_L8(pred_dir_by_key, true_dir_by_key):
    """Cross-quarter variance-adjusted L1.

    Quarters by week_ending: Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec.
    L8 only awards points when mean quarterly L1 exceeds L1_FLOOR (0.45),
    so a trivially consistent constant-answer solver (Invariant 10 probe)
    cannot farm stability points.
    """
    quarter_scores = {}
    for (mid, week), pred in pred_dir_by_key.items():
        if (mid, week) not in true_dir_by_key:
            continue
        q = "Q" + str((int(week[5:7]) - 1) // 3 + 1) + "_" + week[:4]
        quarter_scores.setdefault(q, []).append(
            1 if pred == true_dir_by_key[(mid, week)] else 0)
    q_means = [sum(v)/len(v) for v in quarter_scores.values() if v]
    if not q_means:
        return 0.0, 0.0
    mean = sum(q_means) / len(q_means)
    if mean < L1_FLOOR:
        return 0.0, 0.0
    if len(q_means) == 1:
        variance = 0.0
    else:
        variance = sum((x - mean)**2 for x in q_means) / len(q_means)
    stability = max(0.0, 1.0 - variance / L8_VARIANCE_CAP)
    accuracy_scale = _frac(mean, L1_FLOOR, L1_FULL)
    pts = L8_POINTS * stability * accuracy_scale
    return variance, pts


def recompute_self_reported(pred_dir, true_dir, pred_mag, true_mag,
                            pred_reg, true_reg, pred_flags, true_flags,
                            prob_by_week, true_dir_by_week):
    """Recompute the five self_reported_metrics keys from raw predictions."""
    l1_acc, _ = score_L1(pred_dir, true_dir)
    l2_acc, _ = score_L2(pred_mag, true_mag)
    l3_acc, _ = score_L3(pred_reg, true_reg)
    l4_f1,  _ = score_L4(pred_flags, true_flags)
    l5_rho, _ = score_L5(prob_by_week, true_dir_by_week)
    return {
        "L1_commercial_direction_est": round(l1_acc, 6),
        "L2_magnitude_bucket_est":     round(l2_acc, 6),
        "L3_crowding_regime_est":      round(l3_acc, 6),
        "L4_extreme_flag_f1_est":      round(l4_f1,  6),
        "L5_rank_correlation_est":     round(l5_rho, 6),
    }
