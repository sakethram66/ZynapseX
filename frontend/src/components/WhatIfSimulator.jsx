import { useEffect, useState } from 'react';
import { ArrowRight, RotateCcw, SlidersHorizontal } from 'lucide-react';
import { clearScenario, getScenarios, injectScenario, runWhatIf } from '../services/api';

export default function WhatIfSimulator({ assets = [] }) {
  const [assetId, setAssetId] = useState('');
  const [scenarioType, setScenarioType] = useState('take_offline');
  const [reduction, setReduction] = useState(25);
  const [scenario, setScenario] = useState('overheating');
  const [scenarios, setScenarios] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (!assetId && assets.length) setAssetId(assets[0].id); }, [assets, assetId]);
  useEffect(() => { getScenarios().then(value => setScenarios(value.available ?? [])).catch(() => {}); }, []);
  const run = async () => {
    setBusy(true); setError('');
    try { setResult(await runWhatIf({ scenario_type: scenarioType, asset_id: assetId, ...(scenarioType === 'reduce_load' ? { reduction_pct: reduction } : {}) })); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const inject = async () => {
    setBusy(true); setError('');
    try { await injectScenario(assetId, scenario); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const clear = async () => {
    setBusy(true); setError('');
    try { await clearScenario(assetId); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  return <section className="panel simulator-panel"><div className="panel-heading"><div><span className="eyebrow">SCENARIO PLANNER</span><h2>What if simulator</h2></div><SlidersHorizontal size={17} className="muted-icon" /></div>
    <p className="sim-intro">Illustrative decision support based on the current simulated grid readings.</p>
    <label className="slider-label"><span>Transformer</span></label><select value={assetId} onChange={e => setAssetId(e.target.value)}>{assets.map(a => <option key={a.id} value={a.id}>{a.id} · {a.name}</option>)}</select>
    <label className="slider-label"><span>What-if action</span></label><select value={scenarioType} onChange={e => setScenarioType(e.target.value)}><option value="take_offline">Take transformer offline</option><option value="reduce_load">Reduce load</option></select>
    {scenarioType === 'reduce_load' && <><label className="slider-label"><span>Load reduction</span><b>{reduction}%</b></label><input type="range" min="1" max="100" value={reduction} onChange={e => setReduction(+e.target.value)} /><div className="range-labels"><span>1%</span><span>100%</span></div></>}
    <button className="sim-cta" onClick={run} disabled={!assetId || busy}>{busy ? 'Running…' : 'Run illustrative simulation'} <ArrowRight size={14} /></button>
    {result && <div className="sim-result"><span>Illustrative verdict · {result.verdict}</span><strong className={result.safe ? 'risk-low' : 'risk-high'}>{result.safe ? 'Within limits' : 'Review required'}</strong><span className="result-trend">{result.explanation}</span><small>Unserved load: {Number(result.unserved_kva ?? 0).toFixed(1)} kVA · {result.violations?.length ?? 0} violations</small>{result.changes?.map(change => <small key={change.asset_id}>{change.asset_id}: {change.load_pct_before.toFixed(1)}% → {change.load_pct_after.toFixed(1)}% ({change.status_after})</small>)}{result.violations?.map((item, i) => <small key={`v${i}`}>Violation: {item}</small>)}{result.alternatives?.map((item, i) => <small key={`a${i}`}>Alternative: {item}</small>)}{result.assumptions?.map((item, i) => <small key={`s${i}`}>Assumption: {item}</small>)}</div>}
    <div className="scenario-injection"><label className="slider-label"><span>Inject a live simulator scenario</span></label><select value={scenario} onChange={e => setScenario(e.target.value)}>{scenarios.map(item => <option key={item.scenario} value={item.scenario}>{item.scenario.replaceAll('_', ' ')}</option>)}</select><div className="scenario-actions"><button className="sim-cta" onClick={inject} disabled={!assetId || busy}>Inject scenario</button><button className="sim-reset" onClick={clear} disabled={!assetId || busy}><RotateCcw size={13} />Clear</button></div></div>
    {error && <p role="alert" className="sim-error">{error}</p>}
  </section>;
}
