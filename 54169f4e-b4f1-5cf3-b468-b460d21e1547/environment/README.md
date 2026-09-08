# Corporate Earnings-Distress Forecast

You are an equity/credit analyst. Predict, for each company in the evaluation
cohort, the probability it will report a NET LOSS in the graded quarter.

Data (in `data/`):
- `train_features.csv` + `train_labels.csv` - a labelled boundary->outcome pair
  (company fundamentals and whether each reported a net loss the following
  period). Fit a model on this.
- `eval_features.csv` - the evaluation cohort's boundary fundamentals (NO
  labels). Predict these.

Deliverable: write `forecast/predictions.csv` with columns `cik,loss_probability`
(one row per eval company, probability in [0,1]). Put your model code in
`forecast/model.py` (provenance) and fill `forecast/notes.md`.

Scoring: `metric_lib.py` is the exact grader - AUC of your probabilities vs the
realized outcome, anchored so naive persistence (predict loss iff currently
loss-making) scores 0 and perfect foresight scores 100. numpy and scikit-learn
are available. Run `python3 check.py` to validate format and see your model's
cross-validated AUC on the training pair.
