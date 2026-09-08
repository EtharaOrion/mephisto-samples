# Starter: naive persistence baseline (predict loss iff currently loss-making).
# This scores ~0 (it IS the floor anchor). Replace with a real model - numpy and
# scikit-learn are available; fit on data/train_*.csv, predict data/eval_features.csv.
import csv
from pathlib import Path
D=Path(__file__).resolve().parent.parent/"data"
ev=[dict(r) for r in csv.DictReader(open(D/"eval_features.csv"))]
out=Path(__file__).resolve().parent
with open(out/"predictions.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["cik","loss_probability"])
    for r in ev:
        try: ni=float(r["net_income"])
        except: ni=0.0
        w.writerow([r["cik"], 1.0 if ni<0 else 0.0])
