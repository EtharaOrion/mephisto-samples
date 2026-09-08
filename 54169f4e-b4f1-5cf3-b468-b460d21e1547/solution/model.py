"""Reference walk-forward model: engineer ratios, fit gradient boosting on the
labelled train pair, predict eval loss probabilities. Runs in the agent's own
container (numpy/sklearn available). Writes forecast/predictions.csv."""
import csv, numpy as np
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" if (HERE.parent / "data").exists() else Path("data")

def load(path):
    return [dict(r) for r in csv.DictReader(open(path))]
def f(r, k):
    try: return float(r[k])
    except: return None
def feats(r):
    a = f(r, "total_assets") or 1.0
    ni = f(r, "net_income") or 0.0; nip = f(r, "net_income_prior") or 0.0
    return [ni/a, nip/a, (f(r,"revenue") or 0)/a, (f(r,"stockholders_equity") or 0)/a,
            (f(r,"total_liabilities") or 0)/a, 1.0 if ni<0 else 0.0, 1.0 if nip<0 else 0.0,
            np.log10(a) if a>0 else 0.0]

tr = load(DATA/"train_features.csv"); trl = {r["cik"]: int(r["net_loss"]) for r in load(DATA/"train_labels.csv")}
ev = load(DATA/"eval_features.csv")
Xtr = np.array([feats(r) for r in tr]); ytr = np.array([trl[r["cik"]] for r in tr])
Xev = np.array([feats(r) for r in ev])
m = HistGradientBoostingClassifier(max_depth=3, max_iter=400, learning_rate=0.04, random_state=0).fit(Xtr, ytr)
proba = m.predict_proba(Xev)[:, 1]
out = HERE.parent / "forecast" if (HERE.parent/"forecast").exists() else Path("forecast")
out.mkdir(exist_ok=True)
with open(out/"predictions.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["cik","loss_probability"])
    for r, p in zip(ev, proba): w.writerow([r["cik"], round(float(p),6)])
print("wrote", len(ev), "predictions")
