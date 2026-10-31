import React, { useState, useEffect } from 'react';
import {
  Building2,
  Phone,
  Clock,
  Languages,
  HelpCircle,
  Plus,
  Trash2,
  Save,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Bot,
  ShieldCheck,
  Check,
} from 'lucide-react';
import { api } from '../api';

const INDUSTRY_OPTIONS = [
  'Restaurant',
  'Clinic / Medical',
  'Salon / Spa',
  'Astrology / Spiritual',
  'Consulting / Professional Services',
  'Real Estate',
  'Retail / E-commerce',
  'Automotive',
  'Legal',
  'Other',
];

const TIMEZONE_OPTIONS = ['Asia/Kolkata', 'UTC', 'America/New_York', 'Europe/London', 'Asia/Dubai'];

export default function BusinessSetup({ business, onBusinessSaved }) {
  const [loading, setLoading] = useState(false);
  const [faqSaving, setFaqSaving] = useState(false);
  const [feedback, setFeedback] = useState(null);

  // Registration Form State (when no business exists)
  const [regForm, setRegForm] = useState({
    name: '',
    industry: 'Restaurant',
    phone_number: '+919696967307',
    description: '',
    opening_time: '09:00',
    closing_time: '21:00',
    timezone: 'Asia/Kolkata',
    languages: ['English', 'Hindi'],
    greeting_message: 'Namaste! Welcome to our reception. I am your AI assistant. How may I assist you today?',
    transfer_instructions: 'Transfer to human staff if the caller asks for urgent personal attention or outside services.',
    faqs: [
      { question: 'What are your operating hours?', answer: 'We are open every day from 9:00 AM to 9:00 PM IST.', category: 'General' },
      { question: 'Do you take advance reservations?', answer: 'Yes, reservations can be confirmed directly over the phone.', category: 'General' },
    ],
  });

  // Edit Form State (Synchronized with active business)
  const [editForm, setEditForm] = useState(business || {});

  useEffect(() => {
    if (business) {
      setEditForm(JSON.parse(JSON.stringify(business)));
    }
  }, [business]);

  // Handle New FAQ addition in edit form
  const [newFaqQ, setNewFaqQ] = useState('');
  const [newFaqA, setNewFaqA] = useState('');

  const handleRegister = async (e) => {
    e.preventDefault();
    if (!regForm.name.trim()) {
      setFeedback({ type: 'error', message: 'Business Name is required.' });
      return;
    }
    setLoading(true);
    setFeedback(null);
    try {
      const res = await api.createBusiness(regForm);
      setFeedback({ type: 'success', message: `Business "${res.name}" successfully registered!` });
      onBusinessSaved(res);
    } catch (err) {
      setFeedback({ type: 'error', message: err.message || 'Registration failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdate = async (e) => {
    e.preventDefault();
    if (!editForm.name || !editForm.name.trim()) {
      setFeedback({ type: 'error', message: 'Business Name cannot be empty.' });
      return;
    }
    setLoading(true);
    setFeedback(null);
    try {
      const payload = {
        name: editForm.name.trim(),
        industry: editForm.industry,
        description: editForm.description,
        phone_number: editForm.phone_number,
        opening_time: editForm.opening_time,
        closing_time: editForm.closing_time,
        timezone: editForm.timezone,
        languages: editForm.languages || ['English', 'Hindi'],
        greeting_message: editForm.greeting_message,
        transfer_instructions: editForm.transfer_instructions,
        faqs: editForm.faqs || [],
      };
      const res = await api.updateBusiness(editForm.id, payload);
      setFeedback({ type: 'success', message: `Configuration for "${res.name}" saved successfully!` });
      onBusinessSaved(res);
      setTimeout(() => setFeedback(null), 3500);
    } catch (err) {
      setFeedback({ type: 'error', message: err.message || 'Update failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleAddFaqToEdit = async () => {
    if (!newFaqQ.trim() || !newFaqA.trim()) return;
    const newEntry = { question: newFaqQ.trim(), answer: newFaqA.trim(), category: 'General' };
    const updatedFaqs = [...(editForm.faqs || []), newEntry];

    // Optimistic UI update
    setEditForm((prev) => ({ ...prev, faqs: updatedFaqs }));
    setNewFaqQ('');
    setNewFaqA('');
    setFaqSaving(true);

    try {
      const savedFaqs = await api.updateFaqs(editForm.id, updatedFaqs);
      setEditForm((prev) => ({ ...prev, faqs: savedFaqs }));
      if (onBusinessSaved) {
        onBusinessSaved({ ...business, faqs: savedFaqs });
      }
      setFeedback({ type: 'success', message: 'New FAQ saved directly to database!' });
      setTimeout(() => setFeedback(null), 3000);
    } catch (err) {
      setEditForm((prev) => ({ ...prev, faqs: editForm.faqs || [] }));
      setFeedback({ type: 'error', message: `Failed to save FAQ: ${err.message}` });
    } finally {
      setFaqSaving(false);
    }
  };

  const handleRemoveFaqFromEdit = async (index) => {
    const previousFaqs = editForm.faqs || [];
    const updatedFaqs = previousFaqs.filter((_, idx) => idx !== index);

    setEditForm((prev) => ({ ...prev, faqs: updatedFaqs }));
    setFaqSaving(true);

    try {
      const savedFaqs = await api.updateFaqs(editForm.id, updatedFaqs);
      setEditForm((prev) => ({ ...prev, faqs: savedFaqs }));
      if (onBusinessSaved) {
        onBusinessSaved({ ...business, faqs: savedFaqs });
      }
      setFeedback({ type: 'success', message: 'FAQ removed from database!' });
      setTimeout(() => setFeedback(null), 3000);
    } catch (err) {
      setEditForm((prev) => ({ ...prev, faqs: previousFaqs }));
      setFeedback({ type: 'error', message: `Failed to delete FAQ: ${err.message}` });
    } finally {
      setFaqSaving(false);
    }
  };

  return (
    <section className="main-content" aria-label="Receptionist & Business Settings">
      <div className="section-header" style={{ marginBottom: '1.5rem' }}>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.25rem 0.65rem',
            borderRadius: 'var(--radius-full)',
            background: 'var(--bg-surface-elevated)',
            border: '1px solid var(--border-subtle)',
            color: 'var(--text-secondary)',
            fontSize: '0.74rem',
            fontWeight: 600,
            marginBottom: '0.45rem',
          }}
        >
          <Building2 size={12} /> Persona & Knowledge Engine
        </div>
        <h1 className="section-title">Receptionist Setup & Knowledge Base</h1>
        <p className="section-subtitle">
          Configure business operating hours, AI spoken voice persona, escalation policies, and verified FAQ responses for <strong>{business?.name || 'Your Business'}</strong>.
        </p>
      </div>

      {feedback && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-sm)',
            marginBottom: '1.5rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            background: feedback.type === 'success' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
            color: feedback.type === 'success' ? 'var(--mint-400)' : '#fb7185',
            border: `1px solid ${feedback.type === 'success' ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)'}`,
            fontWeight: 500,
            fontSize: '0.82rem',
          }}
          role="alert"
        >
          {feedback.type === 'success' ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
          <span>{feedback.message}</span>
        </div>
      )}

      {/* Edit Form */}
      {business && (
        <form onSubmit={handleUpdate} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
          {/* Section 1: Business Identity & Line */}
          <div>
            <div style={{ fontSize: '0.76rem', fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.85rem', fontFamily: 'var(--font-mono)' }}>
              1. Business Profile & Inbound Line
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Business Name *</label>
                <input
                  type="text"
                  className="form-input"
                  value={editForm.name || ''}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Industry Category</label>
                <select
                  className="form-select"
                  value={editForm.industry || 'Restaurant'}
                  onChange={(e) => setEditForm({ ...editForm, industry: e.target.value })}
                >
                  {INDUSTRY_OPTIONS.map((ind) => (
                    <option key={ind} value={ind}>{ind}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Inbound Phone DID</label>
                <input
                  type="text"
                  className="form-input"
                  style={{ fontFamily: 'var(--font-mono)' }}
                  value={editForm.phone_number || ''}
                  onChange={(e) => setEditForm({ ...editForm, phone_number: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Business Timezone</label>
                <select
                  className="form-select"
                  value={editForm.timezone || 'Asia/Kolkata'}
                  onChange={(e) => setEditForm({ ...editForm, timezone: e.target.value })}
                >
                  {TIMEZONE_OPTIONS.map((tz) => (
                    <option key={tz} value={tz}>{tz}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">Business Description & Core Offerings</label>
              <textarea
                className="form-textarea"
                value={editForm.description || ''}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                rows={2}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Opening Time (HH:MM)</label>
                <input
                  type="text"
                  className="form-input"
                  style={{ fontFamily: 'var(--font-mono)' }}
                  value={editForm.opening_time || '09:00'}
                  onChange={(e) => setEditForm({ ...editForm, opening_time: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Closing Time (HH:MM)</label>
                <input
                  type="text"
                  className="form-input"
                  style={{ fontFamily: 'var(--font-mono)' }}
                  value={editForm.closing_time || '21:00'}
                  onChange={(e) => setEditForm({ ...editForm, closing_time: e.target.value })}
                />
              </div>
            </div>
          </div>

          {/* Section 2: Spoken Persona & Escalation */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '1.5rem' }}>
            <div style={{ fontSize: '0.76rem', fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.85rem', fontFamily: 'var(--font-mono)' }}>
              2. Spoken Voice Persona & Safety Rules
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">Initial Spoken Greeting</label>
              <textarea
                className="form-textarea"
                value={editForm.greeting_message || ''}
                onChange={(e) => setEditForm({ ...editForm, greeting_message: e.target.value })}
                rows={2}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Guarded Human Operator Transfer Policy</label>
              <textarea
                className="form-textarea"
                value={editForm.transfer_instructions || ''}
                onChange={(e) => setEditForm({ ...editForm, transfer_instructions: e.target.value })}
                rows={2}
              />
            </div>
          </div>

          {/* Section 3: Interactive Knowledge Base FAQs */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <div style={{ fontSize: '0.76rem', fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontFamily: 'var(--font-mono)' }}>
                3. Knowledge Base FAQs ({editForm.faqs?.length || 0})
              </div>
            </div>
            <p className="card-desc" style={{ marginBottom: '1rem' }}>
              Referenced deterministically by the receptionist model during live customer telephone calls.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', marginBottom: '1.25rem' }}>
              {(editForm.faqs || []).map((faq, idx) => (
                <div
                  key={idx}
                  style={{
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '0.85rem 1rem',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: '1rem',
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: '0.86rem', color: '#ffffff' }}>
                      Q: {faq.question}
                    </div>
                    <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: '0.3rem', lineHeight: 1.5 }}>
                      A: {faq.answer}
                    </div>
                  </div>
                  <button
                    type="button"
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--text-tertiary)',
                      cursor: 'pointer',
                      padding: '4px',
                      borderRadius: '4px',
                      transition: 'color var(--transition-fast)',
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.color = 'var(--rose-500)'}
                    onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-tertiary)'}
                    onClick={() => handleRemoveFaqFromEdit(idx)}
                    title="Delete FAQ"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>

            {/* Add FAQ Sub-box */}
            <div
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px dashed var(--border-medium)',
                borderRadius: 'var(--radius-sm)',
                padding: '1rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: '0.8rem', color: '#ffffff', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <Plus size={14} />
                <span>Add Knowledge FAQ Entry</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '0.65rem', alignItems: 'center' }}>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Question (e.g. Do you have valet parking?)"
                  value={newFaqQ}
                  onChange={(e) => setNewFaqQ(e.target.value)}
                />
                <input
                  type="text"
                  className="form-input"
                  placeholder="Answer (e.g. Yes, complimentary valet is available.)"
                  value={newFaqA}
                  onChange={(e) => setNewFaqA(e.target.value)}
                />
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleAddFaqToEdit}
                  disabled={!newFaqQ.trim() || !newFaqA.trim() || faqSaving}
                  style={{ whiteSpace: 'nowrap', padding: '0.5rem 0.85rem' }}
                >
                  <Plus size={14} />
                  <span>{faqSaving ? 'Saving...' : 'Add FAQ'}</span>
                </button>
              </div>
            </div>
          </div>

          {/* Save Action Bar */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '1.25rem', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="submit"
              className="btn-primary"
              disabled={loading}
              style={{ padding: '0.65rem 1.5rem' }}
            >
              <Save size={15} />
              <span>{loading ? 'Saving Changes...' : 'Save Configuration'}</span>
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
