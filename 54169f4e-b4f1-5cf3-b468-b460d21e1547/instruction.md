Read README.md, then act as an equity/credit analyst: fit a model on the
labelled training pair (data/train_features.csv + data/train_labels.csv) and
predict, for every company in data/eval_features.csv, the probability it will
report a net loss in the graded quarter. Write forecast/predictions.csv
(cik,loss_probability in [0,1]), your model in forecast/model.py, and
forecast/notes.md. numpy and scikit-learn are available. Grading is
deterministic: the AUC of your probabilities against the realized SEC-filing
outcome on a hidden cohort, anchored so naive persistence scores 0 and perfect
foresight scores 100 (metric_lib.py is the exact grader). Validate with
python3 check.py.
