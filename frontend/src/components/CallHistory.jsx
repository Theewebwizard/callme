import React, { useState, useEffect, useMemo } from 'react';
import {
  History,
  Search,
  Filter,
  PhoneCall,
  Clock,
  Wrench,
  CheckCircle,
} from 'lucide-react';
import { api } from '../api';

const OUTCOMES = ['All', 'Booking Completed', 'Inquiry Resolved', 'Transferred to Staff', 'Message Recorded'];

export default function CallHistory({ business }) {
  const [calls, setCalls] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedOutcome, setSelectedOutcome] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCallDetail, setActiveCallDetail] = useState(null);

  // Fetch all business calls once when business mounts
  useEffect(() => {
    if (business?.id) {
      loadAllCalls();
    }
  }, [business?.id]);

  const loadAllCalls = async () => {
    setLoading(true);
    try {
      // Load full call history once so tab switching & searches are instantaneous (< 1ms)
      const res = await api.getCallHistory(business.id, 'All');
      setCalls(res.calls || []);
    } catch (err) {
      console.error('Failed to load calls:', err);
    } finally {
      setLoading(false);
    }
  };

  // Instantaneous in-memory multi-predicate filtering (Outcome filter + Search query)
  const filteredCalls = useMemo(() => {
    return calls.filter((c) => {
      // 1. Outcome pill filter
      if (selectedOutcome !== 'All' && c.outcome !== selectedOutcome) {
        return false;
      }
      // 2. Search query filter
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      const numMatch = c.caller_number && c.caller_number.toLowerCase().includes(q);
      const sumMatch = c.summary && c.summary.toLowerCase().includes(q);
      const toolsMatch = c.tools_used && c.tools_used.some((t) => String(t).toLowerCase().includes(q));
      return numMatch || sumMatch || toolsMatch;
    });
  }, [calls, selectedOutcome, searchQuery]);

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
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <h3>No Business Selected</h3>
          <p style={{ color: 'var(--slate-500)', marginTop: '0.5rem' }}>
            Please select or register a business to view call audit logs.
          </p>
        </div>
      </div>
    );
  }

  return (
    <section className="main-content">
      <div className="section-header">
        <h1 className="section-title">📋 Call History & Audit Logs</h1>
        <p className="section-subtitle">
          Audited logs of customer voice calls, resolution outcomes, and automated tool interventions for <strong>{business.name}</strong>.
        </p>
      </div>

      {/* Filter and Search Bar */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1rem 1.25rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '1rem', alignItems: 'center' }}>
          {/* Outcome Filter Pills */}
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            {OUTCOMES.map((out) => (
              <button
                key={out}
                className={`btn-secondary ${selectedOutcome === out ? 'active' : ''}`}
                style={{
                  padding: '0.35rem 0.75rem',
                  fontSize: '0.8rem',
                  borderRadius: 'var(--radius-full)',
                  background: selectedOutcome === out ? 'var(--sky-500)' : 'white',
                  color: selectedOutcome === out ? 'white' : 'var(--slate-700)',
                  borderColor: selectedOutcome === out ? 'var(--sky-500)' : 'var(--slate-300)',
                }}
                onClick={() => setSelectedOutcome(out)}
              >
                {out}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div style={{ position: 'relative', width: '280px' }}>
            <Search size={15} style={{ position: 'absolute', left: '10px', top: '10px', color: 'var(--slate-400)' }} />
            <input
              type="text"
              className="form-input"
              placeholder="Search phone or summary..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ paddingLeft: '32px', fontSize: '0.85rem', width: '100%' }}
            />
          </div>
        </div>
      </div>

      {/* Main Call Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--slate-500)' }}>
            Loading call history records...
          </div>
        ) : filteredCalls.length > 0 ? (
          <div className="table-wrapper" style={{ border: 'none' }}>
            <table className="modern-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Caller Number</th>
                  <th>Duration</th>
                  <th>Outcome</th>
                  <th>Tools Used</th>
                  <th>Call Summary</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredCalls.map((c) => (
                  <tr key={c.id}>
                    <td style={{ whiteSpace: 'nowrap' }}>{c.datetime}</td>
                    <td><code>{c.caller_number}</code></td>
                    <td>{c.duration}</td>
                    <td>
                      <span className={`outcome-pill ${getOutcomeBadgeClass(c.outcome)}`}>
                        {c.outcome}
                      </span>
                    </td>
                    <td style={{ minWidth: '150px' }}>
                      {c.tools_used && c.tools_used.length > 0 ? (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                          {c.tools_used.map((t, idx) => (
                            <span
                              key={idx}
                              style={{
                                background: 'var(--sky-50)',
                                border: '1px solid var(--sky-200)',
                                color: 'var(--sky-700)',
                                fontSize: '0.74rem',
                                fontWeight: 600,
                                padding: '2px 7px',
                                borderRadius: 'var(--radius-full)',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '3px',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              <Wrench size={11} color="var(--sky-600)" />
                              {typeof t === 'string' ? t.replace(/_/g, ' ') : String(t)}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span style={{ color: 'var(--slate-400)', fontSize: '0.78rem', fontStyle: 'italic' }}>
                          Direct Conversation
                        </span>
                      )}
                    </td>
                    <td style={{ maxWidth: '280px', color: 'var(--slate-700)', fontSize: '0.84rem' }}>
                      <span
                        title={c.summary}
                        style={{
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                          lineHeight: 1.45,
                        }}
                      >
                        {c.summary || 'Caller inquiry processed.'}
                      </span>
                    </td>
                    <td>
                      <button
                        className="btn-secondary"
                        style={{
                          padding: '0.28rem 0.75rem',
                          fontSize: '0.78rem',
                          fontWeight: 600,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                        onClick={() => setActiveCallDetail(c)}
                      >
                        <Search size={12} /> Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--slate-500)' }}>
            No call records found matching criteria.
          </div>
        )}
      </div>

      {/* Modal / Inspector Drawer */}
      {activeCallDetail && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.55)',
            backdropFilter: 'blur(6px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '1.5rem',
          }}
          onClick={() => setActiveCallDetail(null)}
        >
          <div
            className="card"
            style={{ width: '100%', maxWidth: '620px', maxHeight: '90vh', overflowY: 'auto', padding: '1.75rem' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', borderBottom: '1px solid var(--slate-100)', paddingBottom: '0.85rem' }}>
              <div className="card-title" style={{ fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <PhoneCall size={20} color="var(--sky-600)" /> Call Details & Audit Report
              </div>
              <button
                className="btn-secondary"
                style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }}
                onClick={() => setActiveCallDetail(null)}
              >
                ✕ Close
              </button>
            </div>

            {/* Call Meta Overview */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.85rem', marginBottom: '1.25rem', background: 'var(--slate-50)', padding: '0.85rem 1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--slate-200)' }}>
              <div>
                <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--slate-500)', fontWeight: 700 }}>Caller DID</span>
                <div style={{ fontWeight: 600, fontSize: '0.88rem', marginTop: '2px' }}><code>{activeCallDetail.caller_number}</code></div>
              </div>
              <div>
                <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--slate-500)', fontWeight: 700 }}>Call Duration</span>
                <div style={{ fontWeight: 600, fontSize: '0.88rem', marginTop: '2px' }}>{activeCallDetail.duration}</div>
              </div>
              <div>
                <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--slate-500)', fontWeight: 700 }}>Date & Time</span>
                <div style={{ fontWeight: 600, fontSize: '0.88rem', marginTop: '2px' }}>{activeCallDetail.datetime}</div>
              </div>
              <div>
                <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--slate-500)', fontWeight: 700 }}>Resolution Outcome</span>
                <div style={{ marginTop: '2px' }}>
                  <span className={`outcome-pill ${getOutcomeBadgeClass(activeCallDetail.outcome)}`}>
                    {activeCallDetail.outcome}
                  </span>
                </div>
              </div>
            </div>

            {/* Executive Call Summary */}
            <div style={{ marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '0.4rem' }}>
                <CheckCircle size={15} color="var(--emerald-600)" />
                <strong style={{ fontSize: '0.9rem', color: 'var(--slate-800)' }}>Executive Call Summary:</strong>
              </div>
              <div style={{ background: 'white', border: '1px solid var(--sky-200)', padding: '1rem', borderRadius: 'var(--radius-md)', fontSize: '0.88rem', lineHeight: 1.6, color: 'var(--slate-800)', boxShadow: '0 2px 6px rgba(14, 165, 233, 0.05)' }}>
                {activeCallDetail.summary || 'Standard call completed successfully. Full turn transcripts are archived in database.'}
              </div>
            </div>

            {/* Tools Interventions */}
            <div style={{ marginBottom: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '0.5rem' }}>
                <Wrench size={15} color="var(--sky-600)" />
                <strong style={{ fontSize: '0.9rem', color: 'var(--slate-800)' }}>Autonomous Tools Interventions:</strong>
              </div>
              {activeCallDetail.tools_used && activeCallDetail.tools_used.length > 0 ? (
                <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
                  {activeCallDetail.tools_used.map((t, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'var(--sky-50)',
                        border: '1px solid var(--sky-200)',
                        padding: '0.5rem 0.85rem',
                        borderRadius: 'var(--radius-md)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                        fontSize: '0.84rem',
                        fontWeight: 600,
                        color: 'var(--sky-800)',
                      }}
                    >
                      <span style={{ fontSize: '1rem' }}>🔧</span>
                      <span>{typeof t === 'string' ? t.replace(/_/g, ' ') : String(t)}</span>
                      <span style={{ fontSize: '0.72rem', background: 'var(--emerald-100)', color: 'var(--emerald-700)', padding: '2px 6px', borderRadius: '4px', fontWeight: 700 }}>
                        Executed
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ background: 'var(--slate-50)', border: '1px solid var(--slate-200)', padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)', fontSize: '0.84rem', color: 'var(--slate-500)', fontStyle: 'italic' }}>
                  No automated external tool invocations were required for this inquiry (handled through direct dialogue & knowledge base).
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
