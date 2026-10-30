import React, { useState } from 'react';
import {
  Plus,
  Trash2,
  RefreshCw,
  Database,
  Calendar,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { api } from '../api';
import BookingCalendarView from './BookingCalendarView';
import { getDomainForBusiness } from '../domain/businessDomainRegistry';

export default function ResourceInventoryCard({
  business,
  resources = [],
  reservations = [],
  onRefresh,
  domainConfig: propDomainConfig,
}) {
  const domainConfig = propDomainConfig || getDomainForBusiness(business);
  const rc = domainConfig.resourceConfig;
  const DomainIcon = rc.icon || Database;

  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState(null);

  // Form State adapted to domain
  const [name, setName] = useState('');
  const [resourceType, setResourceType] = useState(rc.defaultType || rc.allowedTypes[0]?.value || 'table');
  const [section, setSection] = useState(rc.defaultSection || '');
  const [capacity, setCapacity] = useState(2);
  const [minParty, setMinParty] = useState(1);
  const [maxParty, setMaxParty] = useState(4);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;

    setLoading(true);
    setFeedback(null);
    try {
      await api.createResource(business.id, {
        name: name.trim(),
        capacity: Number(capacity),
        min_party_size: Number(minParty),
        max_party_size: Number(maxParty),
        resource_type: resourceType,
        section: section.trim() || rc.defaultSection,
      });

      setName('');
      setFeedback({ type: 'success', text: `${rc.noun} "${name.trim()}" added successfully!` });
      if (onRefresh) await onRefresh();
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to add ${rc.noun}: ${err.message}` });
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (resourceId, resourceName) => {
    if (!window.confirm(`Delete "${resourceName}"? Existing bookings will be preserved in records.`)) return;

    setLoading(true);
    setFeedback(null);
    try {
      await api.deleteResource(business.id, resourceId);
      setFeedback({ type: 'success', text: `"${resourceName}" deleted from inventory.` });
      if (onRefresh) await onRefresh();
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to delete: ${err.message}` });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      {/* Feedback Banner */}
      {feedback && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-md, 8px)',
            background: feedback.type === 'success' ? 'var(--emerald-100, #d1fae5)' : 'var(--rose-100, #ffe4e6)',
            color: feedback.type === 'success' ? 'var(--emerald-700, #047857)' : 'var(--rose-700, #be123c)',
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

      {/* Interactive Booking Calendar & Timeline Grid */}
      <BookingCalendarView
        business={business}
        resources={resources}
        reservations={reservations}
        onRefresh={onRefresh}
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', alignItems: 'flex-start' }}>
        {/* Domain-Adapted Add Form */}
        <form onSubmit={handleAdd} className="card">
          <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Plus size={18} color="var(--sky-600)" />
            Add {rc.noun}
          </div>
          <div className="card-desc">
            {rc.subtitle}
          </div>

          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label className="form-label">{rc.noun} Name / Label *</label>
            <input
              type="text"
              className="form-input"
              placeholder={rc.namePlaceholder}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div className="form-grid" style={{ marginBottom: '1rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div className="form-group">
              <label className="form-label">Type</label>
              <select
                className="form-input"
                value={resourceType}
                onChange={(e) => setResourceType(e.target.value)}
              >
                {rc.allowedTypes.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Section / Area</label>
              <input
                type="text"
                className="form-input"
                placeholder={rc.sectionPlaceholder}
                value={section}
                onChange={(e) => setSection(e.target.value)}
              />
            </div>
          </div>

          <div className="form-grid" style={{ marginBottom: '1.25rem', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
            <div className="form-group">
              <label className="form-label">{rc.capacityLabel}</label>
              <input
                type="number"
                className="form-input"
                min="1"
                max="100"
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Min Party</label>
              <input
                type="number"
                className="form-input"
                min="1"
                max="100"
                value={minParty}
                onChange={(e) => setMinParty(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Max Party</label>
              <input
                type="number"
                className="form-input"
                min="1"
                max="100"
                value={maxParty}
                onChange={(e) => setMaxParty(e.target.value)}
                required
              />
            </div>
          </div>

          <button
            type="submit"
            className="btn-primary"
            disabled={loading}
            style={{ width: '100%', justifyContent: 'center' }}
          >
            <Plus size={16} /> {loading ? 'Registering...' : `Register ${rc.noun}`}
          </button>
        </form>

        {/* Active Inventory List */}
        <div className="card">
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <DomainIcon size={18} color="var(--sky-600)" />
              Active {rc.title} ({resources.length})
            </span>
            <button
              type="button"
              className="btn-secondary"
              onClick={onRefresh}
              disabled={loading}
              style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }}
            >
              <RefreshCw size={12} className={loading ? 'spin' : ''} /> Refresh
            </button>
          </div>
          <div className="card-desc">
            Resources authoritative in your database. AI receptionist checks live availability against this inventory.
          </div>

          {resources.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--slate-500)', background: 'var(--slate-50)', borderRadius: 'var(--radius-md, 8px)' }}>
              No {rc.title.toLowerCase()} registered yet. Register a {rc.noun.toLowerCase()} to enable built-in booking conflict prevention.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '420px', overflowY: 'auto' }}>
              {resources.map((res) => (
                <div
                  key={res.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '0.75rem 1rem',
                    background: 'var(--slate-50, #f8fafc)',
                    border: '1px solid var(--slate-200, #e2e8f0)',
                    borderRadius: 'var(--radius-md, 8px)',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 700, color: 'var(--slate-800, #1e293b)', fontSize: '0.9rem' }}>
                      {res.name}
                    </div>
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginTop: '4px', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: '0.72rem', background: 'var(--sky-100, #e0f2fe)', color: 'var(--sky-700, #0369a1)', padding: '2px 8px', borderRadius: '10px', fontWeight: 600 }}>
                        {res.resource_type}
                      </span>
                      {res.section && (
                        <span style={{ fontSize: '0.72rem', color: 'var(--slate-500, #64748b)' }}>
                          📍 {res.section}
                        </span>
                      )}
                      <span style={{ fontSize: '0.72rem', color: 'var(--slate-500, #64748b)' }}>
                        👥 Capacity: {res.capacity} (Party: {res.min_party_size}–{res.max_party_size})
                      </span>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleDelete(res.id, res.name)}
                    disabled={loading}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--rose-500, #f43f5e)',
                      cursor: 'pointer',
                      padding: '6px',
                    }}
                    title={`Delete ${res.name}`}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
