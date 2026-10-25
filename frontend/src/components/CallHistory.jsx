import React, { useState, useEffect } from 'react';
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

  useEffect(() => {
    if (business) {
      loadCalls();
    }
  }, [business?.id, selectedOutcome]);

  const loadCalls = async () => {
    setLoading(true);
    try {
      const res = await api.getCallHistory(business.id, selectedOutcome);
      setCalls(res.calls || []);
    } catch (err) {
      console.error('Failed to load calls:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredCalls = calls.filter((c) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      (c.caller_number && c.caller_number.toLowerCase().includes(q)) ||
      (c.summary && c.summary.toLowerCase().includes(q))
    );
  });

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
                    <td>
                      {c.tools_used && c.tools_used.length > 0 ? (
                        c.tools_used.map((t, idx) => (
                          <span
                            key={idx}
                            style={{
                              background: 'var(--sky-50)',
                              color: 'var(--sky-700)',
                              fontSize: '0.72rem',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              marginRight: '4px',
                            }}
                          >
                            {t}
                          </span>
                        ))
                      ) : (
                        <span style={{ color: 'var(--slate-400)', fontSize: '0.75rem' }}>None</span>
                      )}
                    </td>
                    <td style={{ maxWidth: '300px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {c.summary}
                    </td>
                    <td>
                      <button
                        className="btn-secondary"
                        style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem' }}
                        onClick={() => setActiveCallDetail(c)}
                      >
                        Inspect
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
            background: 'rgba(15, 23, 42, 0.45)',
            backdropFilter: 'blur(4px)',
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
            style={{ width: '100%', maxWidth: '540px', maxHeight: '90vh', overflowY: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div className="card-title">Call Details — #{activeCallDetail.id}</div>
              <button
                className="btn-secondary"
                style={{ padding: '0.3rem 0.65rem' }}
                onClick={() => setActiveCallDetail(null)}
              >
                ✕ Close
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem', fontSize: '0.85rem' }}>
              <div><strong>Caller:</strong> {activeCallDetail.caller_number}</div>
              <div><strong>Duration:</strong> {activeCallDetail.duration}</div>
              <div><strong>Date:</strong> {activeCallDetail.datetime}</div>
              <div>
                <strong>Outcome:</strong>{' '}
                <span className={`outcome-pill ${getOutcomeBadgeClass(activeCallDetail.outcome)}`}>
                  {activeCallDetail.outcome}
                </span>
              </div>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <strong style={{ fontSize: '0.85rem' }}>Executive Summary:</strong>
              <div style={{ background: 'var(--slate-50)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', marginTop: '0.35rem', fontSize: '0.85rem', lineHeight: 1.5 }}>
                {activeCallDetail.summary}
              </div>
            </div>

            <div>
              <strong style={{ fontSize: '0.85rem' }}>Tools Interventions:</strong>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.35rem', flexWrap: 'wrap' }}>
                {activeCallDetail.tools_used?.map((t, idx) => (
                  <span key={idx} className="outcome-pill outcome-inquiry">
                    🔧 {t}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
