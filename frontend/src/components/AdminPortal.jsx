import React, { useState, useEffect } from 'react';
import ThemeToggle from './ThemeToggle';
import {
  ShieldCheck,
  Users,
  Wrench,
  Sparkles,
  PhoneCall,
  Phone,
  Clock,
  CheckCircle2,
  AlertCircle,
  Eye,
  LogOut,
  Layers,
  ArrowRight,
  TrendingUp,
  Activity,
  Bot,
  X,
  Server,
  Zap,
} from 'lucide-react';
import { api } from '../api';

export default function AdminPortal({ onExitAdmin }) {
  const [adminTab, setAdminTab] = useState('live_agents'); // 'live_agents' | 'users' | 'tools' | 'demands'
  const [overview, setOverview] = useState(null);
  const [toolsRepo, setToolsRepo] = useState(null);
  const [demands, setDemands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgentDetail, setSelectedAgentDetail] = useState(null);
  const [feedback, setFeedback] = useState(null);

  useEffect(() => {
    loadAdminData();
  }, []);

  const loadAdminData = async () => {
    setLoading(true);
    try {
      const [ovData, toolsData, demandsData] = await Promise.all([
        api.getAdminOverview(),
        api.getAdminTools(),
        api.getAdminDemands(),
      ]);
      setOverview(ovData);
      setToolsRepo(toolsData);
      setDemands(demandsData);
    } catch (err) {
      console.error('Failed to load admin data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateDemandStatus = async (demandId, newStatus) => {
    try {
      await api.updateAdminDemandStatus(demandId, newStatus);
      setDemands((prev) =>
        prev.map((d) => (d.id === demandId ? { ...d, status: newStatus } : d))
      );
      setFeedback({ type: 'success', text: `Status updated to "${newStatus}"` });
      setTimeout(() => setFeedback(null), 3000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to update status: ${err.message}` });
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-app)', display: 'flex', flexDirection: 'column' }}>
      {/* Admin Dedicated Command Dock / Taskbar */}
      <header className="taskbar">
        <div className="taskbar-top">
          <div className="taskbar-brand">
            <div className="brand-icon" style={{ background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(16, 185, 129, 0.05))', color: 'var(--color-emerald)', borderColor: 'rgba(16, 185, 129, 0.3)' }}>
              <ShieldCheck size={20} strokeWidth={2.5} />
            </div>
            <div>
              <div className="brand-text" style={{ fontSize: '1.05rem', letterSpacing: '-0.02em' }}>
                Call<span style={{ color: 'var(--color-emerald)' }}>Me</span> <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Admin Fleet</span>
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontWeight: 600, letterSpacing: '0.02em' }}>
                Operator Telemetry & Fleet Oversight
              </div>
            </div>
          </div>

          {/* Right Exit & Status Pill */}
          <div className="taskbar-status">
            <span style={{
              fontSize: '0.74rem',
              background: 'rgba(16, 185, 129, 0.08)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              color: 'var(--color-emerald)',
              padding: '0.3rem 0.75rem',
              borderRadius: 'var(--radius-full)',
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--color-emerald)', display: 'inline-block' }}></span>
              Superuser Mode Active
            </span>
            <ThemeToggle />
            <button
              className="btn-secondary"
              style={{ padding: '0.35rem 0.85rem', fontSize: '0.8rem', borderRadius: 'var(--radius-md)' }}
              onClick={onExitAdmin}
            >
              <LogOut size={13} /> Exit Admin
            </button>
          </div>
        </div>

        {/* Bottom Tier: Admin Navigation */}
        <div className="taskbar-bottom">
          <nav className="taskbar-nav">
            <button
              className={`nav-pill ${adminTab === 'live_agents' ? 'active' : ''}`}
              onClick={() => setAdminTab('live_agents')}
            >
              <Activity size={14} /> Live Agents Fleet
            </button>

            <button
              className={`nav-pill ${adminTab === 'users' ? 'active' : ''}`}
              onClick={() => setAdminTab('users')}
            >
              <Users size={14} /> Registered Tenants
            </button>

            <button
              className={`nav-pill ${adminTab === 'tools' ? 'active' : ''}`}
              onClick={() => setAdminTab('tools')}
            >
              <Wrench size={14} /> Canonical Tool Catalog
            </button>

            <button
              className={`nav-pill ${adminTab === 'demands' ? 'active' : ''}`}
              onClick={() => setAdminTab('demands')}
            >
              <Sparkles size={14} /> Demanded Capabilities
              {demands.length > 0 && (
                <span style={{
                  marginLeft: '4px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  padding: '1px 6px',
                  borderRadius: '10px',
                  fontSize: '0.7rem',
                  fontWeight: 700,
                }}>
                  {demands.length}
                </span>
              )}
            </button>
          </nav>
        </div>
      </header>

      {/* Main Admin Content */}
      <main className="main-content" style={{ flex: 1, padding: '1.75rem' }}>
        {feedback && (
          <div
            style={{
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius-md)',
              marginBottom: '1.25rem',
              background: feedback.type === 'success' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(244, 63, 94, 0.12)',
              border: `1px solid ${feedback.type === 'success' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
              color: feedback.type === 'success' ? 'var(--color-emerald)' : 'var(--color-rose)',
              fontSize: '0.85rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            {feedback.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            {feedback.text}
          </div>
        )}

        {/* Security Isolation Banner (Raycast Obsidian Card) */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.85rem',
          background: 'rgba(16, 185, 129, 0.04)',
          border: '1px solid rgba(16, 185, 129, 0.18)',
          padding: '0.85rem 1.25rem',
          borderRadius: 'var(--radius-lg)',
          marginBottom: '1.75rem',
          fontSize: '0.82rem',
          color: 'var(--text-secondary)',
          boxShadow: 'var(--shadow-card)',
        }}>
          <div style={{
            width: '32px',
            height: '32px',
            borderRadius: 'var(--radius-sm)',
            background: 'rgba(16, 185, 129, 0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--color-emerald)',
            flexShrink: 0,
          }}>
            <ShieldCheck size={18} />
          </div>
          <span style={{ lineHeight: 1.5 }}>
            <strong style={{ color: 'var(--text-primary)' }}>Cryptographic Tenant Isolation Active:</strong> Platform operator oversight is strictly read-only for telemetry, runtime health, and canonical tool governance. Operators cannot authenticate as or impersonate tenant accounts, preserving confidentiality of guest dialogues and reservations.
          </span>
        </div>

        {/* High-level Platform KPIs */}
        {overview && (
          <div className="stat-grid" style={{ marginBottom: '2rem' }}>
            <div className="stat-card">
              <div>
                <div className="stat-label">Active Receptionists Fleet</div>
                <div className="stat-value">{overview.total_agents}</div>
              </div>
              <div className="stat-icon">
                <Bot size={20} />
              </div>
            </div>

            <div className="stat-card">
              <div>
                <div className="stat-label">Total Calls Autonomous Resolution</div>
                <div className="stat-value" style={{ color: 'var(--text-primary)' }}>
                  {overview.total_calls}
                </div>
              </div>
              <div className="stat-icon" style={{ background: 'rgba(255, 255, 255, 0.06)', color: 'var(--text-primary)' }}>
                <PhoneCall size={20} />
              </div>
            </div>

            <div className="stat-card">
              <div>
                <div className="stat-label">Provisioned Inbound DIDs</div>
                <div className="stat-value" style={{ color: 'var(--color-emerald)' }}>
                  {overview.active_phone_lines}
                </div>
              </div>
              <div className="stat-icon" style={{ background: 'rgba(16, 185, 129, 0.12)', color: 'var(--color-emerald)' }}>
                <Activity size={20} />
              </div>
            </div>

            <div className="stat-card">
              <div>
                <div className="stat-label">Feature Pipeline Demands</div>
                <div className="stat-value" style={{ color: 'var(--color-amber)' }}>
                  {overview.total_demands}
                </div>
              </div>
              <div className="stat-icon" style={{ background: 'rgba(245, 158, 11, 0.12)', color: 'var(--color-amber)' }}>
                <Sparkles size={20} />
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
           TAB 1: LIVE AGENTS FLEET OVERVIEW
           ========================================================================= */}
        {adminTab === 'live_agents' && overview && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{
              padding: '1.25rem 1.5rem',
              borderBottom: '1px solid var(--border-medium)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              <div>
                <div className="card-title" style={{ fontSize: '1rem', marginBottom: '2px' }}>Live Receptionist Agents Fleet</div>
                <div className="card-desc" style={{ marginBottom: 0, fontSize: '0.8rem' }}>
                  Real-time operational status, inbound telephony bindings, and conversation metrics across all registered accounts.
                </div>
              </div>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                {overview.agents.length} AGENTS REGISTERED
              </span>
            </div>

            <div className="table-wrapper" style={{ border: 'none' }}>
              <table className="modern-table">
                <thead>
                  <tr>
                    <th>Business Agent</th>
                    <th>Industry</th>
                    <th>Inbound Phone Line</th>
                    <th>Line Status</th>
                    <th>Operating Schedule</th>
                    <th>Total Calls</th>
                    <th>Tools Active</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.agents.map((ag) => {
                    const activeToolsCount = Object.values(ag.enabled_tools || {}).filter(Boolean).length;
                    return (
                      <tr key={ag.id}>
                        <td>
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{ag.name}</div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                            id: {ag.id}
                          </div>
                        </td>
                        <td>
                          <span style={{
                            background: 'rgba(255, 255, 255, 0.05)',
                            color: 'var(--text-secondary)',
                            border: '1px solid var(--border-medium)',
                            padding: '3px 8px',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                          }}>
                            {ag.industry}
                          </span>
                        </td>
                        <td>
                          <code style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.78rem',
                            color: 'var(--color-mint)',
                            background: 'rgba(16, 185, 129, 0.06)',
                            padding: '3px 7px',
                            borderRadius: '4px',
                            border: '1px solid rgba(16, 185, 129, 0.15)',
                          }}>
                            {ag.phone_number || 'Unassigned'}
                          </code>
                        </td>
                        <td>
                          <span style={{
                            color: 'var(--color-emerald)',
                            background: 'rgba(16, 185, 129, 0.1)',
                            border: '1px solid rgba(16, 185, 129, 0.25)',
                            padding: '3px 8px',
                            borderRadius: 'var(--radius-full)',
                            fontSize: '0.74rem',
                            fontWeight: 600,
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}>
                            <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: 'var(--color-emerald)' }}></span>
                            {ag.assigned_number_status}
                          </span>
                        </td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                          {ag.opening_time} – {ag.closing_time}
                        </td>
                        <td>
                          <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                            {ag.stats?.total_calls || 0}
                          </strong>
                        </td>
                        <td>
                          <span style={{
                            background: 'var(--bg-surface-elevated)',
                            color: 'var(--text-secondary)',
                            border: '1px solid var(--border-medium)',
                            padding: '3px 8px',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                          }}>
                            {activeToolsCount} active
                          </span>
                        </td>
                        <td>
                          <button
                            className="btn-secondary"
                            style={{ padding: '0.3rem 0.65rem', fontSize: '0.76rem' }}
                            onClick={() => setSelectedAgentDetail(ag)}
                          >
                            <Eye size={12} /> Inspect
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* =========================================================================
           TAB 2: USERS & REGISTERED AGENTS DIRECTORY
           ========================================================================= */}
        {adminTab === 'users' && overview && (
          <div>
            <div className="section-header" style={{ marginBottom: '1.5rem' }}>
              <h2 className="section-title" style={{ fontSize: '1.25rem' }}>Tenant Directory & Persona Profiles</h2>
              <p className="section-subtitle">
                Isolated receptionist configurations, greeting patterns, and telephony bindings for each registered business.
              </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem' }}>
              {overview.agents.map((ag) => (
                <div key={ag.id} className="card" style={{ display: 'flex', flexDirection: 'column' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.85rem' }}>
                    <div>
                      <div style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {ag.name}
                      </div>
                      <div style={{ fontSize: '0.76rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
                        tenant: {ag.id}
                      </div>
                    </div>
                    <span style={{
                      background: 'rgba(255, 255, 255, 0.05)',
                      color: 'var(--text-secondary)',
                      border: '1px solid var(--border-medium)',
                      padding: '3px 8px',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.74rem',
                      fontWeight: 600,
                    }}>
                      {ag.industry}
                    </span>
                  </div>

                  <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '0.85rem', lineHeight: 1.5, flex: 1 }}>
                    {ag.description || 'No business description provided.'}
                  </div>

                  <div style={{
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-medium)',
                    padding: '0.75rem',
                    borderRadius: 'var(--radius-md)',
                    marginBottom: '1rem',
                    fontSize: '0.8rem',
                  }}>
                    <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }}>
                      Inbound Voice Greeting:
                    </div>
                    <div style={{ color: 'var(--text-primary)', fontStyle: 'italic', lineHeight: 1.45 }}>
                      "{ag.greeting_message}"
                    </div>
                  </div>

                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    borderTop: '1px solid var(--border-medium)',
                    paddingTop: '0.75rem',
                    fontSize: '0.78rem',
                    color: 'var(--text-tertiary)',
                  }}>
                    <span>Line: <strong style={{ color: 'var(--color-mint)', fontFamily: 'var(--font-mono)' }}>{ag.phone_number}</strong></span>
                    <span style={{
                      fontSize: '0.72rem',
                      color: 'var(--text-tertiary)',
                      background: 'rgba(255, 255, 255, 0.04)',
                      padding: '3px 7px',
                      borderRadius: '4px',
                      fontWeight: 600,
                    }}>
                      🔒 Read-Only Oversight
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* =========================================================================
           TAB 3: MASTER TOOL REPOSITORY & AGENT USAGE
           ========================================================================= */}
        {adminTab === 'tools' && toolsRepo && (
          <div>
            <div className="section-header" style={{ marginBottom: '1.5rem' }}>
              <h2 className="section-title" style={{ fontSize: '1.25rem' }}>Master Canonical Tools Repository</h2>
              <p className="section-subtitle">
                Complete catalog of conversational function-calling tools available on the platform and current adoption across tenants.
              </p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {toolsRepo.tools.map((t) => (
                <div key={t.id} className="card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', marginBottom: '0.75rem' }}>
                    <div style={{ display: 'flex', gap: '0.85rem', alignItems: 'center' }}>
                      <div style={{
                        width: '38px',
                        height: '38px',
                        borderRadius: 'var(--radius-md)',
                        background: 'rgba(255, 255, 255, 0.04)',
                        border: '1px solid var(--border-medium)',
                        color: 'var(--text-primary)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}>
                        <Wrench size={18} />
                      </div>
                      <div>
                        <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                          {t.name} <code style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontWeight: 400 }}>({t.id})</code>
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                          Category: <span style={{ color: 'var(--text-secondary)' }}>{t.category}</span> • Adoption Rate: <strong style={{ color: 'var(--color-emerald)' }}>{t.adoption_rate}</strong> ({t.active_agents_count} of {t.total_agents_count} tenants)
                        </div>
                        <div style={{ marginTop: '6px', display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                          <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-tertiary)' }}>Eligible:</span>
                          {t.is_universal ? (
                            <span style={{
                              background: 'rgba(16, 185, 129, 0.08)',
                              color: 'var(--color-emerald)',
                              border: '1px solid rgba(16, 185, 129, 0.25)',
                              padding: '1px 7px',
                              borderRadius: 'var(--radius-full)',
                              fontSize: '0.7rem',
                              fontWeight: 600,
                            }}>
                              Universal (All Industries)
                            </span>
                          ) : (
                            (t.allowed_industries || []).map((ind, idx) => (
                              <span key={idx} style={{
                                background: 'rgba(255, 255, 255, 0.04)',
                                color: 'var(--text-secondary)',
                                border: '1px solid var(--border-medium)',
                                padding: '1px 7px',
                                borderRadius: 'var(--radius-full)',
                                fontSize: '0.7rem',
                                fontWeight: 600,
                              }}>
                                {ind}
                              </span>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginBottom: '1rem', lineHeight: 1.5 }}>
                    {t.description}
                  </div>

                  {/* Agent Usage Breakdown */}
                  <div style={{
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-medium)',
                    borderRadius: 'var(--radius-md)',
                    padding: '0.85rem 1rem',
                  }}>
                    <div style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-tertiary)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Tenant Activation Status:
                    </div>

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                      {t.agent_usage.map((u) => (
                        <div
                          key={u.business_id}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.35rem',
                            padding: '4px 10px',
                            borderRadius: 'var(--radius-full)',
                            fontSize: '0.76rem',
                            fontWeight: 600,
                            background: u.is_enabled ? 'rgba(16, 185, 129, 0.1)' : 'rgba(255, 255, 255, 0.03)',
                            color: u.is_enabled ? 'var(--color-emerald)' : 'var(--text-tertiary)',
                            border: u.is_enabled ? '1px solid rgba(16, 185, 129, 0.25)' : '1px solid var(--border-medium)',
                          }}
                        >
                          {u.is_enabled ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
                          <span>{u.business_name}</span>
                          <span style={{ fontSize: '0.7rem', opacity: 0.8 }}>({u.is_enabled ? 'Active' : 'Disabled'})</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* =========================================================================
           TAB 4: CROSS-TENANT FEATURE DEMANDS
           ========================================================================= */}
        {adminTab === 'demands' && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{
              padding: '1.25rem 1.5rem',
              borderBottom: '1px solid var(--border-medium)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              <div>
                <div className="card-title" style={{ fontSize: '1rem', marginBottom: '2px' }}>Custom Tool Pipeline Demands</div>
                <div className="card-desc" style={{ marginBottom: 0, fontSize: '0.8rem' }}>
                  Conversational function calls and 3rd-party API integrations requested by registered business tenants.
                </div>
              </div>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                {demands.length} REQUESTS IN QUEUE
              </span>
            </div>

            {demands.length === 0 ? (
              <div style={{ padding: '3.5rem', textAlign: 'center', color: 'var(--text-tertiary)' }}>
                No custom features demanded yet by any business tenant.
              </div>
            ) : (
              <div className="table-wrapper" style={{ border: 'none' }}>
                <table className="modern-table">
                  <thead>
                    <tr>
                      <th>Demanded Tool</th>
                      <th>Requested By</th>
                      <th>Category</th>
                      <th>Target Integration / API</th>
                      <th>Priority</th>
                      <th>Status</th>
                      <th>Update Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {demands.map((d) => (
                      <tr key={d.id}>
                        <td>
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{d.tool_name}</div>
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', maxWidth: '280px', marginTop: '2px', lineHeight: 1.4 }}>
                            {d.description}
                          </div>
                        </td>
                        <td>
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{d.business_name}</div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>{d.business_id}</div>
                        </td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>{d.category}</td>
                        <td>
                          <code style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.76rem',
                            color: 'var(--text-primary)',
                            background: 'var(--bg-surface-elevated)',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            border: '1px solid var(--border-medium)',
                          }}>
                            {d.integration_target}
                          </code>
                        </td>
                        <td>
                          <span style={{
                            fontWeight: 700,
                            fontSize: '0.75rem',
                            color: d.priority === 'Business Critical' ? 'var(--color-rose)' : 'var(--text-secondary)',
                          }}>
                            {d.priority}
                          </span>
                        </td>
                        <td>
                          <span style={{
                            padding: '3px 8px',
                            borderRadius: 'var(--radius-full)',
                            fontSize: '0.72rem',
                            fontWeight: 700,
                            background: d.status === 'Ready'
                              ? 'rgba(16, 185, 129, 0.12)'
                              : d.status === 'In Development'
                              ? 'rgba(255, 255, 255, 0.08)'
                              : 'rgba(245, 158, 11, 0.12)',
                            color: d.status === 'Ready'
                              ? 'var(--color-emerald)'
                              : d.status === 'In Development'
                              ? 'var(--text-primary)'
                              : 'var(--color-amber)',
                            border: d.status === 'Ready'
                              ? '1px solid rgba(16, 185, 129, 0.25)'
                              : d.status === 'In Development'
                              ? '1px solid var(--border-medium)'
                              : '1px solid rgba(245, 158, 11, 0.25)',
                          }}>
                            {d.status}
                          </span>
                        </td>
                        <td>
                          <select
                            style={{
                              fontSize: '0.75rem',
                              padding: '4px 8px',
                              borderRadius: 'var(--radius-sm)',
                              border: '1px solid var(--border-medium)',
                              background: 'var(--bg-card)',
                              color: 'var(--text-primary)',
                            }}
                            value={d.status}
                            onChange={(e) => handleUpdateDemandStatus(d.id, e.target.value)}
                          >
                            <option value="Under Review">Under Review</option>
                            <option value="In Development">In Development</option>
                            <option value="Ready">Ready & Active</option>
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Agent Inspector Modal (Obsidian Sheet) */}
        {selectedAgentDetail && (
          <div
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0, 0, 0, 0.75)',
              backdropFilter: 'blur(8px)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 100,
              padding: '1.5rem',
            }}
            onClick={() => setSelectedAgentDetail(null)}
          >
            <div
              className="card"
              style={{
                width: '100%',
                maxWidth: '600px',
                maxHeight: '90vh',
                overflowY: 'auto',
                boxShadow: 'var(--shadow-modal)',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', borderBottom: '1px solid var(--border-medium)', paddingBottom: '0.85rem' }}>
                <div>
                  <div className="card-title" style={{ fontSize: '1.1rem', marginBottom: '2px' }}>
                    Agent Telemetry: {selectedAgentDetail.name}
                  </div>
                  <div style={{ fontSize: '0.76rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                    tenant_id: {selectedAgentDetail.id}
                  </div>
                </div>
                <button
                  className="btn-secondary"
                  style={{ padding: '0.3rem 0.65rem', fontSize: '0.78rem' }}
                  onClick={() => setSelectedAgentDetail(null)}
                >
                  <X size={14} /> Close
                </button>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem', marginBottom: '1.25rem', fontSize: '0.82rem' }}>
                <div style={{ color: 'var(--text-secondary)' }}>Industry: <strong style={{ color: 'var(--text-primary)' }}>{selectedAgentDetail.industry}</strong></div>
                <div style={{ color: 'var(--text-secondary)' }}>Status: <strong style={{ color: 'var(--color-emerald)' }}>{selectedAgentDetail.assigned_number_status}</strong></div>
                <div style={{ color: 'var(--text-secondary)' }}>Inbound DID: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-mint)' }}>{selectedAgentDetail.phone_number}</code></div>
                <div style={{ color: 'var(--text-secondary)' }}>Total Calls: <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{selectedAgentDetail.stats?.total_calls || 0}</strong></div>
                <div style={{ color: 'var(--text-secondary)' }}>Schedule: <span style={{ color: 'var(--text-primary)' }}>{selectedAgentDetail.opening_time} – {selectedAgentDetail.closing_time}</span></div>
                <div style={{ color: 'var(--text-secondary)' }}>Timezone: <span style={{ color: 'var(--text-primary)' }}>{selectedAgentDetail.timezone}</span></div>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }}>
                  Inbound Receptionist Greeting:
                </div>
                <div style={{
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-medium)',
                  padding: '0.75rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.82rem',
                  lineHeight: 1.5,
                  color: 'var(--text-primary)',
                  fontStyle: 'italic',
                }}>
                  "{selectedAgentDetail.greeting_message}"
                </div>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }}>
                  Escalation & Operator Hand-off Instructions:
                </div>
                <div style={{
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-medium)',
                  padding: '0.75rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.82rem',
                  lineHeight: 1.5,
                  color: 'var(--text-secondary)',
                }}>
                  {selectedAgentDetail.transfer_instructions || 'Default: Notify front desk manager.'}
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '6px' }}>
                  Enabled Autonomous Tools:
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  {Object.entries(selectedAgentDetail.enabled_tools || {}).map(([tId, isEnabled]) => (
                    <span
                      key={tId}
                      style={{
                        padding: '3px 8px',
                        borderRadius: 'var(--radius-full)',
                        fontSize: '0.72rem',
                        fontWeight: 600,
                        background: isEnabled ? 'rgba(16, 185, 129, 0.1)' : 'rgba(255, 255, 255, 0.03)',
                        color: isEnabled ? 'var(--color-emerald)' : 'var(--text-tertiary)',
                        border: isEnabled ? '1px solid rgba(16, 185, 129, 0.25)' : '1px solid var(--border-medium)',
                      }}
                    >
                      {tId}: {isEnabled ? 'Active' : 'Off'}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
