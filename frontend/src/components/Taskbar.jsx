import React, { useState, useEffect } from 'react';
import {
  PhoneCall,
  LayoutDashboard,
  Sliders,
  Terminal,
  Phone,
  History,
  Boxes,
  LogOut,
  Radio,
  AlertCircle,
  Menu,
  X,
  ChevronRight,
  Sparkles,
  Zap,
  Building2,
  Calendar,
  ShieldCheck,
} from 'lucide-react';
import InstallAppPrompt from './InstallAppPrompt';

export const NAV_GROUPS = [
  {
    group: 'Operations',
    items: [
      { id: 'overview', label: 'Cockpit', shortcut: '1', icon: LayoutDashboard, desc: 'Operational dashboard & telemetry' },
      { id: 'calls', label: 'Audit Trail', shortcut: '5', icon: History, desc: 'Call logs & acoustic transcripts' },
    ],
  },
  {
    group: 'Voice Agent',
    items: [
      { id: 'setup', label: 'Voice Persona', shortcut: '2', icon: Sliders, desc: 'Greeting, schedule & knowledge base' },
      { id: 'tools', label: 'Capabilities', shortcut: '6', icon: Boxes, desc: 'Autonomous tool registry & inventory' },
    ],
  },
  {
    group: 'Testing & Labs',
    items: [
      { id: 'playground', label: 'Simulator', shortcut: '3', icon: Terminal, desc: 'AI conversation workbench' },
      { id: 'webphone', label: 'Web Phone', shortcut: '4', icon: Phone, desc: 'Inbound WebRTC voice dialer' },
    ],
  },
];

export const FLAT_NAV_ITEMS = NAV_GROUPS.flatMap((g) => g.items);

