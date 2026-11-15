import React, { useState, useMemo } from 'react';
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
  Volume2,
  Copy,
  Check,
  Search,
  ExternalLink,
} from 'lucide-react';

export default function Dashboard({ business, onNavigate, calls = [] }) {
  const [searchFilter, setSearchFilter] = useState('');
  const [copiedDid, setCopiedDid] = useState(false);
  const [isPlayingGreeting, setIsPlayingGreeting] = useState(false);

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
            <h2>Welcome to Your Answerly Voice Receptionist Workspace</h2>
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

  const handleCopyDid = () => {
    if (!business.phone_number) return;
    navigator.clipboard.writeText(business.phone_number);
    setCopiedDid(true);
    setTimeout(() => setCopiedDid(false), 2000);
  };

  const handlePlayGreetingSimulation = () => {
    if (isPlayingGreeting) return;
    setIsPlayingGreeting(true);
    setTimeout(() => setIsPlayingGreeting(false), 3000);
  };

  // Filtered calls stream
  const filteredCalls = useMemo(() => {
    if (!searchFilter.trim()) return calls;
    const q = searchFilter.toLowerCase();
    return calls.filter(
      (c) =>
        (c.caller_number && c.caller_number.toLowerCase().includes(q)) ||
        (c.summary && c.summary.toLowerCase().includes(q)) ||
        (c.outcome && c.outcome.toLowerCase().includes(q))
    );
  }, [calls, searchFilter]);

  return (
    <section className="main-content" aria-label="Business Receptionist Dashboard" style={{ padding: '1.75rem 2rem' }}>
      {/* 1. Operational Cockpit Status Banner */}
      <div
        className="card"
        style={{
          marginBottom: '1.5rem',
          padding: '1.5rem 1.75rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
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
                fontSize: '0.74rem',
                fontWeight: 700,
                color: 'var(--mint-400)',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                fontFamily: 'var(--font-mono)',
              }}
            >
              24/7 RECEPTIONIST OPERATIONAL • ZERO LATENCY DROP
            </span>
          </div>

          <h1 style={{ fontSize: '1.65rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.03em', margin: 0 }}>
            {business.name}
          </h1>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginTop: '0.35rem' }}>
            {/* Click to copy DID */}
            <button
              type="button"
              onClick={handleCopyDid}
              title="Click to copy inbound phone DID"
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                borderRadius: 'var(--radius-sm)',
                padding: '3px 8px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '0.76rem',
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-primary)',
                cursor: 'pointer',
              }}
            >
              <Phone size={11} style={{ color: 'var(--text-tertiary)' }} />
              <span>{business.phone_number || 'DID Unassigned'}</span>
              {copiedDid ? <Check size={11} style={{ color: 'var(--mint-400)' }} /> : <Copy size={11} style={{ color: 'var(--text-tertiary)' }} />}
            </button>

            <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
              <Clock size={12} style={{ color: 'var(--text-tertiary)' }} />
              <span>{business.opening_time || '09:00'} – {business.closing_time || '21:00'} ({business.timezone || 'Asia/Kolkata'})</span>
            </span>

            <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
              <Languages size={12} style={{ color: 'var(--text-tertiary)' }} />
              <span>{(business.languages || ['English', 'Hindi']).join(', ')}</span>
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn-primary"
            onClick={() => onNavigate('webphone')}
          >
            <Phone size={13} />
            <span>Test Inbound Call</span>
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => onNavigate('setup')}
          >
            <Sliders size={13} />
            <span>Configure AI Persona</span>
          </button>
        </div>
      </div>

      {/* 2. Linear-Style KPI Telemetry Cards */}
      <div className="stat-grid" style={{ marginBottom: '1.5rem' }}>
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

      {/* 3. Two-Column Operational Workbench: Left Agent Governance | Right Live Feed */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(320px, 420px) 1fr',
          gap: '1.5rem',
          alignItems: 'start',
        }}
      >
        {/* Left Column: Autonomous Persona State */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Spoken Greeting Card */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
              <div className="card-title" style={{ margin: 0 }}>
                <Bot size={15} />
                <span>Spoken Inbound Greeting</span>
              </div>
              <button
                type="button"
                onClick={handlePlayGreetingSimulation}
                title="Simulate speech synthesis playback"
                style={{
                  background: isPlayingGreeting ? 'rgba(16, 185, 129, 0.2)' : 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '3px 8px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '0.7rem',
                  fontFamily: 'var(--font-mono)',
                  color: isPlayingGreeting ? 'var(--mint-400)' : 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                <Volume2 size={12} className={isPlayingGreeting ? 'animate-pulse' : ''} />
                <span>{isPlayingGreeting ? 'Synthesizing...' : 'Play Audio'}</span>
              </button>
            </div>
            <div className="card-desc">
              Acoustic greeting synthesized autonomously when a caller connects.
            </div>

            <blockquote
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                borderLeft: '3px solid #ffffff',
                padding: '0.85rem 1rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.82rem',
                color: 'var(--text-primary)',
                fontStyle: 'italic',
                lineHeight: 1.55,
                margin: '0 0 0.85rem 0',
              }}
            >
              "{business.greeting_message || 'Namaste and welcome! How can I assist you today?'}"
            </blockquote>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={() => onNavigate('setup')}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-tertiary)',
                  fontSize: '0.74rem',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <span>Edit Spoken Persona</span>
                <ArrowRight size={11} />
              </button>
            </div>
          </div>

          {/* Escalation Policy Card */}
          <div className="card">
            <div className="card-title">
              <ShieldCheck size={15} />
              <span>Guarded Escalation Protocol</span>
            </div>
            <div className="card-desc">
              Autonomous safety rule governing staff handoffs.
            </div>
            <div
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
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
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
              <div className="card-title" style={{ margin: 0 }}>
                <Zap size={15} />
                <span>Active Autonomous Tools</span>
              </div>
              <button
                type="button"
                onClick={() => onNavigate('tools')}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-tertiary)',
                  fontSize: '0.72rem',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '3px',
                }}
              >
                <span>Registry</span>
                <ArrowRight size={11} />
              </button>
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
                        border: '1px solid var(--border-medium)',
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
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '1rem',
              flexWrap: 'wrap',
              gap: '0.75rem',
            }}
          >
            <div>
              <div className="card-title" style={{ margin: 0 }}>Live Inbound Activity & Audio Logs</div>
              <div className="card-desc" style={{ marginBottom: 0, marginTop: '2px' }}>
                Real-time stream of incoming customer calls, transcripts, and verified outcomes.
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {calls && calls.length > 0 && (
                <div style={{ position: 'relative' }}>
                  <Search size={13} style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)' }} />
                  <input
                    type="text"
                    placeholder="Search logs..."
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    style={{
                      background: 'var(--bg-surface-elevated)',
                      border: '1px solid var(--border-medium)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '0.28rem 0.6rem 0.28rem 1.6rem',
                      color: 'var(--text-primary)',
                      fontSize: '0.76rem',
                      width: '120px',
                      outline: 'none',
                    }}
                  />
                </div>
              )}

              <button
                type="button"
                className="btn-secondary"
                style={{ padding: '0.3rem 0.65rem', fontSize: '0.76rem' }}
                onClick={() => onNavigate('calls')}
              >
                <span>Full Audit Trail</span>
                <ArrowRight size={11} />
              </button>
            </div>
          </div>

          {filteredCalls && filteredCalls.length > 0 ? (
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
                  {filteredCalls.slice(0, 8).map((c) => (
                    <tr
                      key={c.id}
                      onClick={() => onNavigate('calls')}
                      style={{ cursor: 'pointer' }}
                      title="Click to view full turn-by-turn audit transcript"
                    >
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
                            color: 'var(--text-primary)',
                            fontFamily: 'var(--font-mono)',
                            border: '1px solid var(--border-medium)',
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
            /* High-Quality Empty State with Test Inbound Call CTA */
            <div
              style={{
                textAlign: 'center',
                padding: '4rem 1.5rem',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'rgba(255, 255, 255, 0.015)',
                borderRadius: 'var(--radius-md)',
                border: '1px dashed var(--border-medium)',
              }}
            >
              <div
                style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '50%',
                  background: 'rgba(16, 185, 129, 0.1)',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                  color: 'var(--mint-400)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '1rem',
                }}
              >
                <PhoneCall size={22} />
              </div>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 0.4rem 0' }}>
                No Inbound Calls Logged Yet
              </h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', maxWidth: '440px', lineHeight: 1.55, margin: '0 0 1.25rem 0' }}>
                Your 24/7 AI receptionist is active and monitoring line <strong>{business.phone_number || 'DID'}</strong>. When callers dial this line or test conversations in Web Phone, verified call summaries and turn-by-turn audio transcripts will appear here.
              </p>
              <button
                type="button"
                className="btn-primary"
                onClick={() => onNavigate('webphone')}
              >
                <Phone size={13} />
                <span>Test First Inbound Call</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
