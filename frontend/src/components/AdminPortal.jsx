import React, { useState, useEffect } from 'react';
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
      {/* Admin Dedicated Taskbar */}
      <header className="taskbar" style={{ background: 'linear-gradient(90deg, #ffffff 0%, #f0f9ff 100%)', borderBottom: '2px solid var(--sky-200)' }}>
        <div className="taskbar-top">
          <div className="taskbar-brand">
            <div className="brand-icon" style={{ background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)' }}>
              <ShieldCheck size={22} strokeWidth={2.5} />
            </div>
            <div>
              <div className="brand-text" style={{ fontSize: '1.15rem' }}>
                Call<span>Me</span> Admin
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--sky-700)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Platform Operator Command Center
              </div>
            </div>
          </div>

          {/* Right Exit */}
          <div className="taskbar-status">
            <span style={{ fontSize: '0.8rem', background: 'var(--emerald-100)', color: 'var(--emerald-800)', padding: '0.3rem 0.75rem', borderRadius: 'var(--radius-full)', fontWeight: 700 }}>
              ● Superuser Mode
            </span>
            <button
              className="btn-secondary"
              style={{ padding: '0.35rem 0.85rem', fontSize: '0.8rem', borderRadius: 'var(--radius-full)' }}
              onClick={onExitAdmin}
            >
              <LogOut size={14} /> Exit Admin
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
              <Activity size={15} /> Live Agents Fleet
            </button>

            <button
              className={`nav-pill ${adminTab === 'users' ? 'active' : ''}`}
              onClick={() => setAdminTab('users')}
            >
              <Users size={15} /> Users & Profiles
            </button>

            <button
              className={`nav-pill ${adminTab === 'tools' ? 'active' : ''}`}
              onClick={() => setAdminTab('tools')}
            >
              <Wrench size={15} /> Master Tool Repository
            </button>

            <button
              className={`nav-pill ${adminTab === 'demands' ? 'active' : ''}`}
              onClick={() => setAdminTab('demands')}
            >
              <Sparkles size={15} /> Demanded Features ({demands.length})
            </button>
          </nav>
        </div>
      </header>

      {/* Main Admin Content */}
      <main className="main-content" style={{ flex: 1 }}>
        {feedback && (
          <div
            style={{
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius-md)',
              marginBottom: '1.25rem',
              background: feedback.type === 'success' ? 'var(--emerald-100)' : 'var(--rose-100)',
              color: feedback.type === 'success' ? 'var(--emerald-700)' : 'var(--rose-700)',
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

        {/* Security Isolation Banner */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', background: 'var(--sky-50)', border: '1px solid var(--sky-200)', padding: '0.65rem 1rem', borderRadius: 'var(--radius-md)', marginBottom: '1.5rem', fontSize: '0.82rem', color: 'var(--sky-900)' }}>
          <ShieldCheck size={18} color="var(--sky-600)" />
          <span>
            <strong>Platform Security Policy Active:</strong> Strict tenant isolation enforced. Admins possess read-only fleet telemetry, user records, and tool catalog oversight. Admin accounts cannot log in as or impersonate business tenants.
          </span>
        </div>

        {/* High-level Platform KPIs */}
        {overview && (
          <div className="stat-grid" style={{ marginBottom: '2rem' }}>
            <div className="stat-card">
              <div>
                <div className="stat-label">Total Live Receptionist Agents</div>
                <div className="stat-value">{overview.total_agents}</div>
              </div>
              <div className="stat-icon">
                <Bot size={22} />
              </div>
            </div>

            <div className="stat-card">
              <div>
                <div className="stat-label">Total Calls Handled Across Agents</div>
                <div className="stat-value" style={{ color: 'var(--sky-600)' }}>
                  {overview.total_calls}
                </div>
              </div>
              <div className="stat-icon">
                <PhoneCall size={22} />
              </div>
            </div>

            <div className="stat-card">
              <div>
                <div className="stat-label">Active Telephony DIDs</div>
                <div className="stat-value" style={{ color: 'var(--emerald-600)' }}>
                  {overview.active_phone_lines}
                </div>
              </div>
              <div className="stat-icon" style={{ background: 'var(--emerald-100)', color: 'var(--emerald-700)' }}>
                <Activity size={22} />
              </div>
            </div>

            <div className="stat-card">
              <div>
                <div className="stat-label">Custom Tool Demands</div>
                <div className="stat-value" style={{ color: 'var(--amber-800)' }}>
                  {overview.total_demands}
                </div>
              </div>
              <div className="stat-icon" style={{ background: 'var(--amber-100)', color: 'var(--amber-800)' }}>
                <Sparkles size={22} />
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
           TAB 1: LIVE AGENTS FLEET OVERVIEW
           ========================================================================= */}
        {adminTab === 'live_agents' && overview && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--slate-100)' }}>
              <div className="card-title">Live Receptionist Agents Fleet</div>
              <div className="card-desc" style={{ marginBottom: 0 }}>
                Real-time operational status, line connections, and metrics for all registered business agents.
              </div>
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
                          <strong>{ag.name}</strong>
                          <div style={{ fontSize: '0.75rem', color: 'var(--slate-400)' }}>ID: {ag.id}</div>
                        </td>
                        <td>
                          <span style={{ background: 'var(--sky-50)', color: 'var(--sky-700)', padding: '2px 8px', borderRadius: '12px', fontSize: '0.78rem', fontWeight: 600 }}>
                            {ag.industry}
                          </span>
                        </td>
                        <td><code>{ag.phone_number || 'Unassigned'}</code></td>
                        <td>
                          <span style={{ color: 'var(--emerald-700)', background: 'var(--emerald-100)', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 700 }}>
                            ● {ag.assigned_number_status}
                          </span>
                        </td>
                        <td>{ag.opening_time} - {ag.closing_time}</td>
                        <td><strong>{ag.stats?.total_calls || 0}</strong></td>
                        <td>
                          <span style={{ background: 'var(--slate-100)', padding: '2px 8px', borderRadius: '10px', fontSize: '0.78rem', fontWeight: 600 }}>
                            {activeToolsCount} active
                          </span>
                        </td>
                        <td>
                          <button
                            className="btn-secondary"
                            style={{ padding: '0.3rem 0.65rem', fontSize: '0.78rem' }}
                            onClick={() => setSelectedAgentDetail(ag)}
                          >
                            <Eye size={13} /> Inspect
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
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
            {overview.agents.map((ag) => (
              <div key={ag.id} className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                  <div>
                    <div style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--slate-900)' }}>
                      {ag.name}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--slate-500)' }}>
                      Tenant Slug: <code>{ag.id}</code>
                    </div>
                  </div>
                  <span style={{ background: 'var(--sky-100)', color: 'var(--sky-800)', padding: '3px 9px', borderRadius: '12px', fontSize: '0.78rem', fontWeight: 700 }}>
                    {ag.industry}
                  </span>
                </div>

                <div style={{ fontSize: '0.85rem', color: 'var(--slate-700)', marginBottom: '0.75rem', lineHeight: 1.4 }}>
                  <strong>Description:</strong> {ag.description || 'No description provided.'}
                </div>

                <div style={{ background: 'var(--slate-50)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', marginBottom: '0.75rem', fontSize: '0.82rem' }}>
                  <div style={{ fontWeight: 700, color: 'var(--sky-800)', marginBottom: '2px' }}>Receptionist Greeting:</div>
                  <div style={{ fontStyle: 'italic', color: 'var(--slate-700)' }}>"{ag.greeting_message}"</div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--slate-100)', paddingTop: '0.75rem', fontSize: '0.8rem', color: 'var(--slate-500)' }}>
                  <span>Line: <strong>{ag.phone_number}</strong></span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--slate-600)', background: 'var(--slate-100)', padding: '3px 8px', borderRadius: '4px', fontWeight: 600 }}>
                    🔒 Tenant Isolated (Supervisory Only)
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* =========================================================================
           TAB 3: MASTER TOOL REPOSITORY & AGENT USAGE
           ========================================================================= */}
        {adminTab === 'tools' && toolsRepo && (
          <div>
            <div className="section-header">
              <h2 className="section-title" style={{ fontSize: '1.4rem' }}>Master Canonical Tools Repository</h2>
              <p className="section-subtitle">
                Complete catalog of conversational tools built into the platform and which registered agents are using each tool.
              </p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {toolsRepo.tools.map((t) => (
                <div key={t.id} className="card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', marginBottom: '0.75rem' }}>
                    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                      <div style={{ width: '40px', height: '40px', borderRadius: 'var(--radius-md)', background: 'var(--sky-500)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800 }}>
                        <Wrench size={20} />
                      </div>
                      <div>
                        <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--slate-900)' }}>
                          {t.name} (<code>{t.id}</code>)
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--sky-700)', fontWeight: 600 }}>
                          Category: {t.category} • Adoption: <strong>{t.adoption_rate}</strong> ({t.active_agents_count} of {t.total_agents_count} agents)
                        </div>
                        <div style={{ marginTop: '4px', display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                          <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--slate-500)' }}>Allowed Industries:</span>
                          {t.is_universal ? (
                            <span style={{ background: 'var(--emerald-50)', color: 'var(--emerald-800)', border: '1px solid var(--emerald-200)', padding: '1px 8px', borderRadius: '10px', fontSize: '0.7rem', fontWeight: 700 }}>
                              🌐 Universal (All Businesses)
                            </span>
                          ) : (
                            (t.allowed_industries || []).map((ind, idx) => (
                              <span key={idx} style={{ background: 'var(--sky-50)', color: 'var(--sky-800)', border: '1px solid var(--sky-200)', padding: '1px 8px', borderRadius: '10px', fontSize: '0.7rem', fontWeight: 600 }}>
                                🎯 {ind}
                              </span>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div style={{ fontSize: '0.85rem', color: 'var(--slate-600)', marginBottom: '1rem', lineHeight: 1.4 }}>
                    {t.description}
                  </div>

                  {/* Agent Usage Breakdown */}
                  <div style={{ background: 'var(--slate-50)', border: '1px solid var(--slate-200)', borderRadius: 'var(--radius-sm)', padding: '0.75rem 1rem' }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--slate-700)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Which Business Agents Are Using This Tool:
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
                            borderRadius: '12px',
                            fontSize: '0.78rem',
                            fontWeight: 600,
                            background: u.is_enabled ? 'var(--emerald-100)' : 'var(--slate-100)',
                            color: u.is_enabled ? 'var(--emerald-800)' : 'var(--slate-500)',
                            border: u.is_enabled ? '1px solid var(--emerald-200)' : '1px solid var(--slate-200)',
                          }}
                        >
                          {u.is_enabled ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
                          <span>{u.business_name}</span>
                          <span style={{ fontSize: '0.7rem', opacity: 0.85 }}>({u.is_enabled ? 'Active' : 'Disabled'})</span>
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
            <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--slate-100)' }}>
              <div className="card-title">Cross-Tenant Custom Tool Demands ({demands.length})</div>
              <div className="card-desc" style={{ marginBottom: 0 }}>
                Feature requests and external API integrations demanded by business owners.
              </div>
            </div>

            {demands.length === 0 ? (
              <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--slate-400)' }}>
                No custom features demanded yet by any business.
              </div>
            ) : (
              <div className="table-wrapper" style={{ border: 'none' }}>
                <table className="modern-table">
                  <thead>
                    <tr>
                      <th>Demanded Tool</th>
                      <th>Requested By</th>
                      <th>Category</th>
                      <th>Target Software / API</th>
                      <th>Priority</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {demands.map((d) => (
                      <tr key={d.id}>
                        <td>
                          <strong>{d.tool_name}</strong>
                          <div style={{ fontSize: '0.78rem', color: 'var(--slate-600)', maxWidth: '280px', marginTop: '2px' }}>
                            {d.description}
                          </div>
                        </td>
                        <td>
                          <strong>{d.business_name}</strong>
                          <div style={{ fontSize: '0.72rem', color: 'var(--slate-400)' }}>{d.business_id}</div>
                        </td>
                        <td>{d.category}</td>
                        <td><code>{d.integration_target}</code></td>
                        <td>
                          <span style={{ fontWeight: 700, color: d.priority === 'Business Critical' ? 'var(--rose-700)' : 'var(--slate-700)' }}>
                            {d.priority}
                          </span>
                        </td>
                        <td>
                          <span style={{
                            padding: '3px 8px',
                            borderRadius: '12px',
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            background: d.status === 'Ready' ? 'var(--emerald-100)' : d.status === 'In Development' ? 'var(--sky-100)' : 'var(--amber-100)',
                            color: d.status === 'Ready' ? 'var(--emerald-800)' : d.status === 'In Development' ? 'var(--sky-800)' : 'var(--amber-800)',
                          }}>
                            {d.status}
                          </span>
                        </td>
                        <td>
                          <select
                            style={{ fontSize: '0.75rem', padding: '3px 6px', borderRadius: '4px', border: '1px solid var(--slate-300)' }}
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

        {/* Agent Inspector Modal */}
        {selectedAgentDetail && (
          <div
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(15, 23, 42, 0.45)',
              backdropFilter: 'blur(4px)',
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
              style={{ width: '100%', maxWidth: '580px', maxHeight: '90vh', overflowY: 'auto' }}
              onClick={(e) => e.stopPropagation()}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <div className="card-title">Agent Telemetry: {selectedAgentDetail.name}</div>
                <button
                  className="btn-secondary"
                  style={{ padding: '0.3rem 0.65rem' }}
                  onClick={() => setSelectedAgentDetail(null)}
                >
                  ✕ Close
                </button>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem', fontSize: '0.85rem' }}>
                <div><strong>Tenant ID:</strong> {selectedAgentDetail.id}</div>
                <div><strong>Industry:</strong> {selectedAgentDetail.industry}</div>
                <div><strong>Inbound DID:</strong> {selectedAgentDetail.phone_number}</div>
                <div><strong>Status:</strong> {selectedAgentDetail.assigned_number_status}</div>
                <div><strong>Opening Time:</strong> {selectedAgentDetail.opening_time}</div>
                <div><strong>Closing Time:</strong> {selectedAgentDetail.closing_time}</div>
                <div><strong>Timezone:</strong> {selectedAgentDetail.timezone}</div>
                <div><strong>Total Calls:</strong> {selectedAgentDetail.stats?.total_calls || 0}</div>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <strong style={{ fontSize: '0.85rem' }}>Greeting Message:</strong>
                <div style={{ background: 'var(--slate-50)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', marginTop: '0.35rem', fontSize: '0.85rem', lineHeight: 1.5 }}>
                  "{selectedAgentDetail.greeting_message}"
                </div>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <strong style={{ fontSize: '0.85rem' }}>Escalation & Transfer Instructions:</strong>
                <div style={{ background: 'var(--slate-50)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', marginTop: '0.35rem', fontSize: '0.85rem', lineHeight: 1.5 }}>
                  {selectedAgentDetail.transfer_instructions}
                </div>
              </div>

              <div>
                <strong style={{ fontSize: '0.85rem' }}>Enabled Tools:</strong>
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.35rem', flexWrap: 'wrap' }}>
                  {Object.entries(selectedAgentDetail.enabled_tools || {}).map(([tId, isEnabled]) => (
                    <span
                      key={tId}
                      style={{
                        padding: '3px 8px',
                        borderRadius: '12px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        background: isEnabled ? 'var(--emerald-100)' : 'var(--slate-100)',
                        color: isEnabled ? 'var(--emerald-800)' : 'var(--slate-500)',
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
