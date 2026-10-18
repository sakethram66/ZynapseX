import { ArrowDownRight, ArrowUpRight, Box, CircleAlert, Gauge, ShieldCheck } from 'lucide-react';
export default function GridOverview({ assets = [], status = {} }) {
  const counts = status.risk_counts ?? {};
  const items = [
    { label: 'Assets monitored', value: status.total_assets ?? assets.length, unit: 'transformers', change: `${status.assets_reporting ?? 0} reporting`, icon: Box, tone: 'blue' },
    { label: 'Average grid load', value: status.average_load_pct ?? '—', unit: '%', change: `${counts.HIGH ?? 0} high risk`, icon: Gauge, tone: 'violet', up: (counts.HIGH ?? 0) + (counts.CRITICAL ?? 0) > 0 },
    { label: 'Open alerts', value: status.active_alerts ?? 0, unit: 'need attention', change: `${counts.CRITICAL ?? 0} critical · ${counts.HIGH ?? 0} high`, icon: CircleAlert, tone: 'amber', up: (status.active_alerts ?? 0) > 0 },
    { label: 'Healthy assets', value: counts.LOW ?? 0, unit: 'low risk', change: `${(counts.MEDIUM ?? 0) + (counts.HIGH ?? 0) + (counts.CRITICAL ?? 0)} need review`, icon: ShieldCheck, tone: 'green' },
  ];
  return <div className="metric-grid">{items.map(({ label, value, unit, change, icon: Icon, tone, up }) => <article className="metric-card" key={label}><div className="metric-top"><span>{label}</span><span className={`metric-icon ${tone}`}><Icon size={17} /></span></div><div className="metric-value">{value}<small>{unit}</small></div><div className="metric-foot"><span className={up ? 'change-warn' : 'change-good'}>{up ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{change.split(' ')[0]}</span><span>{change.substring(change.indexOf(' ') + 1)}</span></div></article>)}</div>;
}
