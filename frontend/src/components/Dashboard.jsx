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
  Sparkles,
  Bot,
  Zap,
  Activity,
  CheckCircle2,
  Sliders,
  Terminal,
} from 'lucide-react';

export default function Dashboard({ business, onNavigate, calls = [] }) {
  if (!business || !business.id) {
    return (
      <section className="main-content" aria-label="Business Onboarding">
        <div className="hero-banner" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '1.25rem' }}>
          <div>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                color: 'var(--text-secondary)',
                padding: '0.25rem 0.75rem',
                borderRadius: 'var(--radius-full)',
                fontSize: '0.78rem',
                fontWeight: 600,
                marginBottom: '0.75rem',
              }}
            >
              <Sparkles size={13} /> Getting Started
            </div>
            <h2>Welcome to Your CallMe Voice Receptionist Workspace</h2>
            <p className="section-subtitle" style={{ maxWidth: '680px' }}>
              No business tenant profile is currently loaded. Configure your business identity, operating hours, and voice prompts now to activate your 24/7 autonomous receptionist.
            </p>
          </div>
          <button
            type="button"
            className="btn-primary"
            onClick={() => onNavigate('setup')}
            style={{ padding: '0.75rem 1.4rem' }}
          >
            <PlusCircle size={16} />
            <span>Register & Setup Your Business</span>
          </button>
        </div>
      </section>
    );
  }

  const stats = business.stats || {};
  const totalCalls = calls.length > 0 ? calls.length : (stats.total_calls ?? 0);
  const bookings = calls.filter((c) => (c.outcome || '').includes('Booking') || (c.outcome || '').includes('Completed')).length || (stats.bookings_completed ?? 0);
  const escalated = calls.filter((c) => (c.outcome || '').includes('Transferred') || (c.outcome || '').includes('Escalated')).length || (stats.escalated_calls ?? 0);
  const resolutionRate = totalCalls > 0 ? Math.round(((totalCalls - escalated) / totalCalls) * 100) : 100;

  return (
    <section className="main-content" aria-label="Business Receptionist Dashboard">
      {/* Operational Cockpit Banner */}
      <div className="hero-banner">
        <div className="hero-info">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.45rem' }}>
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                background: 'var(--mint-500)',
                boxShadow: '0 0 8px rgba(16, 185, 129, 0.7)',
                display: 'inline-block',
              }}
            />
            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 600,
                color: 'var(--mint-400)',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {business.industry || 'Business'} • 24/7 RECEPTIONIST OPERATIONAL
            </span>
          </div>

          <h2>{business.name}</h2>

          <div className="hero-meta">
            <span className="meta-item">
              <Phone size={13} style={{ color: 'var(--text-tertiary)' }} />
              <strong>DID Line:</strong>
              <code
                style={{
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-primary)',
                  background: 'var(--bg-surface-elevated)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                {business.phone_number || 'Not assigned'}
              </code>
            </span>

            <span className="meta-item">
              <Clock size={13} style={{ color: 'var(--text-tertiary)' }} />
              {business.opening_time} - {business.closing_time} ({business.timezone || 'Asia/Kolkata'})
            </span>

            <span className="meta-item">
              <Languages size={13} style={{ color: 'var(--text-tertiary)' }} />
              {(business.languages || ['English', 'Hindi']).join(', ')}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn-primary"
            onClick={() => onNavigate('webphone')}
          >
            <Phone size={14} />
            <span>Test Inbound Call</span>
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => onNavigate('setup')}
          >
            <Sliders size={14} />
            <span>Configure AI Persona</span>
          </button>
        </div>
      </div>

      {/* Telemetry Metric Cards */}
      <div className="stat-grid">
        <div className="stat-card">
          <div>
            <div className="stat-label">Total Inbound Calls</div>
            <div className="stat-value">{totalCalls}</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '0.2rem' }}>
              Autonomous voice sessions
            </div>
          </div>
          <div className="stat-icon">
            <PhoneCall size={18} />
          </div>
        </div>

        <div className="stat-card">
          <div>
            <div className="stat-label">Resolution Rate</div>
            <div className="stat-value" style={{ color: 'var(--mint-400)' }}>
              {resolutionRate}%
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '0.2rem' }}>
              Handled without human staff
            </div>
          </div>
          <div className="stat-icon" style={{ color: 'var(--mint-400)' }}>
            <Activity size={18} />
          </div>
        </div>

        <div className="stat-card">
          <div>
            <div className="stat-label">Bookings Completed</div>
            <div className="stat-value" style={{ color: '#38bdf8' }}>
              {bookings}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '0.2rem' }}>
              Confirmed to live calendar
            </div>
          </div>
          <div className="stat-icon" style={{ color: '#38bdf8' }}>
            <CalendarCheck size={18} />
          </div>
        </div>

        <div className="stat-card">
          <div>
            <div className="stat-label">Operator Escalated</div>
            <div className="stat-value" style={{ color: 'var(--amber-500)' }}>
              {escalated}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '0.2rem' }}>
              Guarded policy transfers
            </div>
          </div>
          <div className="stat-icon" style={{ color: 'var(--amber-500)' }}>
            <UserCheck size={18} />
          </div>
        </div>
      </div>

      {/* Two-Column Cockpit Grid: Left Persona Governance | Right Live Feed */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(320px, 420px) 1fr',
          gap: '1.25rem',
          alignItems: 'start',
        }}
      >
        {/* Left Column: Autonomous Persona State */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Spoken Greeting Card */}
          <div className="card">
            <div className="card-title">
              <Bot size={16} />
              <span>Spoken Inbound Greeting</span>
            </div>
            <div className="card-desc">
              Acoustic greeting synthesized autonomously when a caller connects.
            </div>
            <blockquote
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-subtle)',
                borderLeft: '3px solid #ffffff',
                padding: '0.85rem 1rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.82rem',
                color: 'var(--text-primary)',
                fontStyle: 'italic',
                lineHeight: 1.55,
              }}
            >
              "{business.greeting_message || 'Namaste and welcome! How can I assist you today?'}"
            </blockquote>
          </div>

          {/* Escalation Policy Card */}
          <div className="card">
            <div className="card-title">
              <ShieldCheck size={16} />
              <span>Guarded Escalation Protocol</span>
            </div>
            <div className="card-desc">
              Autonomous safety rule governing staff handoffs.
            </div>
            <div
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-subtle)',
                padding: '0.85rem 1rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.8rem',
                color: 'var(--text-secondary)',
                lineHeight: 1.5,
              }}
            >
              {business.transfer_instructions || 'Transfer to human staff when caller requests operator assistance.'}
            </div>
          </div>

          {/* Active Autonomous Tools */}
          <div className="card">
            <div className="card-title">
              <Zap size={16} />
              <span>Active Autonomous Tools</span>
            </div>
            <div className="card-desc">
              Verified tools available during live caller interaction.
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem', marginTop: '0.5rem' }}>
              {business.enabled_tools && Object.entries(business.enabled_tools).filter(([_, en]) => en).length > 0 ? (
                Object.entries(business.enabled_tools)
                  .filter(([_, en]) => en)
                  .map(([tId]) => (
                    <span
                      key={tId}
                      style={{
                        background: 'var(--bg-surface-elevated)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-primary)',
                        padding: '0.25rem 0.65rem',
                        borderRadius: 'var(--radius-full)',
                        fontSize: '0.74rem',
                        fontWeight: 500,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.35rem',
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      <span
                        style={{
                          width: '5px',
                          height: '5px',
                          borderRadius: '50%',
                          background: 'var(--mint-500)',
                        }}
                      />
                      {tId.replace(/_/g, ' ')}
                    </span>
                  ))
              ) : (
                <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                  No tools configured yet. Enable capabilities in the Capabilities tab.
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Live Call Stream & Audit Snapshots */}
        <div className="card">
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '1rem',
              flexWrap: 'wrap',
              gap: '0.5rem',
            }}
          >
            <div>
              <div className="card-title">Live Inbound Activity & Audio Logs</div>
              <div className="card-desc" style={{ marginBottom: 0 }}>
                Real-time stream of incoming customer calls, transcripts, and outcomes.
              </div>
            </div>

            <button
              type="button"
              className="btn-secondary"
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.78rem' }}
              onClick={() => onNavigate('calls')}
            >
              <span>View Full Audit Trail</span>
              <ArrowRight size={12} />
            </button>
          </div>

          {calls && calls.length > 0 ? (
            <div className="table-wrapper">
              <table className="modern-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Caller DID</th>
                    <th>Duration</th>
                    <th>Outcome</th>
                    <th>Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.slice(0, 8).map((c) => (
                    <tr key={c.id}>
                      <td style={{ whiteSpace: 'nowrap', color: 'var(--text-tertiary)', fontSize: '0.76rem', fontFamily: 'var(--font-mono)' }}>
                        {c.datetime}
                      </td>
                      <td>
                        <code
                          style={{
                            background: 'var(--bg-surface-elevated)',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            fontSize: '0.78rem',
                            color: '#ffffff',
                            fontFamily: 'var(--font-mono)',
                            border: '1px solid var(--border-subtle)',
                          }}
                        >
                          {c.caller_number}
                        </code>
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                        {c.duration}
                      </td>
                      <td>
                        <span
                          className={`outcome-pill ${
                            (c.outcome || '').includes('Booking')
                              ? 'outcome-completed'
                              : (c.outcome || '').includes('Transferred')
                              ? 'outcome-transferred'
                              : (c.outcome || '').includes('Message')
                              ? 'outcome-message'
                              : (c.outcome || '').includes('Missed')
                              ? 'outcome-missed'
                              : 'outcome-inquiry'
                          }`}
                        >
                          {c.outcome}
                        </span>
                      </td>
                      <td
                        style={{
                          maxWidth: '260px',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          color: 'var(--text-secondary)',
                          fontSize: '0.8rem',
                        }}
                      >
                        {c.summary}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '3.5rem 1rem', color: 'var(--text-tertiary)', fontSize: '0.85rem' }}>
              No incoming calls recorded yet. Click <strong>Test Inbound Call</strong> to test your autonomous receptionist in real-time.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
