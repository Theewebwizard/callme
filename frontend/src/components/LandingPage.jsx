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
  Wrench,
  Bot,
  Calendar,
  MessageSquare,
  HelpCircle,
  Zap,
  Activity,
  Layers,
  Lock,
  Headphones,
  Check,
  Mail,
} from 'lucide-react';
import { api } from '../api';
import GoogleAuthModal, { GoogleIcon } from './GoogleAuthModal';

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

const PRE_EXISTING_TOOLS = [
  {
    id: 'lookup_faq',
    name: 'Answer Business FAQs',
    desc: 'Answers questions about hours, menus, prices, and policies using your knowledge base.',
    icon: HelpCircle,
  },
  {
    id: 'book_appointment',
    name: 'Book Appointments / Tables',
    desc: 'Schedules customer reservations with date, time, and party size confirmation.',
    icon: Calendar,
  },
  {
    id: 'take_message',
    name: 'Take Caller Messages',
    desc: 'Captures caller callback requests, contact details, and urgent voicemails.',
    icon: MessageSquare,
  },
  {
    id: 'transfer_call',
    name: 'Transfer to Staff',
    desc: 'Escalates to a human manager if the caller requests emergency attention.',
    icon: Headphones,
  },
];

export default function LandingPage({ onEnterWorkspace, onEnterAdmin }) {
  // Auth state
  const [authRole, setAuthRole] = useState('business'); // 'business' | 'admin'
  const [businessAuthMode, setBusinessAuthMode] = useState('login'); // 'login' | 'register'
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  // Google OAuth / Gmail modal state
  const [googleModalOpen, setGoogleModalOpen] = useState(false);
  const [googleModalMode, setGoogleModalMode] = useState('signin'); // 'signin' | 'signup'

  const handleOpenGoogle = (mode = 'signin') => {
    setGoogleModalMode(mode);
    setGoogleModalOpen(true);
    setErrorMsg(null);
  };

  const handleGoogleSuccess = (biz, googleUser) => {
    onEnterWorkspace(biz);
  };

  // Business Login state (Gmail ID + Password)
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);

  // Business Register state (Gmail ID + Password + Profile)
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [showRegPassword, setShowRegPassword] = useState(false);
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

  // Admin login state
  const [adminPasscode, setAdminPasscode] = useState('');

  const scrollToAuth = (role = 'business', mode = 'login') => {
    setAuthRole(role);
    if (role === 'business') {
      setBusinessAuthMode(mode);
    }
    const el = document.getElementById('auth-section');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const handleBusinessLogin = async (e) => {
    e.preventDefault();
    if (!loginEmail.trim() || !loginPassword.trim()) {
      setErrorMsg('Please enter both Gmail / Email ID and Password.');
      return;
    }
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await api.loginBusiness(loginEmail.trim(), loginPassword.trim());
      if (res && res.business) {
        localStorage.setItem('callme_google_user', JSON.stringify({
          email: loginEmail.trim().toLowerCase(),
          name: res.business.owner_name || res.business.name,
          avatarInitial: (loginEmail.trim())[0].toUpperCase(),
        }));
        onEnterWorkspace(res.business);
      }
    } catch (err) {
      setErrorMsg(err.message || 'Invalid Gmail ID or password. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleBusinessRegister = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setErrorMsg('Business Name is required.');
      return;
    }
    if (!regEmail.trim()) {
      setErrorMsg('Gmail / Email ID is required for account login & DB registration.');
      return;
    }
    if (!regPassword.trim() || regPassword.trim().length < 4) {
      setErrorMsg('Password must be at least 4 characters long.');
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
      owner_email: regEmail.trim().toLowerCase(),
      owner_name: name.trim(),
      password: regPassword.trim(),
      enabled_tools: selectedTools,
      faqs: [],
    };

    try {
      const created = await api.createBusiness(payload);
      localStorage.setItem('callme_google_user', JSON.stringify({
        email: regEmail.trim().toLowerCase(),
        name: name.trim(),
        avatarInitial: (regEmail.trim())[0].toUpperCase(),
      }));
      onEnterWorkspace(created);
    } catch (err) {
      setErrorMsg(err.message || 'Failed to create business profile.');
    } finally {
      setLoading(false);
    }
  };

  const handleAdminLogin = (e) => {
    e.preventDefault();
    // Admin access allowed for platform operators
    onEnterAdmin();
  };

  const toggleTool = (id) => {
    setSelectedTools((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div style={{ minHeight: '100vh', background: '#ffffff', color: 'var(--slate-800)', display: 'flex', flexDirection: 'column' }}>
      {/* =========================================================================
         1. STICKY TOP NAVBAR
         ========================================================================= */}
      <header className="landing-nav">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <div className="brand-icon">
            <PhoneCall size={20} strokeWidth={2.5} />
          </div>
          <div className="brand-text">
            Call<span>Me</span>
          </div>
          <span style={{ fontSize: '0.72rem', background: 'var(--sky-100)', color: 'var(--sky-800)', padding: '2px 8px', borderRadius: '12px', fontWeight: 700, marginLeft: '4px' }}>
            AI Receptionist
          </span>
        </div>

        <nav className="landing-nav-links">
          <a href="#how-it-works">How It Works</a>
          <a href="#features">Features</a>
          <a href="#architecture">Architecture</a>
          <a href="#tools">Tools</a>
          <a href="#auth-section">Sign In</a>
        </nav>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button
            className="btn-secondary"
            style={{ padding: '0.45rem 0.9rem', fontSize: '0.82rem', borderRadius: 'var(--radius-full)' }}
            onClick={() => scrollToAuth('admin')}
          >
            <ShieldCheck size={14} /> Admin
          </button>
          <button
            className="btn-primary"
            style={{ padding: '0.5rem 1.1rem', fontSize: '0.85rem', borderRadius: 'var(--radius-full)' }}
            onClick={() => scrollToAuth('business', 'register')}
          >
            Deploy Receptionist <ArrowRight size={14} />
          </button>
        </div>
      </header>

      {/* =========================================================================
         2. HERO SECTION
         ========================================================================= */}
      <section className="landing-hero" id="overview">
        <div className="landing-badge">
          <Sparkles size={14} /> Next-Generation Inbound Voice AI
        </div>

        <h1 className="landing-title">
          Never Miss a Customer Call Again. <span>Deploy Your AI Receptionist.</span>
        </h1>

        <p className="landing-subtitle">
          An autonomous virtual receptionist that picks up on ring one, answers questions using your business knowledge,
          books appointments, and transfers critical calls to your team — 24 hours a day, 7 days a week.
        </p>

        <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', flexWrap: 'wrap', marginBottom: '3.5rem' }}>
          <button
            className="btn-primary"
            style={{ padding: '0.85rem 1.85rem', fontSize: '1rem', borderRadius: 'var(--radius-full)' }}
            onClick={() => scrollToAuth('business', 'register')}
          >
            <Bot size={18} /> Launch Your AI Receptionist
          </button>
          <button
            className="btn-secondary"
            style={{ padding: '0.85rem 1.65rem', fontSize: '1rem', borderRadius: 'var(--radius-full)' }}
            onClick={() => scrollToAuth('business', 'login')}
          >
            <KeyRound size={17} /> Business Sign In
          </button>
        </div>

        {/* Live Call Voice Simulation Showcase Card */}
        <div
          style={{
            maxWidth: '780px',
            margin: '0 auto',
            background: 'white',
            border: '1px solid var(--sky-200)',
            borderRadius: 'var(--radius-xl)',
            boxShadow: '0 20px 40px -15px rgba(14, 165, 233, 0.2)',
            overflow: 'hidden',
            textAlign: 'left',
          }}
        >
          {/* Header of Call Simulation */}
          <div
            style={{
              background: 'linear-gradient(90deg, #0284c7 0%, #0ea5e9 100%)',
              padding: '0.85rem 1.25rem',
              color: 'white',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', fontWeight: 700 }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#4ade80', display: 'inline-block', animation: 'pulse 1.5s infinite' }}></span>
              Live Simulated Inbound Call • Inbound DID: +91 96969 67307
            </div>
            <div style={{ fontSize: '0.78rem', background: 'rgba(255,255,255,0.2)', padding: '2px 8px', borderRadius: '6px' }}>
              ⚡ 420ms Latency
            </div>
          </div>

          {/* Conversation simulation body */}
          <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem', background: 'var(--slate-50)' }}>
            {/* Caller Message */}
            <div style={{ display: 'flex', gap: '0.75rem', maxWidth: '80%' }}>
              <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'var(--slate-200)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', fontWeight: 800, flexShrink: 0 }}>
                👤
              </div>
              <div style={{ background: 'white', border: '1px solid var(--slate-200)', padding: '0.75rem 1rem', borderRadius: 'var(--radius-md)', fontSize: '0.9rem', color: 'var(--slate-800)', boxShadow: 'var(--shadow-sm)' }}>
                "Namaste! Do you have a table for 4 guests tonight around 8:00 PM?"
              </div>
            </div>

            {/* Receptionist Message */}
            <div style={{ display: 'flex', gap: '0.75rem', maxWidth: '85%', alignSelf: 'flex-end', flexDirection: 'row-reverse' }}>
              <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'var(--sky-500)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <Bot size={18} />
              </div>
              <div style={{ background: 'var(--sky-600)', color: 'white', padding: '0.75rem 1rem', borderRadius: 'var(--radius-md)', fontSize: '0.9rem', boxShadow: '0 4px 12px rgba(2, 132, 199, 0.25)' }}>
                "Namaste! Yes, we have availability for 4 guests at 8:00 PM. Shall I confirm this reservation under your name, or do you have any dietary preferences?"
              </div>
            </div>

            {/* Tool Triggered Pill */}
            <div style={{ alignSelf: 'center', background: 'var(--sky-50)', border: '1px solid var(--sky-200)', color: 'var(--sky-800)', padding: '0.35rem 0.85rem', borderRadius: 'var(--radius-full)', fontSize: '0.78rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Zap size={13} color="var(--sky-600)" /> Tool Executed: <code>book_appointment(guests=4, time="20:00")</code>
            </div>
          </div>
        </div>

        {/* High Impact Numbers Strip */}
        <div style={{ maxWidth: '980px', margin: '0 auto' }}>
          <div className="stats-bar">
            <div className="stat-item">
              <div className="stat-number sky">100%</div>
              <div className="stat-desc">Calls Answered on Ring 1</div>
            </div>
            <div className="stat-item">
              <div className="stat-number">&lt; 500ms</div>
              <div className="stat-desc">Neural Voice Response Latency</div>
            </div>
            <div className="stat-item">
              <div className="stat-number sky">24/7</div>
              <div className="stat-desc">Uninterrupted Availability</div>
            </div>
            <div className="stat-item">
              <div className="stat-number">EN + HI</div>
              <div className="stat-desc">Bilingual English & Hindi</div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
         3. HOW IT WORKS SECTION
         ========================================================================= */}
      <section className="landing-section" id="how-it-works">
        <div style={{ textAlign: 'center' }}>
          <div className="section-tag">
            <Layers size={14} /> Seamless Setup
          </div>
          <h2 style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--slate-900)', letterSpacing: '-0.02em' }}>
            How CallMe Works for Your Business
          </h2>
          <p style={{ color: 'var(--slate-600)', fontSize: '1.05rem', maxWidth: '600px', margin: '0.5rem auto 0' }}>
            Go from zero to a live autonomous phone receptionist in four simple steps.
          </p>
        </div>

        <div className="steps-grid">
          <div className="step-card">
            <div className="step-num">1</div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--slate-900)' }}>
              Claim or Forward DID Line
            </h3>
            <p style={{ fontSize: '0.9rem', color: 'var(--slate-600)', lineHeight: 1.5 }}>
              Assign a dedicated virtual phone number or forward your existing commercial mobile/landline to your CallMe line.
            </p>
          </div>

          <div className="step-card">
            <div className="step-num">2</div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--slate-900)' }}>
              Train Your Knowledge Base
            </h3>
            <p style={{ fontSize: '0.9rem', color: 'var(--slate-600)', lineHeight: 1.5 }}>
              Upload your operating hours, menu, service pricing, clinic doctors, and FAQs in simple plain text.
            </p>
          </div>

          <div className="step-card">
            <div className="step-num">3</div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--slate-900)' }}>
              Select Pre-Built Tools
            </h3>
            <p style={{ fontSize: '0.9rem', color: 'var(--slate-600)', lineHeight: 1.5 }}>
              Toggle appointment bookings, message taking, and smart staff transfers. Request custom tools anytime.
            </p>
          </div>

          <div className="step-card">
            <div className="step-num">4</div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--slate-900)' }}>
              Autonomous 24/7 Coverage
            </h3>
            <p style={{ fontSize: '0.9rem', color: 'var(--slate-600)', lineHeight: 1.5 }}>
              CallMe answers every caller instantly, executes actions, and writes call logs and transcripts directly to your portal.
            </p>
          </div>
        </div>
      </section>

      {/* =========================================================================
         4. CORE CAPABILITIES / FEATURES
         ========================================================================= */}
      <section className="landing-section" id="features" style={{ background: 'var(--slate-50)', borderRadius: 'var(--radius-xl)', padding: '4rem 2rem' }}>
        <div style={{ textAlign: 'center' }}>
          <div className="section-tag">
            <Sparkles size={14} /> Core Capabilities
          </div>
          <h2 style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--slate-900)', letterSpacing: '-0.02em' }}>
            Built Specifically for Inbound Customer Calls
          </h2>
          <p style={{ color: 'var(--slate-600)', fontSize: '1.05rem', maxWidth: '640px', margin: '0.5rem auto 0' }}>
            Everything your front-desk needs without hiring additional staff or missing high-intent callers.
          </p>
        </div>

        <div className="feature-grid">
          <div className="feature-card">
            <div className="feature-icon-box">
              <Phone size={24} />
            </div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--slate-900)' }}>
              24/7 Zero-Hold Inbound Reception
            </h3>
            <p style={{ fontSize: '0.88rem', color: 'var(--slate-600)', lineHeight: 1.5 }}>
              Never send a customer to voicemail or leave them on hold. Inbound calls are answered in under 2 seconds with a warm, natural greeting.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon-box">
              <Calendar size={24} />
            </div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--slate-900)' }}>
              Automated Table & Appointment Booking
            </h3>
            <p style={{ fontSize: '0.88rem', color: 'var(--slate-600)', lineHeight: 1.5 }}>
              Collects party size, dates, and times, performs conflict checks, and books reservations directly into your schedule.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon-box">
              <HelpCircle size={24} />
            </div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--slate-900)' }}>
              Dynamic Business FAQ Answers
            </h3>
            <p style={{ fontSize: '0.88rem', color: 'var(--slate-600)', lineHeight: 1.5 }}>
              Answers questions regarding pricing, menu options, parking, dietary needs, or doctor availability accurately without hallucinating.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon-box">
              <MessageSquare size={24} />
            </div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--slate-900)' }}>
              Smart Caller Message & Voicemail
            </h3>
            <p style={{ fontSize: '0.88rem', color: 'var(--slate-600)', lineHeight: 1.5 }}>
              Captures caller name, phone number, and inquiry urgency so you and your team can follow up promptly with full context.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon-box">
              <Headphones size={24} />
            </div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--slate-900)' }}>
              Guarded Human Staff Escalation
            </h3>
            <p style={{ fontSize: '0.88rem', color: 'var(--slate-600)', lineHeight: 1.5 }}>
              Seamlessly transfers callers to a human staff manager when emergency medical, VIP, or complex personal situations arise.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon-box">
              <Lock size={24} />
            </div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--slate-900)' }}>
              Strict Multi-Tenant Isolation
            </h3>
            <p style={{ fontSize: '0.88rem', color: 'var(--slate-600)', lineHeight: 1.5 }}>
              Each business is sandboxed in its own workspace. Businesses cannot view other tenants, ensuring full privacy and data security.
            </p>
          </div>
        </div>
      </section>

      {/* =========================================================================
         5. REAL-TIME AI VOICE ARCHITECTURE
         ========================================================================= */}
      <section className="landing-section" id="architecture">
        <div style={{ textAlign: 'center' }}>
          <div className="section-tag">
            <Activity size={14} /> Production Telephony Pipeline
          </div>
          <h2 style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--slate-900)', letterSpacing: '-0.02em' }}>
            Ultra-Low Latency Conversational Voice Engine
          </h2>
          <p style={{ color: 'var(--slate-600)', fontSize: '1.05rem', maxWidth: '640px', margin: '0.5rem auto 0' }}>
            Built with modular LangGraph state management, RMS voice activity detection, Faster-Whisper, and Microsoft Edge Neural Voice.
          </p>
        </div>

        <div className="arch-flow">
          <div className="arch-node">
            📞 Inbound Telephony (DID)
          </div>
          <div className="arch-arrow">➔</div>
          <div className="arch-node">
            🎙️ RMS VAD (Speech/Silence Detect)
          </div>
          <div className="arch-arrow">➔</div>
          <div className="arch-node">
            📝 Faster-Whisper STT
          </div>
          <div className="arch-arrow">➔</div>
          <div className="arch-node" style={{ background: 'var(--sky-100)', borderColor: 'var(--sky-400)' }}>
            🧠 LangGraph Orchestrator & Tools
          </div>
          <div className="arch-arrow">➔</div>
          <div className="arch-node">
            🔊 Edge-TTS Neural Voice
          </div>
          <div className="arch-arrow">➔</div>
          <div className="arch-node">
            👂 Caller Speaker Output
          </div>
        </div>
      </section>

      {/* =========================================================================
         6. MODULAR TOOLS & FEATURE DEMANDS
         ========================================================================= */}
      <section className="landing-section" id="tools" style={{ borderTop: '1px solid var(--slate-100)' }}>
        <div style={{ textAlign: 'center' }}>
          <div className="section-tag">
            <Wrench size={14} /> Tool Ecosystem
          </div>
          <h2 style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--slate-900)', letterSpacing: '-0.02em' }}>
            Pre-Existing Tools & Custom Feature Demands
          </h2>
          <p style={{ color: 'var(--slate-600)', fontSize: '1.05rem', maxWidth: '640px', margin: '0.5rem auto 0' }}>
            Choose from standard built-in tools or request custom integrations tailored to your business software.
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.25rem', marginTop: '2.5rem' }}>
          {PRE_EXISTING_TOOLS.map((t) => {
            const Icon = t.icon;
            return (
              <div key={t.id} style={{ background: 'white', border: '1px solid var(--sky-200)', borderRadius: 'var(--radius-lg)', padding: '1.5rem', boxShadow: 'var(--shadow-sm)' }}>
                <div style={{ width: '40px', height: '40px', borderRadius: 'var(--radius-md)', background: 'var(--sky-50)', color: 'var(--sky-600)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem' }}>
                  <Icon size={20} />
                </div>
                <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--slate-900)', marginBottom: '0.35rem' }}>{t.name}</h4>
                <p style={{ fontSize: '0.82rem', color: 'var(--slate-600)', lineHeight: 1.4 }}>{t.desc}</p>
                <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--emerald-600)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Check size={14} /> Pre-Built & Instant
                </div>
              </div>
            );
          })}
        </div>

        {/* Custom Demand Highlight Card */}
        <div style={{ background: 'linear-gradient(135deg, var(--sky-50) 0%, #ffffff 100%)', border: '1px solid var(--sky-200)', borderRadius: 'var(--radius-lg)', padding: '1.75rem 2rem', marginTop: '2rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1.25rem' }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: '1.1rem', color: 'var(--slate-900)', marginBottom: '0.25rem' }}>
              ✨ Need a Custom Tool or Third-Party Integration?
            </div>
            <div style={{ fontSize: '0.88rem', color: 'var(--slate-600)', maxWidth: '640px' }}>
              Want your receptionist to push bookings into OpenTable, Petpooja, Google Calendar, or your proprietary CRM?
              Businesses can submit feature demands directly inside their dashboard with live status tracking.
            </div>
          </div>
          <button
            className="btn-primary"
            style={{ padding: '0.65rem 1.25rem', fontSize: '0.88rem' }}
            onClick={() => scrollToAuth('business', 'register')}
          >
            Deploy & Request Tools <ArrowRight size={15} />
          </button>
        </div>
      </section>

      {/* =========================================================================
         7. AUTHENTICATION & REGISTRATION SECTION (AT BOTTOM)
         ========================================================================= */}
      <section className="auth-section" id="auth-section">
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
          <div className="section-tag">
            <Lock size={14} /> Platform Access
          </div>
          <h2 style={{ fontSize: '2.4rem', fontWeight: 800, color: 'var(--slate-900)', letterSpacing: '-0.02em' }}>
            Access Your Receptionist Platform
          </h2>
          <p style={{ color: 'var(--slate-600)', fontSize: '1.05rem', maxWidth: '600px', margin: '0.5rem auto 0' }}>
            Sign in to manage your private receptionist workspace, register a new business, or access platform administrative fleet oversight.
          </p>
        </div>

        <div className="auth-container">
          {/* Dual Role Selector Tabs */}
          <div className="auth-role-tabs">
            <button
              type="button"
              className={`auth-role-tab ${authRole === 'business' ? 'active' : ''}`}
              onClick={() => {
                setAuthRole('business');
                setErrorMsg(null);
              }}
            >
              <Building2 size={16} /> 🏢 Business Portal
            </button>
            <button
              type="button"
              className={`auth-role-tab ${authRole === 'admin' ? 'active admin' : ''}`}
              onClick={() => {
                setAuthRole('admin');
                setErrorMsg(null);
              }}
            >
              <ShieldCheck size={16} /> 🛡️ Platform Administrator
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
             ROLE 1: BUSINESS PORTAL (SIGN IN OR REGISTER)
             ========================================================================= */}
          {authRole === 'business' && (
            <div>
              {/* Secondary Switch: Login vs Register */}
              <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginBottom: '1.75rem' }}>
                <button
                  type="button"
                  className={`btn-secondary ${businessAuthMode === 'login' ? 'active' : ''}`}
                  style={{
                    background: businessAuthMode === 'login' ? 'var(--sky-500)' : 'white',
                    color: businessAuthMode === 'login' ? 'white' : 'var(--slate-700)',
                    borderColor: businessAuthMode === 'login' ? 'var(--sky-500)' : 'var(--slate-300)',
                    padding: '0.5rem 1.25rem',
                    borderRadius: 'var(--radius-full)',
                    fontSize: '0.85rem',
                    fontWeight: 700,
                  }}
                  onClick={() => { setBusinessAuthMode('login'); setErrorMsg(null); }}
                >
                  <KeyRound size={15} /> Sign In to Workspace
                </button>
                <button
                  type="button"
                  className={`btn-secondary ${businessAuthMode === 'register' ? 'active' : ''}`}
                  style={{
                    background: businessAuthMode === 'register' ? 'var(--sky-500)' : 'white',
                    color: businessAuthMode === 'register' ? 'white' : 'var(--slate-700)',
                    borderColor: businessAuthMode === 'register' ? 'var(--sky-500)' : 'var(--slate-300)',
                    padding: '0.5rem 1.25rem',
                    borderRadius: 'var(--radius-full)',
                    fontSize: '0.85rem',
                    fontWeight: 700,
                  }}
                  onClick={() => { setBusinessAuthMode('register'); setErrorMsg(null); }}
                >
                  <Sparkles size={15} /> Register New Business
                </button>
              </div>

              {/* Business Sign In Form */}
              {businessAuthMode === 'login' && (
                <div>
                  <div style={{ marginBottom: '1.25rem' }}>
                    <div style={{ fontWeight: 700, fontSize: '1.1rem', color: 'var(--slate-900)', marginBottom: '0.25rem' }}>
                      Sign In to Your Receptionist Workspace
                    </div>
                    <div style={{ fontSize: '0.85rem', color: 'var(--slate-600)' }}>
                      Enter your registered Gmail ID and password to access your isolated workspace.
                    </div>
                  </div>

                  <form onSubmit={handleBusinessLogin}>
                    <div className="form-group" style={{ marginBottom: '1rem' }}>
                      <label className="form-label">Gmail / Email ID *</label>
                      <div style={{ position: 'relative' }}>
                        <Mail size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--slate-400)' }} />
                        <input
                          type="email"
                          className="form-input"
                          placeholder="e.g. yourname@gmail.com or haveli.restaurant@gmail.com"
                          value={loginEmail}
                          onChange={(e) => setLoginEmail(e.target.value)}
                          required
                          style={{ paddingLeft: '38px', paddingRight: '12px' }}
                        />
                      </div>
                    </div>

                    <div className="form-group" style={{ marginBottom: '1.25rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <label className="form-label" style={{ marginBottom: 0 }}>Password *</label>
                        <button
                          type="button"
                          onClick={() => setShowLoginPassword(!showLoginPassword)}
                          style={{ background: 'none', border: 'none', color: 'var(--sky-600)', fontSize: '0.78rem', cursor: 'pointer', fontWeight: 600 }}
                        >
                          {showLoginPassword ? 'Hide Password' : 'Show Password'}
                        </button>
                      </div>
                      <div style={{ position: 'relative', marginTop: '4px' }}>
                        <Lock size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--slate-400)' }} />
                        <input
                          type={showLoginPassword ? 'text' : 'password'}
                          className="form-input"
                          placeholder="Enter your account password"
                          value={loginPassword}
                          onChange={(e) => setLoginPassword(e.target.value)}
                          required
                          style={{ paddingLeft: '38px', paddingRight: '12px' }}
                        />
                      </div>
                      <span style={{ fontSize: '0.78rem', color: 'var(--slate-500)', marginTop: '6px', display: 'block' }}>
                        💡 Demo Business Login: <strong>haveli.restaurant@gmail.com</strong> | Password: <strong>haveli123</strong>
                      </span>
                    </div>

                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={loading}
                      style={{ width: '100%', padding: '0.85rem', fontSize: '0.95rem' }}
                    >
                      {loading ? 'Authenticating...' : 'Sign In to Workspace'} <ArrowRight size={16} />
                    </button>
                  </form>

                  <div className="auth-divider">or 1-click continue with Google</div>

                  {/* 1-Click Google Sign In */}
                  <button
                    type="button"
                    className="btn-google"
                    onClick={() => handleOpenGoogle('signin')}
                    disabled={loading}
                  >
                    <GoogleIcon size={19} /> Sign In with Google
                  </button>
                </div>
              )}

              {/* Business Register Form */}
              {businessAuthMode === 'register' && (
                <div>
                  <div style={{ marginBottom: '1.25rem', borderBottom: '1px solid var(--slate-100)', paddingBottom: '0.75rem' }}>
                    <div style={{ fontWeight: 800, fontSize: '1.15rem', color: 'var(--slate-900)' }}>
                      Register Business & Provision AI Receptionist
                    </div>
                    <div style={{ fontSize: '0.85rem', color: 'var(--slate-600)' }}>
                      Create your credentials and setup your business receptionist in 3 easy steps.
                    </div>
                  </div>

                  <form onSubmit={handleBusinessRegister}>
                    {/* Security & Login Credentials Card */}
                    <div style={{ background: 'var(--sky-50)', border: '1px solid var(--sky-200)', padding: '1.1rem 1.25rem', borderRadius: 'var(--radius-md)', marginBottom: '1.5rem' }}>
                      <div style={{ fontWeight: 800, fontSize: '0.88rem', color: 'var(--sky-900)', marginBottom: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Lock size={15} color="var(--sky-600)" />
                        ACCOUNT CREDENTIALS (STORED SECURELY IN DATABASE FOR SIGNIN)
                      </div>

                      <div className="form-grid" style={{ marginBottom: 0 }}>
                        <div className="form-group">
                          <label className="form-label">Gmail / Email ID *</label>
                          <div style={{ position: 'relative' }}>
                            <Mail size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--slate-400)' }} />
                            <input
                              type="email"
                              className="form-input"
                              placeholder="e.g. owner@gmail.com"
                              value={regEmail}
                              onChange={(e) => setRegEmail(e.target.value)}
                              required
                              style={{ paddingLeft: '38px', background: 'white' }}
                            />
                          </div>
                        </div>

                        <div className="form-group">
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <label className="form-label" style={{ marginBottom: 0 }}>Account Password *</label>
                            <button
                              type="button"
                              onClick={() => setShowRegPassword(!showRegPassword)}
                              style={{ background: 'none', border: 'none', color: 'var(--sky-700)', fontSize: '0.75rem', cursor: 'pointer', fontWeight: 600 }}
                            >
                              {showRegPassword ? 'Hide' : 'Show'}
                            </button>
                          </div>
                          <div style={{ position: 'relative', marginTop: '4px' }}>
                            <Lock size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--slate-400)' }} />
                            <input
                              type={showRegPassword ? 'text' : 'password'}
                              className="form-input"
                              placeholder="Create password (min 4 chars)"
                              value={regPassword}
                              onChange={(e) => setRegPassword(e.target.value)}
                              required
                              style={{ paddingLeft: '38px', background: 'white' }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Step 1 */}
                    <div style={{ fontSize: '0.88rem', fontWeight: 800, color: 'var(--sky-700)', marginBottom: '0.75rem' }}>
                      STEP 1: BUSINESS IDENTITY & TELEPHONY LINE
                    </div>

                  <div className="form-grid" style={{ marginBottom: '1.25rem' }}>
                    <div className="form-group">
                      <label className="form-label">Business Name *</label>
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
                      <label className="form-label">Assigned Phone Line (DID)</label>
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

                  <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                    <label className="form-label">Business Description & Services</label>
                    <textarea
                      className="form-textarea"
                      placeholder="e.g. Fine dining Indian cuisine, banquet bookings, tandoor specials, open 7 days."
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={2}
                    />
                  </div>

                  {/* Step 2 */}
                  <div style={{ fontSize: '0.88rem', fontWeight: 800, color: 'var(--sky-700)', marginBottom: '0.75rem' }}>
                    STEP 2: VOICE GREETING & ESCALATION RULES
                  </div>

                  <div className="form-group" style={{ marginBottom: '1.25rem' }}>
                    <label className="form-label">Spoken Receptionist Inbound Greeting</label>
                    <textarea
                      className="form-textarea"
                      placeholder="Namaste! Welcome to our restaurant. I am your AI receptionist. How may I assist you today?"
                      value={greeting}
                      onChange={(e) => setGreeting(e.target.value)}
                      rows={2}
                    />
                  </div>

                  <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                    <label className="form-label">Human Operator Transfer Policy</label>
                    <textarea
                      className="form-textarea"
                      value={transferRules}
                      onChange={(e) => setTransferRules(e.target.value)}
                      rows={2}
                    />
                  </div>

                  {/* Step 3 */}
                  <div style={{ fontSize: '0.88rem', fontWeight: 800, color: 'var(--sky-700)', marginBottom: '0.75rem' }}>
                    STEP 3: SELECT PRE-EXISTING TOOLS
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.65rem', marginBottom: '1.75rem' }}>
                    {PRE_EXISTING_TOOLS.map((t) => {
                      const isChecked = selectedTools[t.id];
                      return (
                        <div
                          key={t.id}
                          onClick={() => toggleTool(t.id)}
                          style={{
                            border: isChecked ? '2px solid var(--sky-500)' : '1px solid var(--slate-200)',
                            background: isChecked ? 'var(--sky-50)' : 'white',
                            padding: '0.85rem',
                            borderRadius: 'var(--radius-md)',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '0.65rem',
                            transition: 'var(--transition)',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => {}}
                            style={{ marginTop: '2px', accentColor: 'var(--sky-500)' }}
                          />
                          <div>
                            <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--slate-900)' }}>
                              {t.name}
                            </div>
                            <div style={{ fontSize: '0.76rem', color: 'var(--slate-600)', marginTop: '2px', lineHeight: 1.3 }}>
                              {t.desc}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={loading}
                    style={{ width: '100%', padding: '0.95rem', fontSize: '1rem' }}
                  >
                    <Bot size={18} /> {loading ? 'Provisioning AI Receptionist...' : '🚀 Create & Launch AI Receptionist'}
                  </button>
                </form>
              </div>
            )}
            </div>
          )}

          {/* =========================================================================
             ROLE 2: PLATFORM ADMINISTRATOR (SUPERVISORY ONLY - STRICT ISOLATION)
             ========================================================================= */}
          {authRole === 'admin' && (
            <div>
              <div style={{ marginBottom: '1.25rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 800, fontSize: '1.15rem', color: 'var(--slate-900)' }}>
                  <ShieldCheck size={20} color="var(--sky-600)" /> Platform Operator Admin Access
                </div>
                <div style={{ fontSize: '0.85rem', color: 'var(--slate-600)', marginTop: '2px' }}>
                  Supervisory overview for live agent fleet metrics, user profiles, master tool catalog, and feature demands.
                </div>
              </div>

              {/* Security Isolation Notice - STRICT REQUIREMENT */}
              <div
                style={{
                  background: '#f8fafc',
                  border: '1px solid var(--sky-200)',
                  borderRadius: 'var(--radius-md)',
                  padding: '1rem',
                  marginBottom: '1.5rem',
                  fontSize: '0.82rem',
                  color: 'var(--slate-700)',
                  lineHeight: 1.5,
                }}
              >
                <div style={{ fontWeight: 800, color: 'var(--sky-800)', display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.35rem' }}>
                  <Lock size={15} color="var(--sky-600)" /> Strict Tenant Security Policy Enforced
                </div>
                Platform Administrators operate in supervisory mode. For security and privacy compliance, <strong>admins can NEVER sign in as or impersonate a business user workspace</strong>. All business data remains isolated to the tenant.
              </div>

              <form onSubmit={handleAdminLogin}>
                <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                  <label className="form-label">Operator Passcode / Access Key</label>
                  <input
                    type="password"
                    className="form-input"
                    placeholder="Enter operator access key (e.g. admin)"
                    value={adminPasscode}
                    onChange={(e) => setAdminPasscode(e.target.value)}
                    style={{ padding: '0.85rem 1rem' }}
                  />
                  <span style={{ fontSize: '0.78rem', color: 'var(--slate-500)', marginTop: '4px' }}>
                    Default development access: leave blank or type <strong>admin</strong>.
                  </span>
                </div>

                <button
                  type="submit"
                  className="btn-primary"
                  style={{
                    width: '100%',
                    padding: '0.85rem',
                    fontSize: '0.95rem',
                    background: 'linear-gradient(135deg, #0284c7 0%, #0f172a 100%)',
                  }}
                >
                  <ShieldCheck size={16} /> Enter Admin Command Center <ArrowRight size={16} />
                </button>
              </form>
            </div>
          )}
        </div>
      </section>

      {/* Google OAuth & Gmail Interactive Modal */}
      <GoogleAuthModal
        isOpen={googleModalOpen}
        onClose={() => setGoogleModalOpen(false)}
        mode={googleModalMode}
        onSuccess={handleGoogleSuccess}
      />

      {/* =========================================================================
         8. MODERN MINIMALISTIC FOOTER
         ========================================================================= */}
      <footer style={{ borderTop: '1px solid var(--slate-200)', background: 'white', padding: '2.5rem 2rem', textAlign: 'center', fontSize: '0.85rem', color: 'var(--slate-500)' }}>
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
          <div className="brand-icon" style={{ width: '28px', height: '28px' }}>
            <PhoneCall size={16} strokeWidth={2.5} />
          </div>
          <strong style={{ color: 'var(--slate-900)', fontSize: '1rem' }}>CallMe AI Telephony Platform</strong>
        </div>
        <p style={{ margin: '0 0 0.5rem 0' }}>
          Autonomous 24/7 Virtual Receptionists for Modern Businesses. Powered by LangGraph, Faster-Whisper, and Edge-TTS.
        </p>
        <div style={{ display: 'flex', justifyContent: 'center', gap: '1.5rem', fontSize: '0.8rem', color: 'var(--slate-400)' }}>
          <span>© 2026 CallMe Inc.</span>
          <span>•</span>
          <span>Strict Multi-Tenant Isolation</span>
          <span>•</span>
          <span>Production Telephony Architecture</span>
        </div>
      </footer>
    </div>
  );
}
