import { ArrowUpRight, ShieldAlert } from 'lucide-react';

export default function RiskCard({ asset, assessment }) {
  const risk = assessment?.risk_score ?? asset.risk ?? 0;
  const level = assessment?.risk_level ?? asset.risk_level ?? asset.status?.toUpperCase() ?? 'LOW';
  const model = assessment?.failure_prediction;
  const drivers = model?.top_features ?? [];
  return <div className="risk-card">
    <div className="risk-card-head"><div><span className="eyebrow">PROTOTYPE RISK INDEX</span><h3>Risk assessment</h3></div><span className="risk-icon"><ShieldAlert size={18} /></span></div>
    <div className="risk-score-row"><span className="risk-score">{Number(risk).toFixed(1)}<small>/100</small></span><span className="risk-pill"><ArrowUpRight size={13} />{level}</span></div>
    <div className="risk-progress"><span style={{ width: `${risk}%` }} /></div>
    <div className="risk-card-foot"><span>Anomaly score {assessment?.anomaly_score?.toFixed?.(2) ?? asset.risk_summary?.anomaly_score ?? '—'}</span><b>{asset.id} · {asset.name}</b></div>
    <small>{assessment?.disclaimer ?? 'Illustrative prototype estimate; not a calibrated real-world failure probability.'}</small>
    <section className={`failure-model-summary ${['HIGH', 'CRITICAL'].includes(model?.risk_classification) ? 'flagged' : ''}`} aria-label="Synthetic failure prediction model">
      <div className="failure-model-heading"><span>FAILURE HORIZON MODEL</span><b>{model?.available ? model.risk_classification : 'UNAVAILABLE'}</b></div>
      {model?.available ? <>
        <p>{model.message} Horizon: {model.horizon_ticks} simulator ticks ({model.horizon_seconds}s at the current sample interval). Prediction recorded {assessment?.timestamp ? new Date(assessment.timestamp).toLocaleTimeString() : 'now'}.</p>
        <p>Uncalibrated model score: {model.model_score == null ? '—' : `${model.model_score.toFixed(3)} / 1.000`}. This score is not a failure probability.</p>
        <div className="failure-model-drivers">{drivers.map(item => <span key={item.feature}>{item.feature.replaceAll('_', ' ')} · {Math.round(item.importance * 100)}% importance <b>{Number(item.observed_value).toFixed(2)}</b></span>)}</div>
        <small>Trained on synthetic simulator data. Score bands are provisional and not validated safety thresholds.</small>
      </> : <p>{model?.message ?? 'Model artifact unavailable; the rule-based risk and anomaly assessments remain active.'}</p>}
    </section>
  </div>;
}
