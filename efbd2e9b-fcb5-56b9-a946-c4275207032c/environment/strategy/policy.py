"""Starter policy: the un-triaged desk. Spread review capacity evenly.

This is a LEGAL submission and it scores ~0: the lanes are anchored on the
copy frontier (the best mechanical single-column book), and equal weight sits
far below it. Your job is to beat every mechanical strategy - see README.md.

allocate(universe, history, asof) -> {cert: weight}
  universe : list of boundary-quarter bank dicts (see credit_lib.FEATURE_COLS)
  history  : {"20241231": [...], ..., "20251231": [...]} five public quarters
  asof     : "2025-12-31"
Constraints: weights sum to 1 (+/-1e-6), max weight 0.0037 (>= 270 banks).
"""


def allocate(universe, history, asof):
    certs = [r["CERT"] for r in universe]
    n = len(certs)
    return {c: 1.0 / n for c in certs}
