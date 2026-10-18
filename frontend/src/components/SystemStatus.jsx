import { Activity, Radio, ShieldCheck, Zap } from 'lucide-react';
export default function SystemStatus({ system = {}, connected = false }) {
  const reporting = system.assets_reporting ?? 0; const total = system.total_assets ?? 0;
  return <div className="status-strip"><div className="status-live"><span className="pulse-dot" />{system.simulator_running ? 'Simulator running' : 'Simulator stopped'}</div><span className="status-sep" /><div className="status-item"><Zap size={15} /><span>Average load</span><b>{system.average_load_pct ?? '—'} <small>%</small></b></div><div className="status-item"><ShieldCheck size={15} /><span>Risk alerts</span><b>{system.active_alerts ?? 0}<small> active</small></b></div><div className="status-item"><Radio size={15} /><span>Assets online</span><b>{reporting}<small> / {total}</small></b></div><div className="status-updated"><Activity size={14} />{connected ? 'Live telemetry' : 'Stream offline'} <span className="pulse-dot" /></div></div>;
}
