"""JUDGE-ONLY scorer for sec_earnings_distress_forecast. Reads the agent's
submitted forecast/predictions.csv and the judge-only eval_labels, computes AUC
(pure stdlib), anchors to 0-100. Runs NO agent code."""
from __future__ import annotations
import csv, json, os, sys
from pathlib import Path
JUDGE = Path(__file__).resolve().parent
sys.path.insert(0, str(JUDGE))
import metric_lib as M
DATA = JUDGE / "data"

def emit(valid, score, summary, details, metrics):
    print(">>>>> Start Structured Result")
    print(json.dumps({"valid":valid,"score":float(score),"pass_rate":1.0 if valid and score>0 else 0.0,
        "total_tests":max(1,len(details)),"passed":sum(1 for d in details if d.get("status")=="PASSED"),
        "failed":sum(1 for d in details if d.get("status")=="FAILED"),"errors":0,
        "summary":summary,"details":details,"metrics":metrics}, ensure_ascii=False))
    print(">>>>> End Structured Result")

def main():
    ws = Path(os.environ.get("TRIAGE_WORKSPACE","/home/workspace"))
    sub = ws / "forecast" / "predictions.csv"
    details, metrics = [], {}
    if not sub.exists():
        metrics["rejected"]="missing_deliverable"
        emit(False,0.0,"forecast/predictions.csv missing",
             [{"name":"deliverable","status":"FAILED","score":0.0}], metrics); return
    labels = {r["cik"]: int(r["net_loss"]) for r in csv.DictReader(open(DATA/"eval_labels.csv"))}
    preds = {}
    try:
        for r in csv.DictReader(open(sub)):
            try:
                p = float(r["loss_probability"])
                if 0.0 <= p <= 1.0: preds[r["cik"]] = p
            except (ValueError, KeyError, TypeError): pass
    except Exception as e:
        metrics["rejected"]="malformed_csv"; emit(False,0.0,f"predictions.csv unreadable: {e}",[],metrics); return
    # missing cik -> uninformative prior 0.5 (never credited)
    pairs = [(preds.get(c, 0.5), labels[c]) for c in labels]
    a = M.auc(pairs); score = M.score_from_auc(a)
    details.append({"name":"auc","status":"PASSED" if score>0 else "FAILED","score":score,
                    "message":f"AUC={a:.4f} (naive {M.NAIVE_AUC}) -> {score:.2f}/100"})
    metrics.update({"auc":round(a,4),"naive_auc":M.NAIVE_AUC,"n_eval":len(labels),
                    "n_predicted":len(preds),"score":score})
    emit(True, score, f"AUC {a:.4f} -> {score:.2f}/100 over {len(labels)} companies", details, metrics)

if __name__ == "__main__":
    main()
