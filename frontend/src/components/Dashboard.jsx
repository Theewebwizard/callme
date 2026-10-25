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
  const totalCalls = stats.total_calls || calls.length || 0;
  const bookings = stats.bookings_completed || 0;
  const escalated = stats.escalated_calls || 0;

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

      {/* Receptionist Persona Snapshot & Quick Launch */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        <div className="card">
          <div className="card-title">
            <span>👋 Reception Greeting Prompt</span>
          </div>
          <div className="card-desc">Spoken autonomously when an inbound customer call connects.</div>
          <blockquote style={{
            background: 'var(--sky-50)',
            borderLeft: '4px solid var(--sky-500)',
            padding: '1rem',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.9rem',
            color: 'var(--slate-800)',
            fontStyle: 'italic',
            lineHeight: 1.5
          }}>
            "{business.greeting_message || 'Welcome to our business! How can I assist you today?'}"
          </blockquote>
        </div>

        <div className="card">
          <div className="card-title">
            <span>🛡️ Escalation & Transfer Policy</span>
          </div>
          <div className="card-desc">Guards that govern when the receptionist escalates to human staff.</div>
          <div style={{
            background: 'var(--slate-50)',
            border: '1px solid var(--slate-200)',
            padding: '1rem',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.85rem',
            color: 'var(--slate-700)',
            lineHeight: 1.5
          }}>
            {business.transfer_instructions || 'Transfer to human staff when caller requests operator assistance.'}
          </div>
        </div>
      </div>

      {/* Recent Activity Snapshot */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div>
            <div className="card-title">Recent Inbound Calls</div>
            <div className="card-desc" style={{ marginBottom: 0 }}>Latest live and simulated calls routed to this tenant.</div>
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
                {calls.slice(0, 4).map((c) => (
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
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--slate-500)', fontSize: '0.9rem' }}>
            No calls recorded yet for {business.name}. Use the <strong>Web Phone</strong> to make your first live test call!
          </div>
        )}
      </div>
    </section>
  );
}
