export default function FailureModelSummary({ model }) {
  const evaluation = model?.evaluation;
  const metrics = evaluation ? [
    ['Precision', evaluation.precision], ['Recall', evaluation.recall],
    ['F1', evaluation.f1], ['ROC-AUC', evaluation.roc_auc_uncalibrated_score],
  ] : [];
  return <section className="panel model-evaluation-panel">
    <div className="panel-heading"><div><span className="eyebrow">PREDICTION MODEL</span><h2>Failure horizon evaluation</h2></div><span className={`model-status ${model?.available ? 'is-available' : ''}`}><i />{model?.available ? 'Model online' : 'Model unavailable'}</span></div>
    {evaluation ? <><p className="model-horizon">Holdout test · {evaluation.test_rows.toLocaleString()} readings · next {evaluation.prediction_horizon_ticks} simulator ticks</p><div className="model-metric-grid">{metrics.map(([label, value]) => <div key={label}><span>{label}</span><b>{value == null ? 'N/A' : Number(value).toFixed(2)}</b></div>)}</div><p className="model-baseline">Baseline F1 {Number(evaluation.baseline?.f1 ?? 0).toFixed(2)} · {evaluation.test_positive_rows.toLocaleString()} positive labels</p></> : <p className="muted-copy">No model evaluation report is available. Generate data and train the model to create one.</p>}
    <p className="model-disclaimer">{model?.data_notice ?? 'Synthetic data only.'} These scores are uncalibrated model outputs, not failure probabilities.</p>
  </section>;
}
