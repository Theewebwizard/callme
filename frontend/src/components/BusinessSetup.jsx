import React, { useState, useEffect, useMemo } from 'react';
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
  Volume2,
  RotateCcw,
  BookOpen,
  Calendar,
  Layers,
  ArrowRight,
} from 'lucide-react';
import { api } from '../api';

const INDUSTRY_OPTIONS = [
  'Restaurant',
  'Hotel / Hospitality',
  'Clinic / Medical',
];

const TIMEZONE_OPTIONS = ['Asia/Kolkata', 'UTC', 'America/New_York', 'Europe/London', 'Asia/Dubai'];

export default function BusinessSetup({ business, onBusinessSaved }) {
  const [activeSection, setActiveSection] = useState('profile'); // 'profile', 'voice', 'escalation', 'faqs'
  const [loading, setLoading] = useState(false);
  const [faqSaving, setFaqSaving] = useState(false);
  const [feedback, setFeedback] = useState(null);

  // Registration Form State (when no business exists)
  const [regForm, setRegForm] = useState({
    name: '',
    industry: 'Restaurant',
    phone_number: '+91 80 4123 5678',
    description: '',
    opening_time: '11:30',
    closing_time: '23:00',
    timezone: 'Asia/Kolkata',
    languages: ['English', 'Hindi'],
    greeting_message: 'Namaste! Welcome to our reception. I am your AI assistant. How may I assist you today?',
    transfer_instructions: 'Transfer to human staff if the caller asks for urgent personal attention or outside services.',
    faqs: [
      { question: 'What are your operating hours?', answer: 'We are open every day from 11:30 AM to 11:00 PM IST.', category: 'General' },
      { question: 'Do you take advance reservations?', answer: 'Yes, reservations can be confirmed directly over the phone.', category: 'General' },
    ],
  });

  // Edit Form State (Synchronized with active business)
  const [editForm, setEditForm] = useState(business || {});
  const [initialState, setInitialState] = useState(business || {});

  useEffect(() => {
    if (business) {
      const cloned = JSON.parse(JSON.stringify(business));
      setEditForm(cloned);
      setInitialState(cloned);
    }
  }, [business]);

  // Track if form has unsaved modifications
  const isDirty = useMemo(() => {
    if (!business) return false;
    return JSON.stringify(editForm) !== JSON.stringify(initialState);
  }, [editForm, initialState, business]);

  // Handle New FAQ addition
  const [newFaqQ, setNewFaqQ] = useState('');
  const [newFaqA, setNewFaqA] = useState('');
  const [newFaqCategory, setNewFaqCategory] = useState('General');

  // Audio greeting playback simulation
  const [simulatingSpeech, setSimulatingSpeech] = useState(false);
  const handleSimulateSpeech = () => {
    if (simulatingSpeech) return;
    setSimulatingSpeech(true);
    setTimeout(() => setSimulatingSpeech(false), 3000);
  };

  const handleDiscardChanges = () => {
    if (isDirty && !window.confirm('Discard all unsaved changes and reload saved configuration?')) {
      return;
    }
    setEditForm(JSON.parse(JSON.stringify(initialState)));
    setFeedback({ type: 'info', message: 'Unsaved modifications discarded.' });
    setTimeout(() => setFeedback(null), 2500);
  };

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
    if (e) e.preventDefault();
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
      setFeedback({ type: 'success', message: `Voice Persona & Configuration for "${res.name}" saved successfully!` });
      setInitialState(JSON.parse(JSON.stringify(res)));
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
    const newEntry = { question: newFaqQ.trim(), answer: newFaqA.trim(), category: newFaqCategory || 'General' };
    const updatedFaqs = [...(editForm.faqs || []), newEntry];

    // Optimistic UI update
    setEditForm((prev) => ({ ...prev, faqs: updatedFaqs }));
    setNewFaqQ('');
    setNewFaqA('');
    setFaqSaving(true);

    try {
      const savedFaqs = await api.updateFaqs(editForm.id, updatedFaqs);
      setEditForm((prev) => ({ ...prev, faqs: savedFaqs }));
      setInitialState((prev) => ({ ...prev, faqs: savedFaqs }));
      if (onBusinessSaved) {
        onBusinessSaved({ ...business, faqs: savedFaqs });
      }
      setFeedback({ type: 'success', message: 'New FAQ saved directly to verified database!' });
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
      setInitialState((prev) => ({ ...prev, faqs: savedFaqs }));
      if (onBusinessSaved) {
        onBusinessSaved({ ...business, faqs: savedFaqs });
      }
      setFeedback({ type: 'success', message: 'FAQ removed from verified database!' });
      setTimeout(() => setFeedback(null), 3000);
    } catch (err) {
      setEditForm((prev) => ({ ...prev, faqs: previousFaqs }));
      setFeedback({ type: 'error', message: `Failed to delete FAQ: ${err.message}` });
    } finally {
      setFaqSaving(false);
    }
  };

  // Determine if business is currently open
  const isOpenNow = useMemo(() => {
    try {
      const now = new Date();
      const currentMinutes = now.getHours() * 60 + now.getMinutes();
      const [oH, oM] = (editForm.opening_time || '09:00').split(':').map(Number);
      const [cH, cM] = (editForm.closing_time || '21:00').split(':').map(Number);
      const openMinutes = oH * 60 + (oM || 0);
      const closeMinutes = cH * 60 + (cM || 0);
      return currentMinutes >= openMinutes && currentMinutes <= closeMinutes;
    } catch {
      return true;
    }
  }, [editForm.opening_time, editForm.closing_time]);

  return (
    <section className="main-content" aria-label="Receptionist & Business Settings" style={{ padding: '1.75rem 2rem 5rem' }}>
      {/* 1. Header with Breadcrumb Title */}
      <div className="section-header" style={{ marginBottom: '1.5rem' }}>
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
          <Building2 size={12} /> Persona & Knowledge Engine
        </div>
        <h1 className="section-title">Voice Persona & Knowledge Base</h1>
        <p className="section-subtitle">
          Configure operating hours, AI spoken voice prompts, deterministic safety rules, and verified FAQs for <strong>{business?.name || 'Your Business'}</strong>.
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
            background: feedback.type === 'success' ? 'rgba(16, 185, 129, 0.1)' : feedback.type === 'info' ? 'rgba(56, 189, 248, 0.1)' : 'rgba(244, 63, 94, 0.1)',
            color: feedback.type === 'success' ? 'var(--mint-400)' : feedback.type === 'info' ? '#38bdf8' : '#fb7185',
            border: `1px solid ${feedback.type === 'success' ? 'rgba(16, 185, 129, 0.25)' : feedback.type === 'info' ? 'rgba(56, 189, 248, 0.25)' : 'rgba(244, 63, 94, 0.25)'}`,
            fontWeight: 500,
            fontSize: '0.82rem',
          }}
          role="alert"
        >
          {feedback.type === 'success' ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
          <span>{feedback.message}</span>
        </div>
      )}

      {/* 2. Main Two-Column Workbench (Configuration on Left | Live Persona Telemetry on Right) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 340px',
          gap: '1.75rem',
          alignItems: 'start',
        }}
      >
        {/* Left Column: Form & Progressive Disclosure Tabs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Section Navigation Tabs */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-medium)',
              borderRadius: 'var(--radius-sm)',
              padding: '4px',
              overflowX: 'auto',
            }}
          >
            {[
              { id: 'profile', label: 'Profile & Hours', icon: Building2 },
              { id: 'voice', label: 'Voice & Greeting', icon: Bot },
              { id: 'escalation', label: 'Escalation Rules', icon: ShieldCheck },
              { id: 'faqs', label: 'Knowledge Base FAQs', icon: BookOpen },
            ].map((tab) => {
              const Icon = tab.icon;
              const isActive = activeSection === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveSection(tab.id)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.45rem',
                    padding: '0.45rem 0.85rem',
                    borderRadius: 'var(--radius-sm)',
                    background: isActive ? 'var(--bg-surface-elevated)' : 'transparent',
                    border: '1px solid',
                    borderColor: isActive ? 'var(--border-medium)' : 'transparent',
                    color: isActive ? 'var(--color-primary)' : 'var(--text-secondary)',
                    fontSize: '0.78rem',
                    fontWeight: isActive ? 600 : 500,
                    cursor: 'pointer',
                    transition: 'all var(--transition-fast)',
                    whiteSpace: 'nowrap',
                    boxShadow: isActive ? 'var(--specular-top)' : 'none',
                  }}
                >
                  <Icon size={13} style={{ color: isActive ? 'var(--color-primary)' : 'inherit' }} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* Tab 1: Profile & Operating Hours */}
          {activeSection === 'profile' && (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div style={{ borderBottom: '1px solid var(--border-medium)', paddingBottom: '0.75rem' }}>
                <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                  Business Profile & Operating Hours
                </h3>
                <p style={{ fontSize: '0.76rem', color: 'var(--text-tertiary)', margin: '4px 0 0' }}>
                  Define identity, inbound telephone DID line, and operating schedule.
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
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

              <div className="form-group">
                <label className="form-label">Business Description & Core Offerings</label>
                <textarea
                  className="form-textarea"
                  value={editForm.description || ''}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  rows={3}
                  placeholder="Summarize specialties, ambiance, locations, or primary services for caller Q&A..."
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
          )}

          {/* Tab 2: Voice Persona & Spoken Greeting */}
          {activeSection === 'voice' && (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div style={{ borderBottom: '1px solid var(--border-medium)', paddingBottom: '0.75rem' }}>
                <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                  Spoken Voice Persona & Natural Greeting
                </h3>
                <p style={{ fontSize: '0.76rem', color: 'var(--text-tertiary)', margin: '4px 0 0' }}>
                  The synthesized voice greeting delivered instantly when an incoming caller connects.
                </p>
              </div>

              <div className="form-group">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <label className="form-label" style={{ margin: 0 }}>Initial Spoken Greeting *</label>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                    {(editForm.greeting_message || '').length} characters
                  </span>
                </div>
                <textarea
                  className="form-textarea"
                  value={editForm.greeting_message || ''}
                  onChange={(e) => setEditForm({ ...editForm, greeting_message: e.target.value })}
                  rows={4}
                  required
                />
              </div>

              {/* Supported Spoken Languages */}
              <div className="form-group">
                <label className="form-label">Active Receptionist Languages</label>
                <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                  {['English', 'Hindi', 'Hinglish'].map((lang) => {
                    const isSelected = (editForm.languages || []).includes(lang);
                    return (
                      <button
                        key={lang}
                        type="button"
                        onClick={() => {
                          const current = editForm.languages || [];
                          const updated = isSelected ? current.filter((l) => l !== lang) : [...current, lang];
                          setEditForm({ ...editForm, languages: updated.length > 0 ? updated : ['English'] });
                        }}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '0.35rem 0.75rem',
                          borderRadius: 'var(--radius-sm)',
                          background: isSelected ? 'rgba(16, 185, 129, 0.15)' : 'var(--bg-surface-elevated)',
                          border: '1px solid',
                          borderColor: isSelected ? 'rgba(16, 185, 129, 0.4)' : 'var(--border-medium)',
                          color: isSelected ? 'var(--mint-400)' : 'var(--text-secondary)',
                          fontSize: '0.78rem',
                          cursor: 'pointer',
                        }}
                      >
                        {isSelected && <Check size={12} />}
                        <span>{lang}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Tab 3: Escalation & Human Staff Transfer */}
          {activeSection === 'escalation' && (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div style={{ borderBottom: '1px solid var(--border-medium)', paddingBottom: '0.75rem' }}>
                <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                  Deterministic Escalation & Staff Handoffs
                </h3>
                <p style={{ fontSize: '0.76rem', color: 'var(--text-tertiary)', margin: '4px 0 0' }}>
                  Safety policies that dictate when Answerly immediately transfers callers to human staff.
                </p>
              </div>

              <div className="form-group">
                <label className="form-label">Guarded Human Operator Transfer Policy</label>
                <textarea
                  className="form-textarea"
                  value={editForm.transfer_instructions || ''}
                  onChange={(e) => setEditForm({ ...editForm, transfer_instructions: e.target.value })}
                  rows={4}
                  placeholder="e.g. Transfer caller immediately if they ask for corporate banquets (>20 guests), private party catering, or have an urgent clinical escalation."
                />
              </div>
            </div>
          )}

          {/* Tab 4: Knowledge Base FAQs */}
          {activeSection === 'faqs' && (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div style={{ borderBottom: '1px solid var(--border-medium)', paddingBottom: '0.75rem' }}>
                <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                  Verified Knowledge Base FAQs ({(editForm.faqs || []).length})
                </h3>
                <p style={{ fontSize: '0.76rem', color: 'var(--text-tertiary)', margin: '4px 0 0' }}>
                  Grounded factual knowledge referenced deterministically by the receptionist model.
                </p>
              </div>

              {/* Add New FAQ Form */}
              <div
                style={{
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '1rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.75rem',
                }}
              >
                <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-primary)' }}>Add New Knowledge Base Q&A</div>
                <input
                  type="text"
                  placeholder="Question (e.g. What is your dress code? Do you offer valet?)"
                  className="form-input"
                  value={newFaqQ}
                  onChange={(e) => setNewFaqQ(e.target.value)}
                />
                <textarea
                  placeholder="Verified answer spoken by receptionist..."
                  className="form-textarea"
                  rows={2}
                  value={newFaqA}
                  onChange={(e) => setNewFaqA(e.target.value)}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={!newFaqQ.trim() || !newFaqA.trim() || faqSaving}
                    onClick={handleAddFaqToEdit}
                    style={{ padding: '0.35rem 0.85rem', fontSize: '0.76rem' }}
                  >
                    <Plus size={13} />
                    <span>{faqSaving ? 'Saving...' : 'Add Knowledge Entry'}</span>
                  </button>
                </div>
              </div>

              {/* FAQ List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                {(editForm.faqs || []).map((faq, index) => (
                  <div
                    key={index}
                    style={{
                      background: 'var(--bg-surface-elevated)',
                      border: '1px solid var(--border-medium)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '0.85rem 1rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      gap: '0.75rem',
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                        Q: {faq.question}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                        A: {faq.answer}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleRemoveFaqFromEdit(index)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--text-tertiary)',
                        cursor: 'pointer',
                        padding: '4px',
                      }}
                      title="Delete FAQ"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Live Spoken Persona Preview & Telemetry Card */}
        <aside style={{ position: 'sticky', top: '70px', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Spoken Persona Preview Card */}
          <div className="card" style={{ padding: '1.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                <Bot size={14} style={{ color: 'var(--mint-400)' }} />
                <span>Live Spoken Preview</span>
              </div>
              <button
                type="button"
                onClick={handleSimulateSpeech}
                title="Play simulated acoustic voice synthesis"
                style={{
                  background: simulatingSpeech ? 'rgba(16, 185, 129, 0.2)' : 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-full)',
                  padding: '2px 8px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '0.68rem',
                  fontFamily: 'var(--font-mono)',
                  color: simulatingSpeech ? 'var(--mint-400)' : 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                <Volume2 size={11} className={simulatingSpeech ? 'animate-pulse' : ''} />
                <span>{simulatingSpeech ? 'Playing...' : 'Play Audio'}</span>
              </button>
            </div>

            {/* Spoken Greeting Quote */}
            <div
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.85rem',
                fontSize: '0.8rem',
                color: 'var(--text-primary)',
                fontStyle: 'italic',
                lineHeight: 1.5,
                marginBottom: '1rem',
              }}
            >
              "{editForm.greeting_message || 'Welcome to our reception. How may I assist you today?'}"
            </div>

            {/* Operating Hours Real-Time Pill */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.74rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Operating Status:</span>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontFamily: 'var(--font-mono)',
                    color: isOpenNow ? 'var(--mint-400)' : 'var(--amber-400)',
                  }}
                >
                  <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: isOpenNow ? 'var(--mint-400)' : 'var(--amber-400)' }} />
                  {isOpenNow ? 'CURRENTLY OPEN' : 'CURRENTLY CLOSED'}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Schedule:</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {editForm.opening_time} – {editForm.closing_time}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Timezone:</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {editForm.timezone}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Knowledge Grounding:</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--mint-400)' }}>
                  {(editForm.faqs || []).length} Verified FAQs
                </span>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* 3. Sticky Bottom Save Bar (Shows Unsaved Status & Save Action) */}
      <div
        className="business-save-bar"
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          padding: '0.75rem 2rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          zIndex: 35,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          {isDirty ? (
            <span
              className="save-bar-status-dirty"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '0.78rem',
                fontFamily: 'var(--font-mono)',
              }}
            >
              <span style={{ width: '7px', height: '7px', borderRadius: '50%' }} />
              <span>Unsaved modifications detected</span>
            </span>
          ) : (
            <span
              className="save-bar-status-saved"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '0.78rem',
                fontFamily: 'var(--font-mono)',
              }}
            >
              <Check size={14} className="save-bar-check-icon" />
              <span>All changes saved to database</span>
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          {isDirty && (
            <button
              type="button"
              className="btn-secondary"
              onClick={handleDiscardChanges}
              style={{ padding: '0.4rem 0.85rem', fontSize: '0.78rem' }}
            >
              <RotateCcw size={13} />
              <span>Discard Changes</span>
            </button>
          )}

          <button
            type="button"
            className="btn-primary"
            onClick={handleUpdate}
            disabled={loading || !isDirty}
            style={{
              padding: '0.4rem 1.15rem',
              fontSize: '0.8rem',
              opacity: !isDirty && !loading ? 0.6 : 1,
              cursor: !isDirty && !loading ? 'default' : 'pointer',
            }}
          >
            <Save size={14} />
            <span>{loading ? 'Saving Configuration...' : 'Save Configuration'}</span>
          </button>
        </div>
      </div>
    </section>
  );
}
