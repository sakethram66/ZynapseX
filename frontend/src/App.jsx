import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronRight, CircleHelp, Command, Search, Settings2, X } from 'lucide-react';
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
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [profileOpen, setProfileOpen] = useState(false);
  const searchInput = useRef(null);
  const data = useGridData();
  const onMessage = useCallback(data.handleMessage, [data.handleMessage]);
  const connection = useWebSocket(onMessage);
  const connected = connection === 'connected';
  const asset = useMemo(() => data.assets.find(a => a.id === selectedAsset?.id) ?? selectedAsset ?? data.assets[0], [selectedAsset, data.assets]);
  const selectAsset = item => { setSelectedAsset(item); setPage('Asset'); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  const navigate = next => { setPage(next); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  const openSearch = () => { setProfileOpen(false); setSearchTerm(''); setSearchOpen(true); };
  useEffect(() => {
    const onKeyDown = event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openSearch(); }
      if (event.key === 'Escape') { setSearchOpen(false); setProfileOpen(false); }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
  useEffect(() => { if (searchOpen) searchInput.current?.focus(); }, [searchOpen]);
  const searchResults = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return data.assets.filter(item => !term || [item.id, item.name, item.region, item.voltage].some(value => String(value ?? '').toLowerCase().includes(term))).slice(0, 8);
  }, [data.assets, searchTerm]);
  return <div className="app-shell">
    <Header page={page === 'Asset' ? 'Assets' : page} setPage={next => { setProfileOpen(false); navigate(next); }} alertCount={data.alerts.length} onSearch={openSearch} profileOpen={profileOpen} onToggleProfile={() => setProfileOpen(value => !value)} />
    <SystemStatus system={data.system} connection={connection} />
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
    <footer className="app-footer"><div><span className="footer-brand">Z</span><span>Grid intelligence platform</span><span className="footer-dot">·</span><span>Simulation mode</span></div><div className="footer-right"><span className={connected ? 'connection connected' : 'connection'}><i />{connected ? 'Connected to grid' : connection === 'connecting' ? 'Connecting to grid' : 'Stream disconnected'}</span><button type="button" onClick={openSearch}><CircleHelp size={14} />Help center</button><button type="button" onClick={() => navigate('Simulator')}><Settings2 size={14} />Settings</button><button type="button" className="footer-shortcut" onClick={openSearch} aria-label="Open search"><Command size={12} />K</button></div></footer>
    {searchOpen && <div className="search-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setSearchOpen(false); }}><section className="search-dialog" role="dialog" aria-modal="true" aria-label="Search grid assets"><div className="search-dialog-input"><Search size={19} /><input ref={searchInput} value={searchTerm} onChange={event => setSearchTerm(event.target.value)} placeholder="Search by asset, ID, region…" aria-label="Search assets" /><button type="button" aria-label="Close search" onClick={() => setSearchOpen(false)}><X size={18} /></button></div><div className="search-results">{searchResults.length ? searchResults.map(item => <button type="button" className="search-result" key={item.id} onClick={() => { setSearchOpen(false); selectAsset(item); }}><span className="search-result-icon"><Search size={15} /></span><span><b>{item.name}</b><small>{item.id} · {item.region ?? 'Grid asset'}</small></span><ChevronRight size={16} /></button>) : <p className="search-empty">No matching assets found.</p>}</div><div className="search-dialog-foot">{data.assets.length} assets <span>ESC to close</span></div></section></div>}
  </div>;
}
