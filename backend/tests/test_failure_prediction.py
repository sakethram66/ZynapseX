from app.ml.failure_prediction import get_failure_predictor
from app.ml.synthetic_failure_data import generate_dataset
from app.ml.synthetic_failure_data import split_by_transformer
from app.pipeline import GridPipeline
from app.schemas import FailurePrediction
from tests.helpers import TS


def test_synthetic_dataset_is_repeatable_and_labels_the_future_horizon():
    a = generate_dataset(episodes=20, ticks=60, seed=919)
    b = generate_dataset(episodes=20, ticks=60, seed=919)
    assert a.equals(b)
    assert {"temperature", "voltage", "current", "load_pct", "frequency",
            "vibration", "power_factor", "temp_slope", "vibration_slope",
            "load_slope", "failure_within_horizon"} <= set(a.columns)
    assert a.failure_within_horizon.sum() > 0
    for _, episode in a.groupby("episode_id"):
        positives = episode[episode.failure_within_horizon == 1]
        assert len(positives) in (0, 12)
        if len(positives):
            event_tick = int(episode.failure_tick.iloc[0])
            assert positives.episode_tick.tolist() == list(range(event_tick - 12, event_tick))


def test_persisted_split_is_episode_disjoint_and_stratified():
    frame = generate_dataset(episodes=20, ticks=60, seed=220)
    train, test = split_by_transformer(frame, test_size=0.2, seed=42)
    assert set(train.episode_id).isdisjoint(set(test.episode_id))
    assert set(train.asset_id).isdisjoint(set(test.asset_id))
    assert train.failure_within_horizon.nunique() == test.failure_within_horizon.nunique() == 2
    assert train.episode_id.nunique() == 16 and test.episode_id.nunique() == 4


def test_trained_artifact_returns_class_and_drivers_without_probability():
    predictor = get_failure_predictor()
    assert predictor is not None
    row = {"temperature": 70.0, "voltage": 11.0, "current": 40.0,
           "load_pct": 60.0, "frequency": 50.0, "vibration": 1.5,
           "power_factor": 0.96, "temp_slope": 0.0, "vibration_slope": 0.0,
           "load_slope": 0.0, "rating_kva": 1000.0,
           "rated_current_a": 52.5}
    result = predictor.predict_many([row], sample_interval_s=2.0)[0]
    assert result.available and result.model_version == "synthetic-rf-v1"
    assert result.risk_classification in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert result.probability is None and not result.probability_calibrated
    assert result.model_score is not None and "not a failure probability" in result.model_score_meaning
    assert result.horizon_ticks == 12 and result.horizon_seconds == 24
    assert result.top_features and result.top_features[0].feature in row


def test_invalid_model_input_is_reported_without_emitting_a_prediction():
    predictor = get_failure_predictor()
    assert predictor is not None
    import pytest
    with pytest.raises(ValueError, match="invalid failure model input"):
        predictor.predict_many([{}], sample_interval_s=2.0)


def test_missing_model_artifact_disables_only_failure_predictor(tmp_path):
    assert get_failure_predictor(str(tmp_path / "missing-model.joblib")) is None


class _FlagPredictor:
    def predict_many(self, rows, sample_interval_s, thresholds=None):
        return [FailurePrediction(
            available=True, model_version="test-model", horizon_ticks=12,
            horizon_seconds=24, predicted_failure_within_horizon=True,
            risk_classification="HIGH", probability=None,
            probability_calibrated=False, message="Synthetic test flag",
        ) for _ in rows]


class _NormalDetector:
    def score_many(self, rows):
        return [{"anomaly_score": 0.0, "is_anomaly": False,
                 "isolation_forest_score": 0.0, "zscore_score": 0.0,
                 "max_abs_z": 0.0, "top_deviations": []} for _ in rows]


def test_classifier_stays_separate_and_feeds_alerts_and_recommendations(repo, settings):
    pipeline = GridPipeline(repo, settings, detector=_NormalDetector(), failure_predictor=_FlagPredictor())
    pipeline.bootstrap()
    messages = []
    for tick in range(3):
        messages = pipeline.step(TS.replace(second=TS.second + tick * 2))
    assessment = pipeline.latest["T01"]["assessment"]
    assert assessment.failure_prediction.risk_classification == "HIGH"
    assert assessment.failure_prediction.probability is None
    # The classifier flag does not overwrite the independent novelty detector.
    assert assessment.is_anomaly is False
    assert any(a.code == "FAILURE_HORIZON" for a in repo.list_alerts("T01", active_only=True))
    assert any(r.action == "INCREASE_MONITORING"
               for r in repo.list_recommendations("T01"))
    tick = next(message for message in messages if message["type"] == "tick")
    assert tick["data"]["risks"][0]["failure_prediction"]["probability"] is None
