import React from 'react';
import {
  PhoneCall,
  LayoutDashboard,
  Settings,
  MessageSquare,
  Phone,
  History,
  Wrench,
  CheckCircle2,
  AlertCircle,
  Building2,
  LogOut,
} from 'lucide-react';

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

  return (
    <header className="taskbar">
      {/* Top Tier: Identity & Controls */}
      <div className="taskbar-top">
        {/* Brand & Isolated Business Identity */}
        <div className="taskbar-brand">
          <div className="brand-icon">
            <PhoneCall size={20} strokeWidth={2.5} />
          </div>
          <div className="brand-text">
            Call<span>Me</span>
          </div>

          {/* Isolated Active Tenant Badge */}
          {business && (
            <div className="tenant-badge">
              <Building2 size={14} color="var(--sky-600)" style={{ flexShrink: 0 }} />
              <strong className="tenant-name">{business.name}</strong>
              <span className="tenant-industry">
                {business.industry || 'Business'}
              </span>
              {business.phone_number && (
                <span className="tenant-phone">
                  • {business.phone_number}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Right Status & Controls */}
        <div className="taskbar-status">
          <div className={`status-badge ${isHealthy ? 'online' : 'offline'}`}>
            {isHealthy ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
            <span>{isHealthy ? 'Supabase Online' : 'Connecting...'}</span>
          </div>

          {savedGoogleUser && (
            <div className="google-user-pill" title={`Authenticated via Google: ${savedGoogleUser.email}`}>
              <div className="google-avatar-mini">
                {savedGoogleUser.avatarInitial || 'G'}
              </div>
              <span className="google-email">{savedGoogleUser.email}</span>
            </div>
          )}

          <button
            className="btn-quick-call"
            onClick={() => setActiveTab('webphone')}
            title="Direct Browser Voice Call"
          >
            <Phone size={14} />
            Direct Call
          </button>

          <button
            className="btn-secondary btn-exit"
            onClick={onExitWorkspace}
            title="Switch Business Workspace"
          >
            <LogOut size={14} />
            Exit
          </button>
        </div>
      </div>

      {/* Bottom Tier: Full-width Navigation Tabs */}
      <div className="taskbar-bottom">
        <nav className="taskbar-nav">
          <button
            className={`nav-pill ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            <LayoutDashboard size={15} />
            Overview
          </button>

          <button
            className={`nav-pill ${activeTab === 'setup' ? 'active' : ''}`}
            onClick={() => setActiveTab('setup')}
          >
            <Settings size={15} />
            Receptionist Setup
          </button>

          <button
            className={`nav-pill ${activeTab === 'playground' ? 'active' : ''}`}
            onClick={() => setActiveTab('playground')}
          >
            <MessageSquare size={15} />
            AI Playground
          </button>

          <button
            className={`nav-pill ${activeTab === 'webphone' ? 'active' : ''}`}
            onClick={() => setActiveTab('webphone')}
          >
            <Phone size={15} />
            Web Phone
          </button>

          <button
            className={`nav-pill ${activeTab === 'calls' ? 'active' : ''}`}
            onClick={() => setActiveTab('calls')}
          >
            <History size={15} />
            Call History
          </button>

          <button
            className={`nav-pill ${activeTab === 'tools' ? 'active' : ''}`}
            onClick={() => setActiveTab('tools')}
          >
            <Wrench size={15} />
            Tools & Demands
          </button>
        </nav>
      </div>
    </header>
  );
}