export default function Taskbar({
  activeTab,
  setActiveTab,
  business,
  onExitWorkspace,
  health,
}) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const isHealthy = health && health.status === 'healthy';

  const savedGoogleUser = (() => {
    try {
      return JSON.parse(localStorage.getItem('callme_google_user') || 'null');
    } catch {
      return null;
    }
  })();

  // Keyboard navigation accelerators (1-6)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
        return;
      }
      const match = FLAT_NAV_ITEMS.find((item) => item.shortcut === e.key);
      if (match) {
        e.preventDefault();
        setActiveTab(match.id);
        setMobileMenuOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setActiveTab]);

  const activeItem = FLAT_NAV_ITEMS.find((i) => i.id === activeTab) || FLAT_NAV_ITEMS[0];

  return (
    <>
      {/* ── Desktop & Tablet Sidebar (Linear / Raycast Architecture) ── */}
      <aside className="workspace-sidebar" aria-label="Console Navigation Sidebar">
        {/* 1. Header: Platform Brand & Version */}
        <div className="sidebar-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div className="brand-icon" title="CallMe Autonomous Voice Platform">
              <PhoneCall size={16} strokeWidth={2.5} />
            </div>
            <div className="brand-text">
              Call<span>Me</span>
            </div>
            <span
              style={{
                fontSize: '0.68rem',
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-tertiary)',
                background: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid var(--border-subtle)',
                padding: '1px 5px',
                borderRadius: '4px',
                marginLeft: 'auto',
              }}
            >
              v2.4
            </span>
          </div>

          {/* 2. Business Tenant Context Card */}
          {business && (
            <div className="sidebar-tenant-card" title={`Active Tenant: ${business.name} (${business.industry})`}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span className="sidebar-tenant-name">{business.name}</span>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontSize: '0.68rem',
                    fontFamily: 'var(--font-mono)',
                    color: isHealthy ? 'var(--mint-400)' : 'var(--amber-500)',
                  }}
                >
                  <span
                    style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      background: isHealthy ? 'var(--mint-500)' : 'var(--amber-500)',
                      boxShadow: isHealthy ? '0 0 6px rgba(16, 185, 129, 0.7)' : 'none',
                    }}
                  />
                  {isHealthy ? 'Online' : 'Standby'}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                <span style={{ textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  {business.industry || 'Business'}
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {business.phone_number || 'DID Unassigned'}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* 3. Grouped Navigation Items */}
        <nav className="sidebar-nav-groups" aria-label="Console Views">
          {NAV_GROUPS.map((group) => (
            <div key={group.group} className="sidebar-group">
              <div className="sidebar-group-title">{group.group}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = activeTab === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`sidebar-nav-item ${isActive ? 'active' : ''}`}
                      onClick={() => {
                        setActiveTab(item.id);
                        setMobileMenuOpen(false);
                      }}
                      title={`${item.label} (${item.desc}) — Press ${item.shortcut}`}
                    >
                      <Icon size={15} className="sidebar-nav-icon" />
                      <span className="sidebar-nav-label">{item.label}</span>
                      <kbd className="sidebar-kbd">{item.shortcut}</kbd>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* 4. Sidebar Footer: Actions & Account */}
        <div className="sidebar-footer">
          {/* Quick Direct Inbound Call Button */}
          <button
            type="button"
            className="sidebar-call-btn"
            onClick={() => setActiveTab('webphone')}
            title="Dial direct inbound test call (WebRTC)"
          >
            <Phone size={14} />
            <span>Direct Inbound Call</span>
          </button>

          {/* User Profile Pill */}
          {savedGoogleUser && (
            <div className="sidebar-user-pill" title={`Logged in as ${savedGoogleUser.email}`}>
              <div className="sidebar-avatar">
                {savedGoogleUser.avatarInitial || 'G'}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                <span className="sidebar-user-name">{savedGoogleUser.name || 'Business Owner'}</span>
                <span className="sidebar-user-email">{savedGoogleUser.email}</span>
              </div>
            </div>
          )}

          {/* Exit Workspace */}
          <button
            type="button"
            className="sidebar-exit-btn"
            onClick={onExitWorkspace}
            title="Exit Workspace & Return to Portal"
          >
            <LogOut size={13} />
            <span>Exit Workspace</span>
          </button>
        </div>
      </aside>

      {/* ── Mobile Top Header (Screens < 900px) ── */}
      <header className="workspace-mobile-header">
        <button
          type="button"
          className="mobile-menu-toggle"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Toggle navigation menu"
        >
          {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div className="brand-icon" style={{ width: 22, height: 22 }}>
            <PhoneCall size={12} strokeWidth={2.5} />
          </div>
          <span style={{ fontSize: '0.88rem', fontWeight: 700, color: '#ffffff' }}>
            {business?.name || 'CallMe Console'}
          </span>
        </div>

        <button
          type="button"
          className="btn-quick-call"
          style={{ padding: '0.25rem 0.55rem', fontSize: '0.74rem' }}
          onClick={() => setActiveTab('webphone')}
        >
          <Phone size={12} />
          <span>Call</span>
        </button>
      </header>

      {/* Mobile Drawer Overlay */}
      {mobileMenuOpen && (
        <div
          className="mobile-drawer-backdrop"
          onClick={() => setMobileMenuOpen(false)}
        >
          <div
            className="mobile-drawer-content"
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div className="brand-icon" style={{ width: 24, height: 24 }}>
                  <PhoneCall size={14} />
                </div>
                <span style={{ fontWeight: 700, color: '#ffffff', fontSize: '0.95rem' }}>CallMe Console</span>
              </div>
              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            {business && (
              <div className="sidebar-tenant-card" style={{ marginBottom: '1.25rem' }}>
                <div style={{ fontWeight: 600, color: '#ffffff', fontSize: '0.85rem' }}>{business.name}</div>
                <div style={{ fontSize: '0.74rem', color: 'var(--text-tertiary)' }}>{business.industry} • {business.phone_number}</div>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {NAV_GROUPS.map((group) => (
                <div key={group.group}>
                  <div className="sidebar-group-title">{group.group}</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                    {group.items.map((item) => {
                      const Icon = item.icon;
                      const isActive = activeTab === item.id;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          className={`sidebar-nav-item ${isActive ? 'active' : ''}`}
                          onClick={() => {
                            setActiveTab(item.id);
                            setMobileMenuOpen(false);
                          }}
                        >
                          <Icon size={16} />
                          <span>{item.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ marginTop: '2rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
              <button
                type="button"
                className="sidebar-exit-btn"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => {
                  setMobileMenuOpen(false);
                  onExitWorkspace();
                }}
              >
                <LogOut size={14} />
                <span>Exit Workspace</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
