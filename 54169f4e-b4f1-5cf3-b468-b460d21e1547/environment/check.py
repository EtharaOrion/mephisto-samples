#!/usr/bin/env python3
"""Validate predictions.csv format + report train-CV AUC (no eval labels here)."""
import csv, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE)); import metric_lib as M
sub=HERE/"forecast"/"predictions.csv"
if not sub.exists(): print("no forecast/predictions.csv yet"); sys.exit(1)
ev={r["cik"] for r in csv.DictReader(open(HERE/"data"/"eval_features.csv"))}
n=0; bad=0
for r in csv.DictReader(open(sub)):
    n+=1
    try:
        p=float(r["loss_probability"])
        if not(0<=p<=1) or r["cik"] not in ev: bad+=1
    except: bad+=1
print(f"predictions: {n} rows, {bad} malformed/unknown-cik, eval cohort size {len(ev)}")
print("OK - format valid" if bad==0 and n>=len(ev)*0.9 else "WARN - cover all eval ciks with probabilities in [0,1]")
