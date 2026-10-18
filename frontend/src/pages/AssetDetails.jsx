import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ClipboardList, Gauge, MapPin, Thermometer, Zap } from 'lucide-react';
import RiskCard from '../components/RiskCard'; import SensorCharts from '../components/SensorCharts'; import Explainability from '../components/Explainability'; import EventTimeline from '../components/EventTimeline';
import { getAsset, getAssetReadings } from '../services/api';
export default function AssetDetails({ asset, reading, risk, history = [], events = [], onBack }) {
  const [detail, setDetail] = useState(null);
  const [storedHistory, setStoredHistory] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    Promise.all([getAsset(asset.id), getAssetReadings(asset.id, 120)]).then(([info, points]) => {
      if (active) { setDetail(info); setStoredHistory(points); setError(''); }
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [asset.id]);
  const currentAsset = detail ? { ...asset, name: detail.name, substation_id: detail.substation_id, rating_kva: detail.rating_kva, risk_summary: detail.risk } : asset;
  const currentRisk = risk ?? detail?.assessment;
  const r = reading ?? detail?.latest_reading ?? asset.latest_reading ?? {};
  const points = useMemo(() => [...new Map([...storedHistory, ...history].map(point => [point.timestamp, point])).values()].sort((a, b) => a.timestamp.localeCompare(b.timestamp)), [storedHistory, history]);
  return <><div className="page-heading asset-page-heading"><div><button className="back-link" onClick={onBack}><ArrowLeft size={14} />Back to overview</button><div className="breadcrumb">ASSETS <span>/</span> {asset.id}</div><h1>{currentAsset.name}</h1><p>{asset.id} <span className="crumb-dot">·</span> Power transformer <span className="crumb-dot">·</span> {asset.region}</p></div><button className="export-button"><ClipboardList size={15} />Simulation telemetry</button></div>{error && <p role="alert">Asset history could not refresh: {error}</p>}<div className="asset-info-strip"><div><MapPin size={16} /><span>Substation</span><b>{currentAsset.substation_id}</b></div><div><Zap size={16} /><span>Rated capacity</span><b>{currentAsset.rating_kva} kVA</b></div><div><Thermometer size={16} /><span>Temperature</span><b>{r.temperature ?? '—'}°C</b></div><div><Gauge size={16} /><span>Current load</span><b>{r.load_pct ?? '—'}%</b></div><span className={`risk-chip ${asset.status.toLowerCase()}`}>{asset.status}</span></div><div className="detail-grid"><RiskCard asset={currentAsset} assessment={currentRisk} /><SensorCharts readings={points.length ? points : (r.timestamp ? [r] : [])} /><Explainability asset={currentAsset} assessment={currentRisk} /><EventTimeline events={events} /></div></>;
}
