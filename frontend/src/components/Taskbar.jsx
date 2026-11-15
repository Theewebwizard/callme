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
  User,
} from 'lucide-react';
import ThemeToggle from './ThemeToggle';

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
  const isHealthy = !health || health.status === 'healthy';

  const savedGoogleUser = (() => {
    try {
      return JSON.parse(localStorage.getItem('answerly_google_user') || localStorage.getItem('callme_google_user') || 'null');
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

  return (
    <>
      {/* ── Top Panel Header Navigation (Horizontal Architecture) ── */}
      <header className="workspace-top-panel" aria-label="Console Navigation Top Panel">
        {/* Row 1: Brand, Tenant Info, Actions, Profile, Theme Toggle */}
        <div className="top-panel-main-row">
          <div className="top-panel-left">
            {/* Platform Brand */}
            <div className="top-panel-brand" title="Answerly Autonomous Voice Platform">
              <div className="brand-icon">
                <PhoneCall size={16} strokeWidth={2.5} />
              </div>
              <div className="brand-text">
                Answer<span>ly</span>
              </div>
              <span className="brand-version-badge">v2.4</span>
            </div>

            <div className="top-panel-divider-v" />

            {/* Active Business Tenant Badge */}
            {business && (
              <div className="top-panel-tenant-card" title={`Active Tenant: ${business.name} (${business.industry || 'Restaurant'})`}>
                <div className="tenant-card-top">
                  <span className="tenant-card-name">{business.name}</span>
                  <span className={`tenant-status-pill ${isHealthy ? 'online' : 'standby'}`}>
                    <span className="status-dot" />
                    {isHealthy ? 'Online' : 'Standby'}
                  </span>
                </div>
                <div className="tenant-card-bottom">
                  <span className="tenant-card-industry">{business.industry || 'RESTAURANT'}</span>
                  <span className="tenant-card-phone">{business.phone_number || '+91 80 4123 5678'}</span>
                </div>
              </div>
            )}
          </div>

          {/* Right Action Controls */}
          <div className="top-panel-right">
            {/* Direct Inbound Call Action */}
            <button
              type="button"
              className="top-panel-call-btn"
              onClick={() => setActiveTab('webphone')}
              title="Dial direct inbound test call (WebRTC)"
            >
              <Phone size={13} />
              <span>Direct Inbound Call</span>
            </button>

            {/* User Profile Pill */}
            {savedGoogleUser && (
              <div className="top-panel-user-pill" title={`Logged in as ${savedGoogleUser.email}`}>
                <div className="user-avatar-circle">
                  {savedGoogleUser.avatarInitial || (business?.name ? business.name[0].toUpperCase() : 'H')}
                </div>
                <div className="user-info-text">
                  <span className="user-name">{savedGoogleUser.name || business?.name || 'Spice Garden Bistro'}</span>
                  <span className="user-email">{savedGoogleUser.email || 'haveli.restaurant@gmail.com'}</span>
                </div>
              </div>
            )}

            {/* Theme Toggle (Light / Dark) */}
            <div className="top-panel-theme-toggle">
              <ThemeToggle />
            </div>

            {/* Exit Workspace */}
            <button
              type="button"
              className="top-panel-exit-btn"
              onClick={onExitWorkspace}
              title="Exit Workspace & Return to Portal"
            >
              <LogOut size={13} />
              <span>Exit Workspace</span>
            </button>
          </div>
        </div>

        {/* Row 2: Horizontal Navigation Tabs & Telemetry */}
        <div className="top-panel-nav-row">
          <nav className="top-panel-nav-tabs" aria-label="Console Views">
            {NAV_GROUPS.map((group, gIdx) => (
              <div key={group.group} className="top-nav-group-section">
                <span className="top-nav-group-label">{group.group}</span>
                <div className="top-nav-group-pills">
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const isActive = activeTab === item.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        className={`top-nav-tab-btn ${isActive ? 'active' : ''}`}
                        onClick={() => {
                          setActiveTab(item.id);
                          setMobileMenuOpen(false);
                        }}
                        title={`${item.label} (${item.desc})`}
                      >
                        <Icon size={14} className="top-nav-icon" />
                        <span className="top-nav-label">{item.label}</span>
                      </button>
                    );
                  })}
                </div>
                {gIdx < NAV_GROUPS.length - 1 && <div className="top-nav-group-separator" />}
              </div>
            ))}
          </nav>

          {/* Live Line Status Indicator */}
          <div className="top-panel-telemetry">
            <div className="live-telemetry-badge">
              <span className="live-dot-pulse" />
              <span>LIVE LINE • RTT 280ms</span>
            </div>
          </div>
        </div>
      </header>

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
          <span style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {business?.name || 'Answerly Console'}
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
                <span style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.95rem' }}>Answerly Console</span>
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
              <div className="top-panel-tenant-card" style={{ marginBottom: '1.25rem' }}>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.85rem' }}>{business.name}</div>
                <div style={{ fontSize: '0.74rem', color: 'var(--text-tertiary)' }}>{business.industry} • {business.phone_number}</div>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {NAV_GROUPS.map((group) => (
                <div key={group.group}>
                  <div style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: '4px', letterSpacing: '0.04em' }}>
                    {group.group}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                    {group.items.map((item) => {
                      const Icon = item.icon;
                      const isActive = activeTab === item.id;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          className={`top-nav-tab-btn ${isActive ? 'active' : ''}`}
                          style={{ width: '100%', justifyContent: 'flex-start', padding: '8px 12px' }}
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

            <div style={{ marginTop: '2rem', borderTop: '1px solid var(--border-medium)', paddingTop: '1rem' }}>
              <div style={{ marginBottom: '0.75rem', display: 'flex', justifyContent: 'center' }}>
                <ThemeToggle />
              </div>
              <button
                type="button"
                className="top-panel-exit-btn"
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
