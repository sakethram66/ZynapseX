import { ArrowDownRight, ArrowUpRight, Box, CircleAlert, Gauge, ShieldCheck } from 'lucide-react';
const items = [
  { label: 'Assets monitored', value: '24', unit: 'transformers', change: '2 added this month', icon: Box, tone: 'blue' },
  { label: 'Grid load', value: '72.4', unit: '%', change: '3.2% from yesterday', icon: Gauge, tone: 'violet', up: true },
  { label: 'Open alerts', value: '03', unit: 'need attention', change: '1 critical · 2 warning', icon: CircleAlert, tone: 'amber', up: true },
  { label: 'System health', value: '98.2', unit: '%', change: '0.8% this week', icon: ShieldCheck, tone: 'green' }
];
export default function GridOverview() { return <div className="metric-grid">{items.map(({ label, value, unit, change, icon: Icon, tone, up }) => <article className="metric-card" key={label}><div className="metric-top"><span>{label}</span><span className={`metric-icon ${tone}`}><Icon size={17} /></span></div><div className="metric-value">{value}<small>{unit}</small></div><div className="metric-foot"><span className={up ? 'change-warn' : 'change-good'}>{up ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{change.split(' ')[0]}</span><span>{change.substring(change.indexOf(' ') + 1)}</span></div></article>)}</div>; }
