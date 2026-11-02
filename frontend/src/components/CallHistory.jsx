import React, { useState, useEffect, useMemo } from 'react';
import {
  History,
  Search,
  Filter,
  PhoneCall,
  Clock,
  Wrench,
  CheckCircle2,
  MessageSquare,
  User,
  Bot,
  Sparkles,
  Phone,
  ArrowRight,
  ShieldCheck,
  Calendar,
  Copy,
  Check,
} from 'lucide-react';
import { api } from '../api';

const OUTCOMES = ['All', 'Booking Completed', 'Inquiry Resolved', 'Transferred to Staff', 'Message Recorded'];

export default function CallHistory({ business, initialCalls = [], onCallsUpdated }) {
  const [calls, setCalls] = useState(initialCalls);
  const [loading, setLoading] = useState(initialCalls.length === 0);
  const [selectedOutcome, setSelectedOutcome] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCallId, setActiveCallId] = useState(initialCalls[0]?.id || null);
  const [copiedTranscript, setCopiedTranscript] = useState(false);
  const [error, setError] = useState(null);

  // Sync state if parent passes new calls
  useEffect(() => {
    if (initialCalls && initialCalls.length > 0) {
      setCalls(initialCalls);
      if (!activeCallId && initialCalls[0]) {
        setActiveCallId(initialCalls[0].id);
      }
      setLoading(false);
    }
  }, [initialCalls]);

  // Fetch calls on mount
  useEffect(() => {
    if (business?.id) {
      loadAllCalls(calls.length === 0);
    }
  }, [business?.id]);

  const loadAllCalls = async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    setError(null);
    try {
      const res = await api.getCallHistory(business.id, 'All');
      const loaded = res.calls || [];
      setCalls(loaded);
      if (loaded.length > 0 && !activeCallId) {
        setActiveCallId(loaded[0].id);
      }
      if (onCallsUpdated) onCallsUpdated(loaded);
    } catch (err) {
      console.error('Failed to load calls:', err);
      if (calls.length === 0) {
        setError(err.message || 'Failed to connect to backend server. Please retry.');
      }
    } finally {
      setLoading(false);
    }
  };

  // Instantaneous multi-predicate filtering
  const filteredCalls = useMemo(() => {
    return calls.filter((c) => {
      if (selectedOutcome !== 'All' && c.outcome !== selectedOutcome) {
        return false;
      }
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      const numMatch = c.caller_number && c.caller_number.toLowerCase().includes(q);
      const sumMatch = c.summary && c.summary.toLowerCase().includes(q);
      const toolsMatch = c.tools_used && c.tools_used.some((t) => String(t).toLowerCase().includes(q));
      return numMatch || sumMatch || toolsMatch;
    });
  }, [calls, selectedOutcome, searchQuery]);

  // Selected call object
  const activeCall = useMemo(() => {
    if (!activeCallId && filteredCalls.length > 0) return filteredCalls[0];
    return filteredCalls.find((c) => c.id === activeCallId) || filteredCalls[0] || null;
  }, [activeCallId, filteredCalls]);

  const handleCopyTranscript = () => {
    if (!activeCall) return;
    const turns = activeCall.transcript || [];
    const text = turns
      .map((t) => `[${t.speaker || t.role}]: ${t.content || t.text || t.message || ''}`)
      .join('\n');
    navigator.clipboard.writeText(text);
    setCopiedTranscript(true);
    setTimeout(() => setCopiedTranscript(false), 2000);
  };

  const getOutcomeBadgeClass = (outcome) => {
    switch (outcome) {
      case 'Booking Completed':
        return 'outcome-completed';
      case 'Inquiry Resolved':
        return 'outcome-inquiry';
      case 'Transferred to Staff':
        return 'outcome-transferred';
      case 'Message Recorded':
        return 'outcome-message';
      default:
        return 'outcome-missed';
    }
  };

  if (!business) {
    return (
      <div className="main-content">
        <div className="card" style={{ textAlign: 'center', padding: '3.5rem 1rem' }}>
          <h3>No Business Selected</h3>
          <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
            Please select or register a business to inspect call audit logs.
          </p>
        </div>
      </div>
    );
  }

  return (
    <section className="main-content" aria-label="Call Audit Trail">
      {/* Header Bar */}
      <div className="section-header" style={{ marginBottom: '1.25rem' }}>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.25rem 0.65rem',
            borderRadius: 'var(--radius-full)',
            background: 'var(--bg-surface-elevated)',
            border: '1px solid var(--border-medium)',
            color: 'var(--text-secondary)',
            fontSize: '0.74rem',
            fontWeight: 600,
            marginBottom: '0.45rem',
          }}
        >
          <History size={12} /> Audited Telephony Session Inspector
        </div>
        <h1 className="section-title">Call History & Turn-by-Turn Audits</h1>
        <p className="section-subtitle">
          Real-time logs of customer voice calls, autonomous tool execution traces, and verified resolutions for <strong>{business.name}</strong>.
        </p>
      </div>

      {/* Raycast Master-Detail Split View */}
      <div className="split-view-container">
        {/* Left Master List Pane */}
        <div className="split-list-pane">
          {/* Search & Filters */}
          <div className="split-list-header">
            <div style={{ position: 'relative', width: '100%' }}>
              <Search
                size={14}
                style={{
                  position: 'absolute',
                  left: '10px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-tertiary)',
                }}
              />
              <input
                type="text"
                placeholder="Search phone, tool, or summary..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="form-input"
                style={{ paddingLeft: '32px', fontSize: '0.8rem' }}
              />
            </div>

            {/* Outcome Filter Pills */}
            <div style={{ display: 'flex', gap: '0.35rem', overflowX: 'auto', paddingBottom: '2px' }}>
              {OUTCOMES.map((oc) => (
                <button
                  key={oc}
                  type="button"
                  onClick={() => setSelectedOutcome(oc)}
                  style={{
                    padding: '0.25rem 0.55rem',
                    borderRadius: 'var(--radius-full)',
                    border: '1px solid',
                    borderColor: selectedOutcome === oc ? 'var(--border-strong)' : 'var(--border-medium)',
                    background: selectedOutcome === oc ? 'var(--bg-surface-elevated)' : 'transparent',
                    color: selectedOutcome === oc ? '#ffffff' : 'var(--text-secondary)',
                    fontSize: '0.72rem',
                    fontWeight: 500,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    transition: 'all var(--transition-fast)',
                  }}
                >
                  {oc}
                </button>
              ))}
            </div>
          </div>

          {/* List Items */}
          <div className="split-list-body">
            {loading ? (
              <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: '0.82rem' }}>
                Loading session logs...
              </div>
            ) : filteredCalls.length === 0 ? (
              <div style={{ padding: '2.5rem 1rem', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: '0.82rem' }}>
                No calls match your criteria.
              </div>
            ) : (
              filteredCalls.map((c) => {
                const isSelected = activeCall?.id === c.id;
                return (
                  <div
                    key={c.id}
                    className={`call-item ${isSelected ? 'active' : ''}`}
                    onClick={() => setActiveCallId(c.id)}
                  >
                    <div className="call-item-top">
                      <span className="call-item-did">{c.caller_number}</span>
                      <span className="call-item-time">{c.datetime?.split(' ')[1] || c.datetime}</span>
                    </div>

                    <div className="call-item-meta">
                      <span className={`outcome-pill ${getOutcomeBadgeClass(c.outcome)}`}>
                        {c.outcome}
                      </span>
                      <span>•</span>
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{c.duration}</span>
                    </div>

                    <div className="call-item-summary">
                      {c.summary || 'Inbound voice call processed.'}
                    </div>

                    {c.tools_used && c.tools_used.length > 0 && (
                      <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap', marginTop: '0.2rem' }}>
                        {c.tools_used.slice(0, 2).map((t, idx) => (
                          <span
                            key={idx}
                            style={{
                              fontSize: '0.68rem',
                              fontFamily: 'var(--font-mono)',
                              background: 'var(--bg-surface-elevated)',
                              border: '1px solid var(--border-medium)',
                              padding: '1px 5px',
                              borderRadius: '4px',
                              color: 'var(--text-secondary)',
                            }}
                          >
                            {typeof t === 'string' ? t.replace(/_/g, ' ') : String(t)}
                          </span>
                        ))}
                        {c.tools_used.length > 2 && (
                          <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)' }}>
                            +{c.tools_used.length - 2}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Detail Inspector Pane */}
        <div className="split-detail-pane">
          {activeCall ? (
            <>
              {/* Top Inspector Bar */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  borderBottom: '1px solid var(--border-medium)',
                  paddingBottom: '1rem',
                  flexWrap: 'wrap',
                  gap: '0.75rem',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                    <code
                      style={{
                        fontSize: '1.15rem',
                        fontWeight: 700,
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-primary)',
                      }}
                    >
                      {activeCall.caller_number}
                    </code>
                    <span className={`outcome-pill ${getOutcomeBadgeClass(activeCall.outcome)}`}>
                      {activeCall.outcome}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.76rem', color: 'var(--text-tertiary)', marginTop: '0.25rem', fontFamily: 'var(--font-mono)' }}>
                    Session ID: {activeCall.id} • {activeCall.datetime} • Duration: {activeCall.duration}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={handleCopyTranscript}
                    style={{ padding: '0.35rem 0.75rem', fontSize: '0.78rem' }}
                  >
                    {copiedTranscript ? <Check size={13} style={{ color: 'var(--mint-400)' }} /> : <Copy size={13} />}
                    <span>{copiedTranscript ? 'Copied' : 'Copy Transcript'}</span>
                  </button>
                </div>
              </div>

              {/* Section 1: Executive Call Summary */}
              <div>
                <div className="card-title" style={{ fontSize: '0.85rem', marginBottom: '0.4rem' }}>
                  <Sparkles size={14} />
                  <span>Executive Resolution Summary</span>
                </div>
                <div
                  style={{
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-medium)',
                    padding: '0.85rem 1rem',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.84rem',
                    color: 'var(--text-primary)',
                    lineHeight: 1.55,
                  }}
                >
                  {activeCall.summary || 'Inbound caller inquiry addressed and resolved autonomously.'}
                </div>
              </div>

              {/* Section 2: Autonomous Tool Execution Trace */}
              {activeCall.tools_used && activeCall.tools_used.length > 0 && (
                <div>
                  <div className="card-title" style={{ fontSize: '0.85rem', marginBottom: '0.4rem' }}>
                    <Wrench size={14} />
                    <span>Autonomous Tool Interventions ({activeCall.tools_used.length})</span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    {activeCall.tools_used.map((t, idx) => (
                      <div
                        key={idx}
                        style={{
                          background: 'var(--bg-surface-elevated)',
                          border: '1px solid var(--border-medium)',
                          padding: '0.65rem 0.85rem',
                          borderRadius: 'var(--radius-sm)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          fontSize: '0.78rem',
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <CheckCircle2 size={13} style={{ color: 'var(--mint-400)' }} />
                          <span style={{ color: 'var(--text-primary)' }}>{typeof t === 'string' ? t : JSON.stringify(t)}</span>
                        </div>
                        <span
                          style={{
                            fontSize: '0.7rem',
                            color: 'var(--mint-400)',
                            background: 'rgba(16, 185, 129, 0.1)',
                            padding: '1px 6px',
                            borderRadius: '4px',
                          }}
                        >
                          SUCCESS
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Section 3: Turn-by-Turn Spoken Dialogue Transcript */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div className="card-title" style={{ fontSize: '0.85rem', marginBottom: '0.4rem' }}>
                  <MessageSquare size={14} />
                  <span>Turn-by-Turn Acoustic Transcript</span>
                </div>

                <div
                  style={{
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-medium)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '1rem',
                    flex: 1,
                    maxHeight: '400px',
                    overflowY: 'auto',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.75rem',
                  }}
                >
                  {activeCall.transcript && activeCall.transcript.length > 0 ? (
                    activeCall.transcript.map((turn, idx) => {
                      const isUser = turn.speaker === 'user' || turn.role === 'user' || turn.speaker === 'caller';
                      return (
                        <div
                          key={idx}
                          style={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: isUser ? 'flex-end' : 'flex-start',
                            maxWidth: '85%',
                            alignSelf: isUser ? 'flex-end' : 'flex-start',
                          }}
                        >
                          <div
                            style={{
                              fontSize: '0.68rem',
                              color: 'var(--text-tertiary)',
                              marginBottom: '2px',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.3rem',
                            }}
                          >
                            {isUser ? <User size={10} /> : <Bot size={10} />}
                            <span>{isUser ? 'Caller' : `${business.name} Receptionist`}</span>
                          </div>
                          <div
                            style={{
                              background: isUser ? '#ffffff' : 'var(--bg-surface-hover)',
                              color: isUser ? '#07080a' : 'var(--text-primary)',
                              padding: '0.6rem 0.85rem',
                              borderRadius: 'var(--radius-sm)',
                              fontSize: '0.82rem',
                              lineHeight: 1.5,
                              border: isUser ? 'none' : '1px solid var(--border-medium)',
                              fontWeight: isUser ? 500 : 400,
                            }}
                          >
                            {turn.content || turn.text || turn.message || ''}
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div style={{ color: 'var(--text-tertiary)', fontStyle: 'italic', fontSize: '0.82rem', padding: '1rem 0' }}>
                      Audio session completed. Full transcription archived in telephony store.
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '4rem 1rem', color: 'var(--text-tertiary)' }}>
              Select a call session from the left stream to inspect turns and tool interventions.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
