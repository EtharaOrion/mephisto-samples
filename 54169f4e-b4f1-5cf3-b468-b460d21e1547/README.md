# 54169f4e-b4f1-5cf3-b468-b460d21e1547

Corporate earnings-distress forecasting from SEC fundamentals. Acting as an equity/credit
analyst, the agent predicts which US public companies will report a net loss in the next
quarter, fitting a model on a labelled training panel and emitting a probability for every
company in the evaluation cohort. Data derives from the SEC EDGAR XBRL frames API
(public-domain US government filings).

## Task

Fit on the labelled training pair (`data/train_features.csv` + `data/train_labels.csv`) and
predict, for every company in `data/eval_features.csv`, the probability it reports a net loss
in the graded quarter. numpy and scikit-learn are available in the work image. Both work and
judge containers run with no network access.

## Deliverables

```
forecast/predictions.csv    cik,loss_probability in [0,1]
forecast/model.py           the model
forecast/notes.md           analyst notes
```

`python3 check.py` validates the submission locally before grading.

## Scoring

Grading is deterministic: the AUC of the submitted probabilities against realized SEC-filing
outcomes on a hidden cohort, anchored so that naive persistence scores 0 and perfect foresight
scores 100. `metric_lib.py` in the work image is the exact grader, so the metric is fully
inspectable.

## Calibration

Measured anchors for the anchored-AUC scale:

| Model | AUC | Anchored score |
|---|---|---|
| Perfect foresight | 1.000 | 100 |
| Features model (reference) | 0.887 | ~41 |
| Naive persistence | 0.807 | 0 |

The spread between naive persistence and the features model shows genuine signal is
extractable from the fundamentals beyond simple label carry-forward.

## Layout

```
task.toml           task contract; work and judge images pinned by digest
instruction.md      agent-facing brief
environment/        work image: training/eval features, labels, check.py, metric_lib.py
tests/              judge image: hidden cohort and deterministic AUC grader
solution/           private oracle tree: reference model and truth materials
```
