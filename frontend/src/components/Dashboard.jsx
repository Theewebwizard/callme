import React from 'react';
import {
  PhoneCall,
  Clock,
  Languages,
  Phone,
  CalendarCheck,
  UserCheck,
  ShieldCheck,
  ArrowRight,
  PlusCircle,
  ExternalLink,
} from 'lucide-react';

export default function Dashboard({ business, onNavigate, calls = [] }) {
  if (!business || !business.id) {
    return (
      <section className="main-content">
        <div className="hero-banner" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '1rem' }}>
          <div>
            <h2>👋 Welcome to CallMe AI Receptionist</h2>
            <p className="section-subtitle">
              No business tenant is currently configured in the database. Onboard your real business profile now to activate your 24/7 autonomous receptionist.
            </p>
          </div>
          <button className="btn-primary" onClick={() => onNavigate('setup')}>
            <PlusCircle size={18} />
            Register Your Business Now
          </button>
        </div>
      </section>
    );
  }

  const stats = business.stats || {};
  const totalCalls = calls.length > 0 ? calls.length : (stats.total_calls ?? 0);
  const bookings = calls.filter((c) => (c.outcome || '').includes('Booking') || (c.outcome || '').includes('Completed')).length || (stats.bookings_completed ?? 0);
  const escalated = calls.filter((c) => (c.outcome || '').includes('Transferred') || (c.outcome || '').includes('Escalated')).length || (stats.escalated_calls ?? 0);

  return (
    <section className="main-content">
      {/* Hero Active Business Banner */}
      <div className="hero-banner">
        <div className="hero-info">
          <h2>{business.name}</h2>
          <p style={{ color: 'var(--sky-700)', fontWeight: 600, fontSize: '0.9rem', marginTop: '0.15rem' }}>
            {business.industry || 'Business'} • Virtual Receptionist Active
          </p>
          <div className="hero-meta">
            <span className="meta-item">
              <Phone size={14} color="var(--sky-600)" />
              <strong>Line:</strong> {business.phone_number || 'Not assigned'}
            </span>
            <span className="meta-item">
              <Clock size={14} color="var(--sky-600)" />
              {business.opening_time} - {business.closing_time} ({business.timezone || 'Asia/Kolkata'})
            </span>
            <span className="meta-item">
              <Languages size={14} color="var(--sky-600)" />
              {(business.languages || ['English']).join(', ')}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn-primary" onClick={() => onNavigate('webphone')}>
            <Phone size={16} />
            Test Voice Call
          </button>
          <button className="btn-secondary" onClick={() => onNavigate('setup')}>
            Configure Profile
          </button>
        </div>
      </div>

      {/* KPI Stat Cards */}
      <div className="stat-grid">
        <div className="stat-card">
          <div>
            <div className="stat-label">Total Inbound Calls</div>
            <div className="stat-value">{totalCalls}</div>
          </div>
          <div className="stat-icon">
            <PhoneCall size={20} />
          </div>
        </div>

        <div className="stat-card">
          <div>
            <div className="stat-label">Bookings Completed</div>
            <div className="stat-value" style={{ color: 'var(--emerald-600)' }}>
              {bookings}
            </div>
          </div>
          <div className="stat-icon" style={{ background: 'var(--emerald-100)', color: 'var(--emerald-700)' }}>
            <CalendarCheck size={20} />
          </div>
        </div>

        <div className="stat-card">
          <div>
            <div className="stat-label">Operator Escalated</div>
            <div className="stat-value" style={{ color: 'var(--amber-800)' }}>
              {escalated}
            </div>
          </div>
          <div className="stat-icon" style={{ background: 'var(--amber-100)', color: 'var(--amber-800)' }}>
            <UserCheck size={20} />
          </div>
        </div>

        <div className="stat-card">
          <div>
            <div className="stat-label">Telephony Line Status</div>
            <div className="stat-value" style={{ fontSize: '1.25rem', color: 'var(--sky-600)' }}>
              {business.assigned_number_status || 'Active & Connected'}
            </div>
          </div>
          <div className="stat-icon">
            <ShieldCheck size={20} />
          </div>
        </div>
      </div>

      {/* Receptionist Persona Snapshot & Tools */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem', marginBottom: '1.75rem' }}>
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="card-title">
            <span>👋 Reception Greeting Prompt</span>
          </div>
          <div className="card-desc">Spoken autonomously when an inbound customer call connects.</div>
          <blockquote style={{
            background: 'linear-gradient(135deg, var(--sky-50) 0%, rgba(224, 242, 254, 0.4) 100%)',
            borderLeft: '4px solid var(--sky-500)',
            padding: '1rem 1.15rem',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.88rem',
            color: 'var(--slate-800)',
            fontStyle: 'italic',
            lineHeight: 1.55,
            marginTop: 'auto',
          }}>
            "{business.greeting_message || 'Welcome to our business! How can I assist you today?'}"
          </blockquote>
        </div>

        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="card-title">
            <span>🛡️ Escalation & Transfer Policy</span>
          </div>
          <div className="card-desc">Policy governing when the receptionist escalates to human staff.</div>
          <div style={{
            background: 'var(--slate-50)',
            border: '1px solid var(--slate-200)',
            padding: '1rem 1.15rem',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.86rem',
            color: 'var(--slate-700)',
            lineHeight: 1.55,
            marginTop: 'auto',
          }}>
            {business.transfer_instructions || 'Transfer to human staff when caller requests operator assistance.'}
          </div>
        </div>

        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="card-title">
            <span>⚡ Active Agent Capabilities</span>
          </div>
          <div className="card-desc">Autonomous tools currently enabled for this business.</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem', marginTop: 'auto', paddingTop: '0.5rem' }}>
            {business.enabled_tools && Object.entries(business.enabled_tools).filter(([_, en]) => en).length > 0 ? (
              Object.entries(business.enabled_tools)
                .filter(([_, en]) => en)
                .map(([tId]) => (
                  <span
                    key={tId}
                    style={{
                      background: 'var(--sky-50)',
                      border: '1px solid var(--sky-200)',
                      color: 'var(--sky-700)',
                      padding: '0.25rem 0.65rem',
                      borderRadius: 'var(--radius-full)',
                      fontSize: '0.78rem',
                      fontWeight: 600,
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                    }}
                  >
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--emerald-500)' }} />
                    {tId.replace(/_/g, ' ')}
                  </span>
                ))
            ) : (
              <span style={{ fontSize: '0.85rem', color: 'var(--slate-500)' }}>
                No tools configured yet. Enable tools in Tools & Demands tab.
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Recent Activity Snapshot */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div>
            <div className="card-title">Recent Inbound Calls</div>
            <div className="card-desc" style={{ marginBottom: 0 }}>Latest live calls and transcripts recorded in the database.</div>
          </div>
          <button className="btn-secondary" style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem' }} onClick={() => onNavigate('calls')}>
            View All Calls <ArrowRight size={13} />
          </button>
        </div>

        {calls && calls.length > 0 ? (
          <div className="table-wrapper">
            <table className="modern-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Caller</th>
                  <th>Duration</th>
                  <th>Outcome</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {calls.slice(0, 5).map((c) => (
                  <tr key={c.id}>
                    <td>{c.datetime}</td>
                    <td><code>{c.caller_number}</code></td>
                    <td>{c.duration}</td>
                    <td>
                      <span className={`outcome-pill ${
                        c.outcome === 'Booking Completed' ? 'outcome-completed' :
                        c.outcome === 'Transferred to Staff' ? 'outcome-transferred' :
                        'outcome-inquiry'
                      }`}>
                        {c.outcome}
                      </span>
                    </td>
                    <td style={{ maxWidth: '300px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {c.summary}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '2.5rem 1rem', color: 'var(--slate-500)', fontSize: '0.9rem' }}>
            <PhoneCall size={32} color="var(--sky-400)" style={{ margin: '0 auto 0.75rem', display: 'block' }} />
            No calls recorded yet in the database for <strong>{business.name}</strong>.<br />
            Click <strong>Test Voice Call</strong> above to test your receptionist in real-time.
          </div>
        )}
      </div>
    </section>
  );
}
