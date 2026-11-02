import React, { useState, useEffect } from 'react';
import Taskbar from './components/Taskbar';
import LandingPage from './components/LandingPage';
import AdminPortal from './components/AdminPortal';
import Dashboard from './components/Dashboard';
import BusinessSetup from './components/BusinessSetup';
import Playground from './components/Playground';
import WebPhone from './components/WebPhone';
import CallHistory from './components/CallHistory';
import ToolLibrary from './components/ToolLibrary';
import { api } from './api';

export default function App() {
  const [role, setRole] = useState(null); // 'admin' | 'business' | null
  const [activeTab, setActiveTab] = useState('overview');
  const [activeBusiness, setActiveBusiness] = useState(null);
  const [health, setHealth] = useState(null);
  const [recentCalls, setRecentCalls] = useState([]);
  const [initialLoading, setInitialLoading] = useState(true);

  useEffect(() => {
    initApp();

    const handleUnauthorized = () => {
      localStorage.removeItem('callme_active_business_id');
      localStorage.removeItem('callme_role');
      localStorage.removeItem('callme_token');
      localStorage.removeItem('callme_google_user');
      setActiveBusiness(null);
      setRole(null);
    };

    window.addEventListener('callme:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('callme:unauthorized', handleUnauthorized);
  }, []);

  const initApp = async () => {
    try {
      // 1. Health check
      api.getHealth().then(setHealth).catch(() => {});

      // 2. Check saved role and tenant context
      const savedRole = localStorage.getItem('callme_role');
      const urlParams = new URLSearchParams(window.location.search);
      const urlBizId = urlParams.get('biz');
      const savedBizId = localStorage.getItem('callme_active_business_id');

      if (savedRole === 'admin' || urlParams.get('admin') === 'true') {
        setRole('admin');
        setInitialLoading(false);
        return;
      }

      const targetId = urlBizId || (savedRole === 'business' ? savedBizId : null);
      if (targetId) {
        const token = localStorage.getItem('callme_token');
        if (!token || !token.trim() || token === 'undefined' || token === 'null') {
          // Token is missing or invalid; clean session to require sign-in
          localStorage.removeItem('callme_active_business_id');
          localStorage.removeItem('callme_role');
          localStorage.removeItem('callme_token');
          setRole(null);
          setActiveBusiness(null);
        } else {
          try {
            const profile = await api.getBusiness(targetId);
            setActiveBusiness(profile);
            setRole('business');
            localStorage.setItem('callme_role', 'business');
            localStorage.setItem('callme_active_business_id', profile.id);
            loadCalls(profile.id);
          } catch {
            localStorage.removeItem('callme_active_business_id');
            localStorage.removeItem('callme_role');
            localStorage.removeItem('callme_token');
            setRole(null);
            setActiveBusiness(null);
          }
        }
      } else {
        // Clean start: initial page is stylish platform landing page
        setRole(null);
        setActiveBusiness(null);
      }
    } catch (err) {
      console.error('App init error:', err);
      setRole(null);
    } finally {
      setInitialLoading(false);
    }
  };

  const loadCalls = async (bizId) => {
    try {
      const res = await api.getCallHistory(bizId);
      setRecentCalls(res.calls || []);
    } catch (err) {
      console.error('Failed to load call history:', err);
    }
  };

  const handleEnterWorkspace = (biz) => {
    setActiveBusiness(biz);
    setRole('business');
    localStorage.setItem('callme_role', 'business');
    localStorage.setItem('callme_active_business_id', biz.id);
    setActiveTab('overview');
    loadCalls(biz.id);
  };

  const handleEnterAdmin = () => {
    setRole('admin');
    localStorage.setItem('callme_role', 'admin');
  };

  const handleExitAdmin = () => {
    localStorage.removeItem('callme_role');
    setRole(null);
  };

  const handleExitWorkspace = () => {
    localStorage.removeItem('callme_role');
    localStorage.removeItem('callme_active_business_id');
    localStorage.removeItem('callme_google_user');
    localStorage.removeItem('callme_token');
    setActiveBusiness(null);
    setRole(null);
  };

  if (initialLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-app)', color: 'var(--indigo-600)', fontWeight: 600 }}>
        Loading CallMe AI Receptionist Platform...
      </div>
    );
  }

  // View 1: Platform Operator / Admin Command Center (Strictly supervisory, zero tenant impersonation)
  if (role === 'admin') {
    return (
      <AdminPortal
        onExitAdmin={handleExitAdmin}
      />
    );
  }

  // View 2: Platform Landing Page with stylish platform overview & bottom Auth Section
  if (!activeBusiness || role !== 'business') {
    return (
      <LandingPage
        onEnterWorkspace={handleEnterWorkspace}
        onEnterAdmin={handleEnterAdmin}
      />
    );
  }

  // View 3: Strictly Isolated Business Person Workspace (Linear / Raycast Architecture)
  return (
    <div className="workspace-layout">
      {/* Sidebar Command Navigation */}
      <Taskbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        business={activeBusiness}
        onExitWorkspace={handleExitWorkspace}
        health={health}
      />

      {/* Main Business Viewport */}
      <div className="workspace-main">
        {/* Top Operational Command Bar */}
        <header className="workspace-topbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
              {activeBusiness.name}
            </span>
            <span style={{ color: 'var(--border-strong)', fontSize: '0.75rem' }}>/</span>
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              {activeTab === 'overview' && 'Cockpit'}
              {activeTab === 'setup' && 'Voice Persona & Knowledge'}
              {activeTab === 'playground' && 'AI Dialogue Simulator'}
              {activeTab === 'webphone' && 'Inbound Web Phone'}
              {activeTab === 'calls' && 'Audit Trail & Telemetry'}
              {activeTab === 'tools' && 'Capabilities & Inventory'}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {/* Live Operational Indicator */}
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                padding: '2px 8px',
                borderRadius: 'var(--radius-full)',
                background: 'rgba(16, 185, 129, 0.08)',
                border: '1px solid rgba(16, 185, 129, 0.25)',
                fontSize: '0.7rem',
                color: 'var(--mint-400)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: 'var(--mint-400)' }} />
              <span>LIVE LINE • RTT 280ms</span>
            </div>

            {/* Quick Inbound Test Call Action */}
            <button
              type="button"
              className="btn-primary"
              style={{ padding: '0.3rem 0.75rem', fontSize: '0.76rem' }}
              onClick={() => setActiveTab('webphone')}
            >
              <span>Test Inbound Call</span>
            </button>
          </div>
        </header>

        {/* Viewport Content */}
        <main className="workspace-content">
          {activeTab === 'overview' && (
            <Dashboard
              business={activeBusiness}
              calls={recentCalls}
              onNavigate={(tab) => setActiveTab(tab)}
            />
          )}

          {activeTab === 'setup' && (
            <BusinessSetup
              business={activeBusiness}
              onBusinessSaved={(updated) => {
                setActiveBusiness(updated);
              }}
            />
          )}

          {activeTab === 'playground' && (
            <Playground business={activeBusiness} />
          )}

          {activeTab === 'webphone' && (
            <WebPhone business={activeBusiness} />
          )}

          {activeTab === 'calls' && (
            <CallHistory
              business={activeBusiness}
              initialCalls={recentCalls}
              onCallsUpdated={setRecentCalls}
            />
          )}

          {activeTab === 'tools' && (
            <ToolLibrary business={activeBusiness} />
          )}
        </main>
      </div>
    </div>
  );
}
