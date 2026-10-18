"""Train and evaluate the synthetic-data Random Forest failure classifier."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.pipeline import Pipeline

from app.ml.synthetic_failure_data import HORIZON_TICKS, MODEL_FEATURES, TARGET
from app.config import DEFAULT_FAILURE_SCORE_THRESHOLDS

MODEL_VERSION = "synthetic-rf-v1"


def train(train_dataset: Path, test_dataset: Path, model_path: Path, report_path: Path,
          random_state: int = 42) -> dict:
    train_frame = pd.read_csv(train_dataset)
    test_frame = pd.read_csv(test_dataset)
    required = {"episode_id", "episode_had_failure", TARGET, *MODEL_FEATURES}
    missing = sorted(required - set(train_frame.columns))
    missing += sorted(required - set(test_frame.columns))
    if missing:
        raise ValueError(f"train/test dataset is missing columns: {', '.join(sorted(set(missing)))}")
    train_groups = train_frame[["episode_id", "episode_had_failure"]].drop_duplicates()
    test_groups = test_frame[["episode_id", "episode_had_failure"]].drop_duplicates()
    if train_groups.episode_id.duplicated().any() or test_groups.episode_id.duplicated().any():
        raise ValueError("episode_had_failure must be consistent within each episode")
    overlap = set(train_groups.episode_id) & set(test_groups.episode_id)
    if overlap:
        raise ValueError(f"episode leakage: {len(overlap)} episode IDs appear in both train and test")
    asset_overlap = set(train_frame.asset_id) & set(test_frame.asset_id)
    if asset_overlap:
        raise ValueError(f"transformer leakage: {len(asset_overlap)} asset IDs appear in both train and test")
    y_train = train_frame[TARGET].astype(int)
    y_test = test_frame[TARGET].astype(int)
    if y_train.nunique() < 2 or y_test.nunique() < 2:
        raise ValueError("train and test partitions must each contain both target classes")

    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("classifier", RandomForestClassifier(
            n_estimators=300, min_samples_leaf=3, class_weight="balanced_subsample",
            random_state=random_state, n_jobs=-1,
        )),
    ])
    model.fit(train_frame[MODEL_FEATURES], y_train)
    scores = model.predict_proba(test_frame[MODEL_FEATURES])[:, list(model.classes_).index(1)]
    decision_threshold = DEFAULT_FAILURE_SCORE_THRESHOLDS[1]
    predicted = (scores >= decision_threshold).astype(int)
    matrix = confusion_matrix(y_test, predicted, labels=[0, 1])
    baseline_predicted = [0] * len(y_test)  # majority-class, all-negative baseline
    baseline_matrix = confusion_matrix(y_test, baseline_predicted, labels=[0, 1])
    clf = model.named_steps["classifier"]
    importances = sorted(zip(MODEL_FEATURES, clf.feature_importances_), key=lambda x: x[1], reverse=True)
    report = {
        "model_version": MODEL_VERSION,
        "scikit_learn_version": sklearn.__version__,
        "dataset": {"train": str(train_dataset.name), "test": str(test_dataset.name)},
        "dataset_provenance": "synthetic; generated from this project's simulator and scheduled synthetic event labels",
        "prediction_horizon_ticks": HORIZON_TICKS,
        "positive_label": TARGET,
        "split_method": "80/20 group split by transformer ID; neither asset IDs nor episode IDs overlap",
        "train_transformers": int(train_frame.asset_id.nunique()),
        "test_transformers": int(test_frame.asset_id.nunique()),
        "random_state": random_state,
        "train_episodes": int(train_groups.episode_id.nunique()),
        "test_episodes": int(test_groups.episode_id.nunique()),
        "train_rows": int(len(train_frame)),
        "test_rows": int(len(test_frame)),
        "train_positive_rows": int(y_train.sum()),
        "test_positive_rows": int(y_test.sum()),
        "test_positive_prevalence": float(y_test.mean()),
        "model_decision_score_threshold": float(decision_threshold),
        "precision": float(precision_score(y_test, predicted, zero_division=0)),
        "recall": float(recall_score(y_test, predicted, zero_division=0)),
        "f1": float(f1_score(y_test, predicted, zero_division=0)),
        "confusion_matrix_labels_0_1": matrix.tolist(),
        "baseline": {
            "name": "majority class (always predict no failure)",
            "precision": float(precision_score(y_test, baseline_predicted, zero_division=0)),
            "recall": float(recall_score(y_test, baseline_predicted, zero_division=0)),
            "f1": float(f1_score(y_test, baseline_predicted, zero_division=0)),
            "confusion_matrix_labels_0_1": baseline_matrix.tolist(),
            "roc_auc": None,
        },
        # ROC-AUC uses uncalibrated RF ranking scores; it does not validate
        # probability calibration.
        "roc_auc_uncalibrated_score": float(roc_auc_score(y_test, scores)) if y_test.nunique() == 2 else None,
        "probability_calibration_validated": False,
        "risk_score_thresholds": list(DEFAULT_FAILURE_SCORE_THRESHOLDS),
        "calibrated_probability_exposed": False,
        "global_feature_importance": [{"feature": k, "importance": float(v)} for k, v in importances],
        "limitations": [
            "Synthetic labels are scheduled simulator events, not observed failures.",
            "Holdout metrics measure separation within this synthetic generator only.",
            "Metrics do not establish real-world accuracy or calibrated failure probability.",
        ],
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": model, "metadata": {
        "model_version": MODEL_VERSION,
        "scikit_learn_version": sklearn.__version__,
        "prediction_horizon_ticks": HORIZON_TICKS,
        "features": MODEL_FEATURES,
        "dataset_provenance": report["dataset_provenance"],
        "probability_calibration_validated": False,
    }}, model_path, compress=3)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-dataset", type=Path, default=root / "data" / "synthetic_transformer_failure_train.csv")
    parser.add_argument("--test-dataset", type=Path, default=root / "data" / "synthetic_transformer_failure_test.csv")
    parser.add_argument("--model", type=Path, default=root / "artifacts" / "failure_model.joblib")
    parser.add_argument("--report", type=Path, default=root / "reports" / "failure_model_metrics.json")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    report = train(args.train_dataset, args.test_dataset, args.model, args.report, args.seed)
    print(json.dumps({k: report[k] for k in (
        "precision", "recall", "f1", "confusion_matrix_labels_0_1",
        "roc_auc_uncalibrated_score", "train_episodes", "test_episodes",
        "train_positive_rows", "test_positive_rows",
    )}, indent=2))
    print("Saved model:", args.model)
    print("Saved evaluation:", args.report)


if __name__ == "__main__":
    main()
