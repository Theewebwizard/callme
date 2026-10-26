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
} from 'lucide-react';
import { api } from '../api';

const INDUSTRY_OPTIONS = [
  'Astrology / Spiritual',
  'Consulting / Services',
  'Restaurant',
  'Clinic',
  'Salon',
  'Real Estate',
  'Retail / E-commerce',
  'Legal',
  'Other',
];

const LANGUAGE_OPTIONS = ['English', 'Hindi', 'Tamil', 'Telugu', 'Kannada', 'Marathi', 'Bengali', 'Spanish'];
const TIMEZONE_OPTIONS = ['Asia/Kolkata', 'UTC', 'America/New_York', 'Europe/London', 'Asia/Dubai'];

export default function BusinessSetup({ business, onBusinessSaved, onSelectBusiness }) {
  const [activeSubTab, setActiveSubTab] = useState(business ? 'edit' : 'register');
  const [loading, setLoading] = useState(false);
  const [faqSaving, setFaqSaving] = useState(false);
  const [feedback, setFeedback] = useState(null);

  // Registration Form State
  const [regForm, setRegForm] = useState({
    name: '',
    industry: 'Astrology / Spiritual',
    phone_number: '+919513886363',
    description: '',
    opening_time: '09:00',
    closing_time: '21:00',
    timezone: 'Asia/Kolkata',
    languages: ['English', 'Hindi'],
    greeting_message: 'Namaste! Welcome to our reception. I am your AI assistant. How can I help guide you today?',
    transfer_instructions: 'Transfer to human staff if the caller asks for urgent personal attention or outside services.',
    faqs: [
      { question: 'What are your consultation charges?', answer: '15-minute consultations start at Rs. 499, and comprehensive sessions are Rs. 1,499.', category: 'General' },
      { question: 'What are your operating hours?', answer: 'We are open every day from 9:00 AM to 9:00 PM IST.', category: 'General' },
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
      setActiveSubTab('edit');
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
        languages: editForm.languages,
        greeting_message: editForm.greeting_message,
        transfer_instructions: editForm.transfer_instructions,
        faqs: editForm.faqs || [],
      };
      const res = await api.updateBusiness(editForm.id, payload);
      setFeedback({ type: 'success', message: `Configuration for "${res.name}" saved successfully!` });
      onBusinessSaved(res);
    } catch (err) {
      setFeedback({ type: 'error', message: err.message || 'Update failed' });
    } finally {
      setLoading(false);
    }
  };

  // Option A: Direct database auto-save when adding an FAQ
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
      // Revert if failed
      setEditForm((prev) => ({ ...prev, faqs: editForm.faqs || [] }));
      setFeedback({ type: 'error', message: `Failed to save FAQ to DB: ${err.message}` });
    } finally {
      setFaqSaving(false);
    }
  };

  // Option A: Direct database auto-save when removing an FAQ
  const handleRemoveFaqFromEdit = async (index) => {
    const previousFaqs = editForm.faqs || [];
    const updatedFaqs = previousFaqs.filter((_, idx) => idx !== index);

    // Optimistic UI update
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
    <section className="main-content">
      <div className="section-header">
        <h1 className="section-title">⚙️ Business Setup</h1>
        <p className="section-subtitle">
          Configure business identity, virtual receptionist persona, operating schedule, and FAQ knowledge base.
        </p>
      </div>

      {feedback && (
        <div
          style={{
            padding: '1rem',
            borderRadius: 'var(--radius-md)',
            marginBottom: '1.5rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.65rem',
            background: feedback.type === 'success' ? 'var(--emerald-100)' : 'var(--rose-100)',
            color: feedback.type === 'success' ? 'var(--emerald-700)' : 'var(--rose-700)',
            fontWeight: 600,
            fontSize: '0.9rem',
          }}
        >
          {feedback.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
          {feedback.message}
        </div>
      )}

      {/* If no business is configured yet, show initial registration form */}
      {!business && (
        <form onSubmit={handleRegister} className="card">
          <div className="card-title">
            <Building2 size={20} color="var(--sky-600)" /> Onboard Real Business Profile
          </div>
          <div className="card-desc">Enter your business profile details. Your virtual AI receptionist will immediately adopt this persona.</div>

          <div className="form-grid" style={{ marginBottom: '1.5rem' }}>
            <div className="form-group">
              <label className="form-label">Official Business Name *</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Astro Coach"
                value={regForm.name}
                onChange={(e) => setRegForm({ ...regForm, name: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Industry Category</label>
              <select
                className="form-select"
                value={regForm.industry}
                onChange={(e) => setRegForm({ ...regForm, industry: e.target.value })}
              >
                {INDUSTRY_OPTIONS.map((ind) => (
                  <option key={ind} value={ind}>{ind}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Inbound Phone Number (DID)</label>
              <input
                type="text"
                className="form-input"
                placeholder="+919513886363"
                value={regForm.phone_number}
                onChange={(e) => setRegForm({ ...regForm, phone_number: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Timezone</label>
              <select
                className="form-select"
                value={regForm.timezone}
                onChange={(e) => setRegForm({ ...regForm, timezone: e.target.value })}
              >
                {TIMEZONE_OPTIONS.map((tz) => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: '1.5rem' }}>
            <label className="form-label">Business Description & Core Offerings *</label>
            <textarea
              className="form-textarea"
              placeholder="e.g. Vedic astrology consultations, birth chart analysis, planetary gem consultations, relationship guidance."
              value={regForm.description}
              onChange={(e) => setRegForm({ ...regForm, description: e.target.value })}
              required
            />
          </div>

          <div className="form-grid" style={{ marginBottom: '1.5rem' }}>
            <div className="form-group">
              <label className="form-label">Opening Time (HH:MM)</label>
              <input
                type="text"
                className="form-input"
                value={regForm.opening_time}
                onChange={(e) => setRegForm({ ...regForm, opening_time: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Closing Time (HH:MM)</label>
              <input
                type="text"
                className="form-input"
                value={regForm.closing_time}
                onChange={(e) => setRegForm({ ...regForm, closing_time: e.target.value })}
              />
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: '1.5rem' }}>
            <label className="form-label">Receptionist Inbound Greeting Prompt *</label>
            <textarea
              className="form-textarea"
              value={regForm.greeting_message}
              onChange={(e) => setRegForm({ ...regForm, greeting_message: e.target.value })}
              required
            />
          </div>

          <div className="form-group" style={{ marginBottom: '1.5rem' }}>
            <label className="form-label">Human Escalation & Transfer Policy *</label>
            <textarea
              className="form-textarea"
              value={regForm.transfer_instructions}
              onChange={(e) => setRegForm({ ...regForm, transfer_instructions: e.target.value })}
              required
            />
          </div>

          <button type="submit" className="btn-primary" disabled={loading} style={{ width: '100%' }}>
            <Save size={18} /> {loading ? 'Registering...' : '🚀 Register & Activate Business'}
          </button>
        </form>
      )}

      {/* =========================================================================
         EDIT ACTIVE BUSINESS
         ========================================================================= */}
      {business && (
        <form onSubmit={handleUpdate} className="card">
          <div className="card-title">
            <Building2 size={20} color="var(--sky-600)" /> Manage Profile: {editForm.name}
          </div>
          <div className="card-desc">Update business operating hours, reception voice prompts, and knowledge base FAQs.</div>

          <div className="form-grid" style={{ marginBottom: '1.5rem' }}>
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
                value={editForm.industry || 'Other'}
                onChange={(e) => setEditForm({ ...editForm, industry: e.target.value })}
              >
                {INDUSTRY_OPTIONS.map((ind) => (
                  <option key={ind} value={ind}>{ind}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Inbound Phone Number</label>
              <input
                type="text"
                className="form-input"
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

          <div className="form-group" style={{ marginBottom: '1.5rem' }}>
            <label className="form-label">Business Description & Core Offerings</label>
            <textarea
              className="form-textarea"
              value={editForm.description || ''}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
            />
          </div>

          <div className="form-grid" style={{ marginBottom: '1.5rem' }}>
            <div className="form-group">
              <label className="form-label">Opening Time (HH:MM)</label>
              <input
                type="text"
                className="form-input"
                value={editForm.opening_time || '09:00'}
                onChange={(e) => setEditForm({ ...editForm, opening_time: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Closing Time (HH:MM)</label>
              <input
                type="text"
                className="form-input"
                value={editForm.closing_time || '21:00'}
                onChange={(e) => setEditForm({ ...editForm, closing_time: e.target.value })}
              />
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: '1.5rem' }}>
            <label className="form-label">Initial Inbound Greeting Prompt</label>
            <textarea
              className="form-textarea"
              value={editForm.greeting_message || ''}
              onChange={(e) => setEditForm({ ...editForm, greeting_message: e.target.value })}
            />
          </div>

          <div className="form-group" style={{ marginBottom: '1.5rem' }}>
            <label className="form-label">Human Escalation & Transfer Policy</label>
            <textarea
              className="form-textarea"
              value={editForm.transfer_instructions || ''}
              onChange={(e) => setEditForm({ ...editForm, transfer_instructions: e.target.value })}
            />
          </div>

          {/* Interactive Knowledge Base FAQs */}
          <div style={{ marginTop: '2rem', borderTop: '1px solid var(--slate-200)', paddingTop: '1.5rem' }}>
            <div className="card-title">
              <HelpCircle size={18} color="var(--sky-600)" /> Knowledge Base FAQs ({editForm.faqs?.length || 0})
            </div>
            <div className="card-desc">Referenced autonomously by the AI receptionist during customer calls.</div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.5rem' }}>
              {(editForm.faqs || []).map((faq, idx) => (
                <div
                  key={idx}
                  style={{
                    background: 'var(--slate-50)',
                    border: '1px solid var(--slate-200)',
                    borderRadius: 'var(--radius-md)',
                    padding: '0.85rem 1rem',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: '1rem',
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--slate-900)' }}>
                      Q: {faq.question}
                    </div>
                    <div style={{ fontSize: '0.85rem', color: 'var(--slate-600)', marginTop: '0.25rem' }}>
                      A: {faq.answer}
                    </div>
                  </div>
                  <button
                    type="button"
                    style={{ background: 'transparent', border: 'none', color: 'var(--rose-500)', cursor: 'pointer', padding: '4px' }}
                    onClick={() => handleRemoveFaqFromEdit(idx)}
                    title="Delete FAQ"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>

            {/* Add FAQ Sub-card */}
            <div
              style={{
                background: 'var(--sky-50)',
                border: '1px dashed var(--sky-300)',
                borderRadius: 'var(--radius-md)',
                padding: '1rem',
                marginBottom: '1.5rem',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--sky-800)', marginBottom: '0.5rem' }}>
                ➕ Add New FAQ
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '0.75rem', alignItems: 'center' }}>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Question (e.g. Do you accept UPI?)"
                  value={newFaqQ}
                  onChange={(e) => setNewFaqQ(e.target.value)}
                />
                <input
                  type="text"
                  className="form-input"
                  placeholder="Answer (e.g. Yes, UPI and all cards are accepted.)"
                  value={newFaqA}
                  onChange={(e) => setNewFaqA(e.target.value)}
                />
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleAddFaqToEdit}
                  disabled={!newFaqQ.trim() || !newFaqA.trim() || faqSaving}
                >
                  <Plus size={16} /> {faqSaving ? 'Saving...' : 'Add FAQ'}
                </button>
              </div>
            </div>
          </div>

          <button type="submit" className="btn-primary" disabled={loading} style={{ width: '100%' }}>
            <Save size={18} /> {loading ? 'Saving...' : '💾 Save Profile & Knowledge Base'}
          </button>
        </form>
      )}
    </section>
  );
}
