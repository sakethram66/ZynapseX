import { Activity, Bell, ChevronDown, Command, Search } from 'lucide-react';

const links = ['Overview', 'Assets', 'Alerts', 'Simulator'];

export default function Header({ page, setPage, alertCount = 0, onSearch, profileOpen, onToggleProfile }) {
  return <header className="topbar">
    <button className="brand" type="button" onClick={() => setPage('Overview')} aria-label="Go to overview"><span className="brand-mark"><Activity size={19} strokeWidth={2.7} /></span><span>ZYNAPSE<span className="brand-light">X</span></span></button>
    <nav className="main-nav" aria-label="Main navigation">{links.map(link => <button key={link} className={page === link ? 'nav-link active' : 'nav-link'} onClick={() => setPage(link)}>{link}{link === 'Alerts' && <span className="nav-count">{alertCount}</span>}</button>)}</nav>
    <div className="header-actions">
      <button className="icon-button search-button" type="button" aria-label="Search assets" onClick={onSearch}><Search size={18} /><span>Search assets</span><kbd><Command size={11} /> K</kbd></button>
      <button className="icon-button notification-button" type="button" aria-label={`Open alerts${alertCount ? ` (${alertCount})` : ''}`} onClick={() => setPage('Alerts')}><Bell size={18} />{alertCount > 0 && <i />}</button>
      <div className="header-divider" />
      <div className="profile-wrap">
        <button className="profile-button" type="button" aria-expanded={profileOpen} aria-haspopup="menu" onClick={onToggleProfile}><span className="avatar">S</span><span className="profile-text"><b>sakethram</b><small>Grid operator</small></span><ChevronDown size={15} /></button>
        {profileOpen && <div className="profile-menu" role="menu"><div className="profile-menu-heading"><b>sakethram</b><small>Grid operator</small></div>{links.map(link => <button role="menuitem" key={link} onClick={() => setPage(link)}>{link}{link === 'Alerts' && <span>{alertCount}</span>}</button>)}</div>}
      </div>
    </div>
  </header>;
}
