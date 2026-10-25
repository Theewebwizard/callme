import React, { useState } from 'react';
import {
  PhoneCall,
  Sparkles,
  KeyRound,
  Building2,
  Phone,
  Clock,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Wrench,
  Bot,
} from 'lucide-react';
import { api } from '../api';

const INDUSTRY_OPTIONS = [
  'Restaurant',
  'Clinic',
  'Salon',
  'Astrology / Spiritual',
  'Consulting / Services',
  'Real Estate',
  'Retail / E-commerce',
  'Legal',
  'Other',
];

const PRE_EXISTING_TOOLS = [
  { id: 'lookup_faq', name: 'Answer Business FAQs', desc: 'Answers questions about hours, menus, prices, and policies using your knowledge base.' },
  { id: 'book_appointment', name: 'Book Appointments / Tables', desc: 'Schedules customer reservations with date, time, and party size confirmation.' },
  { id: 'take_message', name: 'Take Caller Messages', desc: 'Captures caller callback requests, contact details, and urgent voicemails.' },
  { id: 'transfer_call', name: 'Transfer to Staff', desc: 'Escalates to a human manager if the caller requests emergency attention.' },
];

export default function PortalGateway({ onEnterWorkspace, onEnterAdmin }) {
  const [mode, setMode] = useState('onboard'); // 'onboard', 'access', 'admin'
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [adminPasscode, setAdminPasscode] = useState('');

  // Access existing business state
  const [accessQuery, setAccessQuery] = useState('');

  // Onboard new business state
  const [name, setName] = useState('');
  const [industry, setIndustry] = useState('Restaurant');
  const [phone, setPhone] = useState('+919696967307');
  const [description, setDescription] = useState('');
  const [openTime, setOpenTime] = useState('09:00');
  const [closeTime, setCloseTime] = useState('21:00');
  const [timezone, setTimezone] = useState('Asia/Kolkata');
  const [greeting, setGreeting] = useState('');
  const [transferRules, setTransferRules] = useState(
    'Transfer call to human manager if caller asks for emergency personal attention or questions outside our services.'
  );
  const [selectedTools, setSelectedTools] = useState({
    lookup_faq: true,
    book_appointment: true,
    take_message: true,
    transfer_call: true,
  });

  const handleAccessSubmit = async (e) => {
    e.preventDefault();
    if (!accessQuery.trim()) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const match = await api.accessBusiness(accessQuery.trim());
      const full = await api.getBusiness(match.id);
      onEnterWorkspace(full);
    } catch (err) {
      setErrorMsg(err.message || 'Business workspace not found.');
    } finally {
      setLoading(false);
    }
  };

  const handleOnboardSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setErrorMsg('Business Name is required.');
      return;
    }
    setLoading(true);
    setErrorMsg(null);

    const greetingText =
      greeting.trim() ||
      `Namaste! Welcome to ${name.trim()}. I am your AI receptionist. How can I assist you today?`;

    const payload = {
      name: name.trim(),
      industry,
      phone_number: phone.trim(),
      description: description.trim(),
      opening_time: openTime.trim(),
      closing_time: closeTime.trim(),
      timezone,
      languages: ['English', 'Hindi'],
      greeting_message: greetingText,
      transfer_instructions: transferRules.trim(),
      enabled_tools: selectedTools,
      faqs: [],
    };

    try {
      const created = await api.createBusiness(payload);
      onEnterWorkspace(created);
    } catch (err) {
      setErrorMsg(err.message || 'Failed to create business.');
    } finally {
      setLoading(false);
    }
  };

  const toggleTool = (id) => {
    setSelectedTools((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(180deg, #f0f9ff 0%, #ffffff 100%)', display: 'flex', flexDirection: 'column' }}>
      {/* Top Simple Brand Header */}
      <header style={{ padding: '1.25rem 2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--slate-200)', background: 'white' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <div className="brand-icon">
            <PhoneCall size={20} strokeWidth={2.5} />
          </div>
          <div className="brand-text">
            Call<span>Me</span>
          </div>
        </div>
        <div style={{ fontSize: '0.85rem', color: 'var(--slate-500)', fontWeight: 600 }}>
          Dedicated Multi-Tenant AI Telephony Platform
        </div>
      </header>

      {/* Main Landing / Gateway */}
      <main style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2.5rem 1.5rem' }}>
        <div style={{ width: '100%', maxWidth: '820px' }}>
          {/* Hero Pitch */}
          <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                background: 'var(--sky-100)',
                color: 'var(--sky-800)',
                padding: '0.35rem 0.85rem',
                borderRadius: 'var(--radius-full)',
                fontSize: '0.82rem',
                fontWeight: 700,
                marginBottom: '1rem',
              }}
            >
              <Sparkles size={14} /> Autonomous AI Receptionists for Every Business
            </div>
            <h1 style={{ fontSize: '2.4rem', fontWeight: 800, color: 'var(--slate-900)', letterSpacing: '-0.03em', lineHeight: 1.2 }}>
              Deploy Your 24/7 Virtual Receptionist
            </h1>
            <p style={{ color: 'var(--slate-600)', fontSize: '1.05rem', marginTop: '0.5rem', maxWidth: '600px', margin: '0.5rem auto 0' }}>
              Create an autonomous conversational receptionist agent with pre-built booking, FAQ answers, and live phone routing.
            </p>
          </div>

          {/* Mode Switcher Tabs */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: '0.75rem', marginBottom: '1.75rem' }}>
            <button
              className={`btn-secondary ${mode === 'onboard' ? 'active' : ''}`}
              style={{
                background: mode === 'onboard' ? 'var(--sky-500)' : 'white',
                color: mode === 'onboard' ? 'white' : 'var(--slate-700)',
                borderColor: mode === 'onboard' ? 'var(--sky-500)' : 'var(--slate-300)',
                padding: '0.65rem 1.25rem',
                borderRadius: 'var(--radius-full)',
              }}
              onClick={() => { setMode('onboard'); setErrorMsg(null); }}
            >
              <Sparkles size={16} /> 🚀 Create Receptionist Agent
            </button>
            <button
              className={`btn-secondary ${mode === 'access' ? 'active' : ''}`}
              style={{
                background: mode === 'access' ? 'var(--sky-500)' : 'white',
                color: mode === 'access' ? 'white' : 'var(--slate-700)',
                borderColor: mode === 'access' ? 'var(--sky-500)' : 'var(--slate-300)',
                padding: '0.65rem 1.25rem',
                borderRadius: 'var(--radius-full)',
              }}
              onClick={() => { setMode('access'); setErrorMsg(null); }}
            >
              <KeyRound size={16} /> 🔑 Business Login
            </button>
            <button
              className={`btn-secondary ${mode === 'admin' ? 'active' : ''}`}
              style={{
                background: mode === 'admin' ? 'var(--slate-800)' : 'white',
                color: mode === 'admin' ? 'white' : 'var(--slate-700)',
                borderColor: mode === 'admin' ? 'var(--slate-800)' : 'var(--slate-300)',
                padding: '0.65rem 1.25rem',
                borderRadius: 'var(--radius-full)',
              }}
              onClick={() => { setMode('admin'); setErrorMsg(null); }}
            >
              <ShieldCheck size={16} /> 🛡️ Operator Admin
            </button>
          </div>

          {errorMsg && (
            <div
              style={{
                padding: '0.85rem 1.25rem',
                borderRadius: 'var(--radius-md)',
                marginBottom: '1.5rem',
                background: 'var(--rose-100)',
                color: 'var(--rose-700)',
                fontWeight: 600,
                fontSize: '0.88rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              <AlertCircle size={18} /> {errorMsg}
            </div>
          )}

          {/* =========================================================================
             MODE A: ACCESS EXISTING BUSINESS (NO DIRECTORY LEAK)
             ========================================================================= */}
          {mode === 'access' && (
            <div className="card" style={{ maxWidth: '520px', margin: '0 auto', padding: '2rem' }}>
              <div className="card-title">
                <KeyRound size={20} color="var(--sky-600)" /> Access Your Receptionist Workspace
              </div>
              <div className="card-desc">
                Enter your business name, tenant slug, or registered phone number to open your private dashboard.
              </div>

              <form onSubmit={handleAccessSubmit}>
                <div className="form-group" style={{ marginBottom: '1.25rem' }}>
                  <label className="form-label">Business Name or ID</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. haveli or +919696967307"
                    value={accessQuery}
                    onChange={(e) => setAccessQuery(e.target.value)}
                    required
                    style={{ padding: '0.75rem 1rem' }}
                  />
                  <span style={{ fontSize: '0.78rem', color: 'var(--slate-400)', marginTop: '4px' }}>
                    Tip: Enter <strong>haveli</strong> to access the registered business portal.
                  </span>
                </div>

                <button type="submit" className="btn-primary" disabled={loading} style={{ width: '100%', padding: '0.85rem' }}>
                  {loading ? 'Verifying...' : 'Open My Workspace'} <ArrowRight size={16} />
                </button>
              </form>
            </div>
          )}

          {/* =========================================================================
             MODE C: OPERATOR / ADMIN COMMAND CENTER
             ========================================================================= */}
          {mode === 'admin' && (
            <div className="card" style={{ maxWidth: '520px', margin: '0 auto', padding: '2rem', border: '2px solid var(--sky-400)' }}>
              <div className="card-title">
                <ShieldCheck size={22} color="var(--sky-600)" /> Operator Admin Command Center
              </div>
              <div className="card-desc">
                Access the cross-tenant admin overview, live agents fleet, user records, and master tool repository.
              </div>

              <div style={{ background: 'var(--sky-50)', padding: '1rem', borderRadius: 'var(--radius-sm)', marginBottom: '1.25rem', fontSize: '0.85rem', color: 'var(--sky-900)' }}>
                <strong>Platform Operator Privileges:</strong>
                <ul style={{ paddingLeft: '1.25rem', marginTop: '0.35rem', lineHeight: 1.5 }}>
                  <li>Monitor all registered receptionist agents live</li>
                  <li>Inspect tenant user profiles & operating schedules</li>
                  <li>Review master canonical tools repository and cross-agent usage</li>
                  <li>Manage custom tool demands and integrations queue</li>
                </ul>
              </div>

              <button
                type="button"
                className="btn-primary"
                onClick={onEnterAdmin}
                style={{ width: '100%', padding: '0.85rem', background: 'linear-gradient(135deg, #0284c7 0%, #0f172a 100%)' }}
              >
                <ShieldCheck size={16} /> Enter Admin Command Center <ArrowRight size={16} />
              </button>
            </div>
          )}

          {/* =========================================================================
             MODE B: CREATE RECEPTIONIST AGENT (ONBOARDING WIZARD)
             ========================================================================= */}
          {mode === 'onboard' && (
            <form onSubmit={handleOnboardSubmit} className="card" style={{ padding: '2rem' }}>
              {/* Step 1 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '1rem', borderBottom: '1px solid var(--slate-100)', paddingBottom: '0.75rem' }}>
                <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'var(--sky-500)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: '0.85rem' }}>
                  1
                </div>
                <div style={{ fontWeight: 800, fontSize: '1.1rem', color: 'var(--slate-900)' }}>
                  Business Identity & Telephony Line
                </div>
              </div>

              <div className="form-grid" style={{ marginBottom: '1.5rem' }}>
                <div className="form-group">
                  <label className="form-label">Business Trading Name *</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. Haveli Grand Restaurant"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Industry Category</label>
                  <select
                    className="form-select"
                    value={industry}
                    onChange={(e) => setIndustry(e.target.value)}
                  >
                    {INDUSTRY_OPTIONS.map((ind) => (
                      <option key={ind} value={ind}>{ind}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Assigned Inbound Phone Line (DID)</label>
                  <input
                    type="text"
                    className="form-input"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+91 95138 86363"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Operating Schedule (HH:MM)</label>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <input
                      type="text"
                      className="form-input"
                      value={openTime}
                      onChange={(e) => setOpenTime(e.target.value)}
                      style={{ width: '50%' }}
                    />
                    <input
                      type="text"
                      className="form-input"
                      value={closeTime}
                      onChange={(e) => setCloseTime(e.target.value)}
                      style={{ width: '50%' }}
                    />
                  </div>
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: '1.75rem' }}>
                <label className="form-label">What does your business offer? (Context for AI)</label>
                <textarea
                  className="form-textarea"
                  placeholder="e.g. North Indian dining, tandoor specials, family banquets, and online catering."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>

              {/* Step 2 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '1rem', borderBottom: '1px solid var(--slate-100)', paddingBottom: '0.75rem' }}>
                <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'var(--sky-500)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: '0.85rem' }}>
                  2
                </div>
                <div style={{ fontWeight: 800, fontSize: '1.1rem', color: 'var(--slate-900)' }}>
                  Virtual Receptionist Voice & Escalation
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: '1.25rem' }}>
                <label className="form-label">Receptionist Inbound Greeting Prompt</label>
                <textarea
                  className="form-textarea"
                  placeholder="Namaste! Welcome to our restaurant. I am your virtual host. How can I assist you with reservations or our menu today?"
                  value={greeting}
                  onChange={(e) => setGreeting(e.target.value)}
                />
                <span style={{ fontSize: '0.78rem', color: 'var(--slate-400)' }}>
                  Spoken automatically by the AI receptionist when a customer calls your phone line.
                </span>
              </div>

              <div className="form-group" style={{ marginBottom: '1.75rem' }}>
                <label className="form-label">Human Operator Transfer Policy</label>
                <textarea
                  className="form-textarea"
                  value={transferRules}
                  onChange={(e) => setTransferRules(e.target.value)}
                />
              </div>

              {/* Step 3 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '1rem', borderBottom: '1px solid var(--slate-100)', paddingBottom: '0.75rem' }}>
                <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'var(--sky-500)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: '0.85rem' }}>
                  3
                </div>
                <div style={{ fontWeight: 800, fontSize: '1.1rem', color: 'var(--slate-900)' }}>
                  Select Pre-Existing Receptionist Tools
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '0.75rem', marginBottom: '2rem' }}>
                {PRE_EXISTING_TOOLS.map((t) => {
                  const isChecked = selectedTools[t.id];
                  return (
                    <div
                      key={t.id}
                      onClick={() => toggleTool(t.id)}
                      style={{
                        border: isChecked ? '2px solid var(--sky-500)' : '1px solid var(--slate-200)',
                        background: isChecked ? 'var(--sky-50)' : 'white',
                        padding: '1rem',
                        borderRadius: 'var(--radius-md)',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: '0.75rem',
                        transition: 'var(--transition)',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}}
                        style={{ marginTop: '3px', accentColor: 'var(--sky-500)' }}
                      />
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--slate-900)' }}>
                          {t.name}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--slate-600)', marginTop: '2px' }}>
                          {t.desc}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <button type="submit" className="btn-primary" disabled={loading} style={{ width: '100%', padding: '0.95rem', fontSize: '1rem' }}>
                <Bot size={18} /> {loading ? 'Provisioning AI Receptionist...' : '🚀 Create & Launch AI Receptionist'}
              </button>
            </form>
          )}
        </div>
      </main>
    </div>
  );
}
