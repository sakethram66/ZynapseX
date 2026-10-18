# Synthetic transformer failure-horizon model

## What it predicts

The Random Forest predicts `failure_within_horizon`: whether a scheduled synthetic event occurs in the next 12 simulator ticks (1 through 12 ticks ahead). At the default two-second tick interval, that is a 24-second horizon. The API returns the active horizon in ticks and seconds. This is a development prototype trained on generated scenario schedules, not observed transformer failures. Holdout metrics do not estimate real-world predictive accuracy.

## Dataset and provenance

The deterministic generator in `scripts/generate_failure_dataset.py` uses this project's `GridSimulator` and scenarios with seed `73021`, 240 independent episodes, and 100 ticks per episode. Half contain a synthetic scheduled event; control episodes can contain short, self-clearing stresses. An event episode ends before the scheduled event, and readings are positive only when the event is 1–12 ticks ahead. Labels are generated from the schedule, not inferred from sensor thresholds.

The generator writes:

- `data/synthetic_transformer_failure_dataset.csv`: 21,800 total rows, 20,360 negative and 1,440 positive.
- `data/synthetic_transformer_failure_train.csv`: 17,489 rows from 192 episodes and 16 transformer IDs.
- `data/synthetic_transformer_failure_test.csv`: 4,311 rows from 48 episodes and 4 transformer IDs.

The 80/20 train/test split keeps all episodes from each transformer ID in one partition; neither asset IDs nor episode IDs overlap. The generator's asset schedule gives each held-out transformer positive and negative episodes. Columns include transformer ID, timestamp, temperature, voltage, current, load percentage, frequency, vibration, power factor, and rolling least-squares temperature, vibration, and load slopes, plus rating metadata. The simulator provides one voltage reading, not separate input/output voltage sensors. Episode/scenario/event and label-provenance columns are excluded from model inputs.

A real transformer dataset was investigated: [IEEE DataPort record](https://doi.org/10.21227/qnt2-hy89) describes 13 transformer/load/environment features and a failure label, and says the source data is available under CC BY 4.0. However, its files require an IEEE DataPort subscription, and its processed records do not provide time-aligned sensor histories or a future failure horizon. It could not be accessed and verified as suitable for this implementation. See also the record's [linked source repository](https://github.com/julihdez36/Predictive-maintenance). Therefore all checked-in model data is synthetic and labelled as such.

Regenerate data from `backend/`:

```powershell
python scripts/generate_failure_dataset.py
```

Options include `--episodes`, `--ticks`, `--seed`, `--output`, `--train-output`, and `--test-output`. Episode count must be even and at least 10. The default horizon is 12 ticks.

## Training and measured evaluation

From `backend/`, install `requirements.txt` and run:

```powershell
python scripts/train_failure_model.py
```

The script reads the persisted train and test CSVs, rejects overlapping asset or episode IDs, fits median imputation on training rows only, then trains a 300-tree Random Forest with `balanced_subsample` class weighting. It writes `artifacts/failure_model.joblib` (the fitted preprocessing and model pipeline) and `reports/failure_model_metrics.json`. Use `--train-dataset`, `--test-dataset`, `--model`, `--report`, and `--seed` to override paths/settings. The API loads the saved artifact once at startup; `FAILURE_MODEL_PATH` overrides the default. Missing, invalid, or scikit-learn-version-mismatched artifacts disable only this classifier and return an unavailable result.

Measured results, seed 42, on 4,311 held-out rows from 4 unseen transformers (288 positive, 4,023 negative):

| Metric | Random Forest | Majority-class baseline |
|---|---:|---:|
| Precision | 0.4674 | 0.0000 |
| Recall | 0.5729 | 0.0000 |
| F1 | 0.5148 | 0.0000 |
| Confusion matrix `[ [TN, FP], [FN, TP] ]` | `[[3835, 188], [123, 165]]` | `[[4023, 0], [288, 0]]` |
| ROC-AUC | 0.9456 | N/A |

Positive prevalence is 6.68%. Precision, recall, F1, and confusion matrices use an uncalibrated score cutoff of 0.40. ROC-AUC uses the same uncalibrated Random Forest ranking scores and does not validate calibration. These results compare models only within the synthetic generator; they are not real-world accuracy.

## Runtime output and dashboard

The anomaly detector, rule-based engineering risk index, and future-event classifier remain separate. Each assessment includes a `failure_prediction` object with model availability/version, classification, horizon, timestamp via the enclosing assessment, score, score meaning, and top global feature importances with current values. `probability` remains null because calibration is not validated. `model_score` is an uncalibrated Random Forest class score between zero and one, not a probability.

Default category cutoffs are `0.20,0.40,0.65`: LOW below 0.20, MEDIUM from 0.20, HIGH from 0.40, and CRITICAL from 0.65. Configure these provisional display/alert thresholds with `FAILURE_SCORE_THRESHOLDS`. They are not validated safety limits; changing them does not update the persisted holdout evaluation. HIGH and CRITICAL predictions can trigger a warning after three consecutive flags and an increase-monitoring recommendation. They never control equipment. `GET /api/model/failure` returns model availability and the evaluation report; `/api/predictions/{asset_id}?history=100` includes recent failure classifications in the saved history. The overview dashboard displays evaluation metrics and a synthetic-data disclaimer; asset details show recent predictions, anomaly results, sensor history, and feature drivers.

## Limitations

- There are no verified, accessible, time-aligned real sensor histories with future transformer failure labels in this project.
- Synthetic event schedules and simulator scenario effects have not been validated against utility fleet behavior.
- Holdout episodes come from the same simulator generator, so this is not an independent fleet or time-based evaluation.
- Metrics are limited and do not establish real-world accuracy or a safe operating threshold.
- The score is uncalibrated. Feature importances are global drivers, not causal per-reading explanations.
- Only a single voltage sensor is represented by the current simulator.
- Use representative field histories and outcome labels, validate across assets and time, assess calibration and operating thresholds, and obtain engineering review before operational use.
