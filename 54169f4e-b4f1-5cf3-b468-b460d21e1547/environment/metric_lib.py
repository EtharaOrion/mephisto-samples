"""Deterministic AUC grader for sec_earnings_distress_forecast.

PUBLIC. Contains NO labels and NO model - only the scoring of submitted
probabilities against realized net-loss labels. Pure standard library.

score = 100 * clamp((auc - NAIVE_AUC) / (1.0 - NAIVE_AUC), 0, 1)
where NAIVE_AUC is the frozen naive-persistence anchor measured at build.
AUC is computed exactly (rank-sum / Mann-Whitney), ties averaged.
"""
from __future__ import annotations

NAIVE_AUC = 0.807   # frozen naive-persistence anchor (2025Q3 boundary loss-flag -> 2026Q1)


def auc(pairs):
    """pairs: list of (probability, label in {0,1}). Exact ROC-AUC via rank-sum."""
    pos = [p for p, y in pairs if y == 1]
    neg = [p for p, y in pairs if y == 0]
    n_pos, n_neg = len(pos), len(neg)
    if n_pos == 0 or n_neg == 0:
        return 0.5
    order = sorted(pairs, key=lambda t: t[0])
    ranks = [0.0] * len(order)
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and order[j][0] == order[i][0]:
            j += 1
        avg = (i + 1 + j) / 2.0            # average rank for ties (1-indexed)
        for k in range(i, j):
            ranks[k] = avg
        i = j
    rank_sum_pos = sum(r for r, (p, y) in zip(ranks, order) if y == 1)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def score_from_auc(a):
    lo, hi = NAIVE_AUC, 1.0
    frac = max(0.0, min(1.0, (a - lo) / (hi - lo)))
    return round(100.0 * frac, 4)
