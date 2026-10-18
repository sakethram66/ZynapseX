import { useCallback, useMemo, useState } from 'react';
import { ChevronRight, CircleHelp, Command, Settings2 } from 'lucide-react';
import Header from './components/Header';
import SystemStatus from './components/SystemStatus';
import Dashboard from './pages/Dashboard';
import AssetDetails from './pages/AssetDetails';
import Alerts from './pages/Alerts';
import Simulator from './pages/Simulator';
import useGridData from './hooks/useGridData';
import useWebSocket from './hooks/useWebSocket';

export default function App() {
  const [page, setPage] = useState('Overview');
  const [selectedAsset, setSelectedAsset] = useState(null);
  const data = useGridData();
  const onMessage = useCallback(data.handleMessage, [data.handleMessage]);
  const connected = useWebSocket(onMessage);
  const asset = useMemo(() => data.assets.find(a => a.id === selectedAsset?.id) ?? selectedAsset ?? data.assets[0], [selectedAsset, data.assets]);
  const selectAsset = item => { setSelectedAsset(item); setPage('Asset'); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  const navigate = next => { setPage(next); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  return <div className="app-shell">
    <Header page={page === 'Asset' ? 'Assets' : page} setPage={navigate} alertCount={data.alerts.length} />
    <SystemStatus system={data.system} connected={connected} />
    <main className="main-content">
      {data.error && <div className="panel" role="alert">Backend connection failed: {data.error}. Start the API and refresh this page.</div>}
      {data.loading && <div className="panel">Connecting to the grid backend…</div>}
      {!data.loading && !data.error && data.assets.length === 0 && <div className="panel">Waiting for the first simulator reading…</div>}
      {!data.loading && page === 'Asset' && asset ? <AssetDetails asset={asset} reading={data.readings[asset.id] ?? asset.latest_reading} risk={data.risks[asset.id]} history={data.histories[asset.id] ?? []} events={data.events.filter(event => event.asset_id === asset.id)} onBack={() => navigate('Overview')} />
        : page === 'Alerts' ? <Alerts alerts={data.alerts} />
        : page === 'Simulator' ? <Simulator assets={data.assets} histories={data.histories} />
        : page === 'Assets' ? <><div className="page-heading"><div><div className="breadcrumb">OPERATIONS <span>/</span> ASSETS</div><h1>Asset directory</h1><p>Monitor transformer health across your service territory.</p></div></div><div className="panel directory-panel">{data.assets.map(item => <button key={item.id} className="directory-row" onClick={() => selectAsset(item)}><span className={`asset-status ${item.status.toLowerCase()}`} /><span><b>{item.name}</b><small>{item.id} · {item.voltage} · {item.region}</small></span><span className="directory-health"><i><em style={{ width: `${item.health}%` }} /></i>{item.health}% health</span><span className={`risk-chip ${item.status.toLowerCase()}`}>{item.status}</span><ChevronRight size={16} /></button>)}</div></>
        : <Dashboard data={data} onSelectAsset={selectAsset} setPage={navigate} />}
    </main>
    <footer className="app-footer"><div><span className="footer-brand">Z</span><span>Grid intelligence platform</span><span className="footer-dot">·</span><span>Simulation mode</span></div><div className="footer-right"><span className={connected ? 'connection connected' : 'connection'}><i />{connected ? 'Connected to grid' : 'Stream disconnected'}</span><button><CircleHelp size={14} />Help center</button><button><Settings2 size={14} />Settings</button><button className="footer-shortcut"><Command size={12} />K</button></div></footer>
  </div>;
}
