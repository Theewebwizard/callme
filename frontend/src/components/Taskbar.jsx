import React, { useEffect } from 'react';
import {
  PhoneCall,
  LayoutDashboard,
  Sliders,
  Terminal,
  Phone,
  History,
  Boxes,
  Building2,
  LogOut,
  Radio,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import InstallAppPrompt from './InstallAppPrompt';

const NAV_ITEMS = [
  { id: 'overview', label: 'Cockpit', shortcut: '1', icon: LayoutDashboard },
  { id: 'setup', label: 'Voice Persona', shortcut: '2', icon: Sliders },
  { id: 'playground', label: 'Simulator', shortcut: '3', icon: Terminal },
  { id: 'webphone', label: 'Web Phone', shortcut: '4', icon: Phone },
  { id: 'calls', label: 'Audit Trail', shortcut: '5', icon: History },
  { id: 'tools', label: 'Capabilities', shortcut: '6', icon: Boxes },
];

export default function Taskbar({
  activeTab,
  setActiveTab,
  business,
  onExitWorkspace,
  health,
}) {
  const isHealthy = health && health.status === 'healthy';

  const savedGoogleUser = (() => {
    try {
      return JSON.parse(localStorage.getItem('callme_google_user') || 'null');
    } catch {
      return null;
    }
  })();

  // Raycast-style keyboard navigation (1-6) when not focused on an input
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
        return;
      }
      const match = NAV_ITEMS.find((item) => item.shortcut === e.key);
      if (match) {
        e.preventDefault();
        setActiveTab(match.id);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setActiveTab]);

  return (
    <header className="taskbar" role="banner">
      {/* Top Tier: Brand Identity, Live Telephony Capsule, Status & Controls */}
      <div className="taskbar-top">
        {/* Left: Brand + Active Business Capsule */}
        <div className="taskbar-brand">
          <div className="brand-icon" title="CallMe Autonomous Voice Platform">
            <PhoneCall size={16} strokeWidth={2.5} />
          </div>
          <div className="brand-text">
            Call<span>Me</span>
          </div>

          {business && (
            <div className="tenant-badge" title={`Active Tenant: ${business.name} (${business.industry})`}>
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  background: 'var(--mint-500)',
                  boxShadow: '0 0 6px rgba(16, 185, 129, 0.6)',
                  display: 'inline-block',
                }}
              />
              <strong className="tenant-name">{business.name}</strong>
              <span className="tenant-industry">[{business.industry || 'Business'}]</span>
              {business.phone_number && (
                <span className="tenant-phone">
                  {business.phone_number}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Center: Command Dock Segmented Navigation */}
        <nav className="taskbar-nav" role="navigation" aria-label="Workspace Command Dock">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                className={`nav-pill ${isActive ? 'active' : ''}`}
                onClick={() => setActiveTab(item.id)}
                title={`${item.label} (Press ${item.shortcut})`}
              >
                <Icon size={14} />
                <span>{item.label}</span>
                <kbd>{item.shortcut}</kbd>
              </button>
            );
          })}
        </nav>

        {/* Right: Telephony Status & User Controls */}
        <div className="taskbar-status">
          <div
            className={`status-badge ${isHealthy ? 'online' : 'offline'}`}
            title={isHealthy ? 'Inbound Voice Telephony Engine Operational' : 'Connecting to Voice Gateway...'}
          >
            {isHealthy ? (
              <Radio size={12} className="animate-pulse" />
            ) : (
              <AlertCircle size={12} />
            )}
            <span>{isHealthy ? 'Live Line' : 'Connecting'}</span>
          </div>

          {savedGoogleUser && (
            <div className="google-user-pill" title={`Logged in as ${savedGoogleUser.email}`}>
              <div className="google-avatar-mini">
                {savedGoogleUser.avatarInitial || 'G'}
              </div>
              <span className="google-email">{savedGoogleUser.email}</span>
            </div>
          )}

          <InstallAppPrompt />

          <button
            type="button"
            className="btn-quick-call"
            onClick={() => setActiveTab('webphone')}
            title="Dial direct inbound test call (Browser WebRTC)"
          >
            <Phone size={13} />
            <span>Direct Call</span>
          </button>

          <button
            type="button"
            className="btn-exit"
            onClick={onExitWorkspace}
            title="Exit Workspace & Return to Portal"
          >
            <LogOut size={13} />
            <span>Exit</span>
          </button>
        </div>
      </div>
    </header>
  );
}
