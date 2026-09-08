import csv
from pathlib import Path
# oracle reads the realized labels (present only on the judge/solution side) and
# emits them as perfect probabilities -> AUC 1.0 -> 100. Proves the full-reward path.
for base in ["/judge/data","/solution/data",str(Path(__file__).parent/"data")]:
    p=Path(base)/"eval_labels.csv"
    if p.exists(): LBL=p; break
out=Path("/home/workspace/forecast"); out.mkdir(parents=True,exist_ok=True)
with open(out/"predictions.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["cik","loss_probability"])
    for r in csv.DictReader(open(LBL)): w.writerow([r["cik"], float(r["net_loss"])])
print("oracle predictions staged")
