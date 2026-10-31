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
  Eye,
  EyeOff,
  UserCheck,
  Globe2,
  Cpu,
  Radio,
  Sliders,
  Terminal,
} from 'lucide-react';
import { api } from '../api';
import GoogleAuthModal, { GoogleIcon } from './GoogleAuthModal';
import InstallAppPrompt from './InstallAppPrompt';

const INDUSTRY_PREVIEWS = [
  {
    id: 'Restaurant',
    title: 'Restaurant & Dining',
    businessName: 'Spice Garden Bistro',
    phone: '+91 80 4123 5678',
    dialogue: [
      { speaker: 'caller', text: 'Namaste! Do you have a table for 4 tonight around 8 PM? Also is outdoor seating available?' },
      { speaker: 'receptionist', text: 'Namaste! Let me check our live table inventory for 4 guests at 8:00 PM tonight.' },
      { speaker: 'tool', text: '⚡ check_table_availability(party_size: 4, time: "20:00") → Table #12 (Cover 4, Patio Garden) Available' },
      { speaker: 'receptionist', text: 'We have a lovely table on our garden patio open at 8:00 PM. Shall I confirm this reservation under your name?' },
      { speaker: 'caller', text: 'Yes please, under Rohit Verma.' },
      { speaker: 'tool', text: '⚡ create_table_booking(name: "Rohit Verma", party_size: 4, time: "20:00") → Confirmed #BK-8821' },
      { speaker: 'receptionist', text: 'Your table is confirmed for 8:00 PM tonight, Rohit! A confirmation SMS has been dispatched. See you soon!' },
    ],
    tools: ['check_table_availability', 'create_table_booking', 'query_menu_pricing'],
    outcome: 'Booking Confirmed • Table #12',
  },
  {
    id: 'Hotel',
    title: 'Hotel & Hospitality',
    businessName: 'The Heritage Palace Resort',
    phone: '+91 294 245 9900',
    dialogue: [
      { speaker: 'caller', text: 'Hi, I would like to book a Deluxe Suite for 2 nights starting this Friday. Does it include breakfast?' },
      { speaker: 'receptionist', text: 'Hello! Let me check suite availability and our weekend package rates for this Friday.' },
      { speaker: 'tool', text: '⚡ check_room_availability(room_type: "Deluxe Suite", check_in: "2026-11-06", nights: 2) → Room #304 Open' },
      { speaker: 'receptionist', text: 'Our Lake-View Deluxe Suite is available for 2 nights. Complimentary buffet breakfast and airport transfers are fully included.' },
      { speaker: 'caller', text: 'Wonderful, please reserve it.' },
      { speaker: 'tool', text: '⚡ book_hotel_stay(room: "Deluxe Suite", nights: 2, guest: "Ananya Roy") → Reservation #HT-4091' },
      { speaker: 'receptionist', text: 'Done! Your stay is locked in. We have sent the check-in voucher and directions to your number.' },
    ],
    tools: ['check_room_availability', 'book_hotel_stay', 'inquire_amenities'],
    outcome: 'Reservation Confirmed • Deluxe Suite #304',
  },
  {
    id: 'Clinic',
    title: 'Clinic & Healthcare',
    businessName: 'Apex Multi-Specialty Clinic',
    phone: '+91 11 4982 7100',
    dialogue: [
      { speaker: 'caller', text: 'Hello, is Dr. Sharma available for a cardiology consultation tomorrow afternoon?' },
      { speaker: 'receptionist', text: 'Good day! Let me inspect Dr. Sharma’s appointment schedule for tomorrow afternoon.' },
      { speaker: 'tool', text: '⚡ query_doctor_schedule(doctor: "Dr. Sharma", specialty: "Cardiology", date: "Tomorrow") → 15:30 Open' },
      { speaker: 'receptionist', text: 'Dr. Sharma has an open consultation slot at 3:30 PM tomorrow. Would that work for you?' },
      { speaker: 'caller', text: 'Yes, 3:30 PM works. My chest feels slightly heavy.' },
      { speaker: 'tool', text: '⚡ safety_triage_check(symptom: "chest heavy") → Alert: High Priority Escalation' },
      { speaker: 'receptionist', text: 'I am immediately securing your 3:30 PM slot, and I am also transferring you directly to our duty nurse for preliminary triage.' },
    ],
    tools: ['query_doctor_schedule', 'book_consultation', 'safety_triage_transfer'],
    outcome: 'Consultation Slotted & Triage Transferred',
  },
  {
    id: 'Salon',
    title: 'Salon & Wellness',
    businessName: 'Aura Luxury Spa & Salon',
    phone: '+91 22 2640 8812',
    dialogue: [
      { speaker: 'caller', text: 'Hi! Can I get an appointment with Priya for a hair spa and styling this Saturday at 11 AM?' },
      { speaker: 'receptionist', text: 'Hi there! Let me verify Priya’s chair schedule for Saturday morning.' },
      { speaker: 'tool', text: '⚡ check_stylist_slots(stylist: "Priya", service: "Hair Spa", date: "Saturday", time: "11:00") → Confirmed Open' },
      { speaker: 'receptionist', text: 'Priya is available at 11:00 AM this Saturday. The treatment takes approximately 75 minutes. Shall I book it?' },
      { speaker: 'caller', text: 'Yes please!' },
      { speaker: 'tool', text: '⚡ schedule_service_appointment(stylist: "Priya", service: "Hair Spa", date: "Saturday") → Booked #SL-1904' },
      { speaker: 'receptionist', text: 'You are all set with Priya for Saturday at 11:00 AM! Looking forward to pampering you.' },
    ],
    tools: ['check_stylist_slots', 'schedule_service_appointment', 'service_catalog'],
    outcome: 'Appointment Booked • Stylist Priya',
  },
];

export default function LandingPage({ onEnterWorkspace, onEnterAdmin }) {
  // Auth state
  const [authRole, setAuthRole] = useState('business'); // 'business' | 'admin'
  const [businessAuthMode, setBusinessAuthMode] = useState('login'); // 'login' | 'register'
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  // Active industry tab for hero simulation
  const [activeIndustryId, setActiveIndustryId] = useState('Restaurant');
  const activePreview = INDUSTRY_PREVIEWS.find((p) => p.id === activeIndustryId) || INDUSTRY_PREVIEWS[0];

  // Google OAuth modal
  const [googleModalOpen, setGoogleModalOpen] = useState(false);
  const [googleModalMode, setGoogleModalMode] = useState('signin');

  const handleOpenGoogle = (mode = 'signin') => {
    setGoogleModalMode(mode);
    setGoogleModalOpen(true);
    setErrorMsg(null);
  };

  // Business Login state
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);

  // Business Register state
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [showRegPassword, setShowRegPassword] = useState(false);
  const [name, setName] = useState('');
  const [industry, setIndustry] = useState('Restaurant');
  const [phone, setPhone] = useState('+919696967307');
  const [openTime, setOpenTime] = useState('09:00');
  const [closeTime, setCloseTime] = useState('21:00');

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

  const handleAutoFillDemoBusiness = () => {
    setLoginEmail('haveli.restaurant@gmail.com');
    setLoginPassword('haveli123');
    setErrorMsg(null);
  };

  const handleAutoFillDemoAdmin = () => {
    setAdminPasscode('admin');
    setErrorMsg(null);
  };

  const handleBusinessLogin = async (e) => {
    e.preventDefault();
    if (!loginEmail.trim() || !loginPassword.trim()) {
      setErrorMsg('Please enter both Email ID and Password.');
      return;
    }
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await api.loginBusiness(loginEmail.trim(), loginPassword.trim());
      if (res && res.business) {
        localStorage.setItem(
          'callme_google_user',
          JSON.stringify({
            email: loginEmail.trim().toLowerCase(),
            name: res.business.owner_name || res.business.name,
            avatarInitial: loginEmail.trim()[0].toUpperCase(),
          })
        );
        onEnterWorkspace(res.business);
      }
    } catch (err) {
      setErrorMsg(err.message || 'Invalid credentials. Please verify your login.');
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
      setErrorMsg('Email ID is required.');
      return;
    }
    if (!regPassword.trim() || regPassword.trim().length < 4) {
      setErrorMsg('Password must be at least 4 characters.');
      return;
    }
    setLoading(true);
    setErrorMsg(null);

    const payload = {
      name: name.trim(),
      industry,
      phone_number: phone.trim(),
      description: `${industry} business front-desk.`,
      opening_time: openTime.trim(),
      closing_time: closeTime.trim(),
      timezone: 'Asia/Kolkata',
      languages: ['English', 'Hindi'],
      greeting_message: `Namaste! Welcome to ${name.trim()}. How can I assist you today?`,
      transfer_instructions: 'Transfer to staff when caller requests emergency or management assistance.',
      owner_email: regEmail.trim().toLowerCase(),
      owner_name: name.trim(),
      password: regPassword.trim(),
      enabled_tools: {
        lookup_faq: true,
        book_appointment: true,
        take_message: true,
        transfer_call: true,
      },
      faqs: [],
    };

    try {
      const created = await api.createBusiness(payload);
      localStorage.setItem(
        'callme_google_user',
        JSON.stringify({
          email: regEmail.trim().toLowerCase(),
          name: name.trim(),
          avatarInitial: regEmail.trim()[0].toUpperCase(),
        })
      );
      onEnterWorkspace(created);
    } catch (err) {
      setErrorMsg(err.message || 'Failed to provision business receptionist.');
    } finally {
      setLoading(false);
    }
  };

  const handleAdminLogin = (e) => {
    e.preventDefault();
    localStorage.setItem('callme_admin_key', adminPasscode.trim() || 'admin');
    onEnterAdmin();
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-app)', color: 'var(--text-primary)', display: 'flex', flexDirection: 'column' }}>
      {/* 1. Sticky Navigation Bar */}
      <header className="landing-nav" role="banner">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <div className="brand-icon" title="CallMe AI Voice Platform">
            <PhoneCall size={16} strokeWidth={2.5} />
          </div>
          <span style={{ fontWeight: 700, fontSize: '1.05rem', letterSpacing: '-0.03em', color: '#ffffff' }}>
            Call<span style={{ color: 'var(--text-secondary)' }}>Me</span>
          </span>
          <span
            style={{
              fontSize: '0.72rem',
              fontFamily: 'var(--font-mono)',
              background: 'var(--bg-surface-elevated)',
              border: '1px solid var(--border-subtle)',
              padding: '2px 7px',
              borderRadius: 'var(--radius-full)',
              color: 'var(--text-secondary)',
            }}
          >
            v2.4
          </span>
        </div>

        <nav className="landing-nav-links" aria-label="Main Navigation">
          <a href="#overview">Product</a>
          <a href="#industries">Industries</a>
          <a href="#capabilities">Capabilities</a>
          <a href="#auth-section">Access Portal</a>
        </nav>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <button
            type="button"
            className="landing-btn-secondary"
            style={{ padding: '0.35rem 0.85rem', fontSize: '0.8rem' }}
            onClick={() => scrollToAuth('admin')}
          >
            <ShieldCheck size={13} />
            <span>Operator Access</span>
          </button>
          <button
            type="button"
            className="landing-btn-primary"
            style={{ padding: '0.35rem 0.95rem', fontSize: '0.8rem' }}
            onClick={() => scrollToAuth('business', 'login')}
          >
            <span>Launch Console</span>
            <ArrowRight size={13} />
          </button>
        </div>
      </header>

      {/* 2. Hero Section */}
      <section className="landing-hero" id="overview">
        {/* Subtle Status Pill */}
        <div className="landing-badge">
          <span className="pulse-dot" />
          <span>AUTONOMOUS INBOUND VOICE TELEPHONY • ZERO HUMAN INTERVENTION</span>
        </div>

        {/* Product-First Headline */}
        <h1 className="landing-title">
          Your front desk, handled.<br />
          <span>An AI receptionist that actually sounds human.</span>
        </h1>

        <p className="landing-subtitle">
          Picks up on the first ring. Answers caller questions using your verified business knowledge base, checks live room or table availability, confirms reservations, and guards your business 24/7.
        </p>

        {/* Action CTAs */}
        <div className="landing-cta-group">
          <button
            type="button"
            className="landing-btn-primary"
            onClick={() => scrollToAuth('business', 'register')}
          >
            <Sparkles size={16} />
            <span>Provision AI Receptionist</span>
          </button>

          <button
            type="button"
            className="landing-btn-secondary"
            onClick={() => scrollToAuth('business', 'login')}
          >
            <KeyRound size={15} />
            <span>Sign In to Console</span>
          </button>
        </div>

        {/* 3. Interactive Product Hero Mockup (Raycast Style) */}
        <div className="call-simulation-container" id="industries">
          {/* Header Bar */}
          <div className="call-simulation-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              <span
                style={{
                  width: '7px',
                  height: '7px',
                  borderRadius: '50%',
                  background: 'var(--mint-500)',
                  boxShadow: '0 0 8px rgba(16, 185, 129, 0.7)',
                }}
              />
              <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#ffffff', fontFamily: 'var(--font-mono)' }}>
                {activePreview.businessName} • {activePreview.phone}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span
                style={{
                  fontSize: '0.72rem',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--mint-400)',
                  background: 'rgba(16, 185, 129, 0.1)',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                  padding: '2px 7px',
                  borderRadius: '4px',
                }}
              >
                RTT: 280ms
              </span>
              <span
                style={{
                  fontSize: '0.72rem',
                  color: 'var(--text-tertiary)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                LIVE WEBRTC
              </span>
            </div>
          </div>

          {/* Industry Switcher Segmented Bar */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.75rem 1.25rem',
              borderBottom: '1px solid var(--border-subtle)',
              background: 'var(--bg-card)',
              overflowX: 'auto',
            }}
          >
            <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-tertiary)', marginRight: '0.25rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Industry Mode:
            </span>
            {INDUSTRY_PREVIEWS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setActiveIndustryId(p.id)}
                style={{
                  padding: '0.25rem 0.65rem',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid',
                  borderColor: activeIndustryId === p.id ? 'var(--border-strong)' : 'var(--border-subtle)',
                  background: activeIndustryId === p.id ? 'var(--bg-surface-elevated)' : 'transparent',
                  color: activeIndustryId === p.id ? '#ffffff' : 'var(--text-secondary)',
                  fontSize: '0.76rem',
                  fontWeight: 500,
                  cursor: 'pointer',
                  transition: 'all var(--transition-fast)',
                  whiteSpace: 'nowrap',
                }}
              >
                {p.title}
              </button>
            ))}
          </div>

          {/* Body: Live Streaming Dialogue & Tool Traces */}
          <div className="call-simulation-body">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {activePreview.dialogue.map((turn, idx) => {
                if (turn.speaker === 'tool') {
                  return (
                    <div
                      key={idx}
                      style={{
                        alignSelf: 'center',
                        background: 'var(--bg-surface-elevated)',
                        border: '1px solid var(--border-medium)',
                        padding: '0.45rem 0.85rem',
                        borderRadius: 'var(--radius-full)',
                        fontSize: '0.74rem',
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--mint-400)',
                        boxShadow: 'var(--specular-top)',
                      }}
                    >
                      {turn.text}
                    </div>
                  );
                }

                const isCaller = turn.speaker === 'caller';
                return (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: isCaller ? 'flex-start' : 'flex-end',
                      maxWidth: '85%',
                      alignSelf: isCaller ? 'flex-start' : 'flex-end',
                    }}
                  >
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginBottom: '3px' }}>
                      {isCaller ? 'Incoming Caller' : `${activePreview.businessName} Receptionist`}
                    </div>
                    <div
                      style={{
                        background: isCaller ? 'var(--bg-surface-elevated)' : '#ffffff',
                        color: isCaller ? 'var(--text-primary)' : '#07080a',
                        border: isCaller ? '1px solid var(--border-subtle)' : 'none',
                        padding: '0.65rem 0.95rem',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.84rem',
                        lineHeight: 1.5,
                        fontWeight: isCaller ? 400 : 500,
                      }}
                    >
                      {turn.text}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Confirmed Resolution Card */}
            <div
              style={{
                marginTop: '0.5rem',
                background: 'rgba(16, 185, 129, 0.08)',
                border: '1px solid rgba(16, 185, 129, 0.25)',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-sm)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <CheckCircle2 size={16} style={{ color: 'var(--mint-400)' }} />
                <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#ffffff' }}>
                  Session Outcome: {activePreview.outcome}
                </span>
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--mint-400)', fontFamily: 'var(--font-mono)' }}>
                DISPATCHED 0.4s
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* 4. Product Capabilities Matrix */}
      <section
        id="capabilities"
        style={{
          maxWidth: '1100px',
          margin: '0 auto',
          padding: '4rem 1.5rem',
          width: '100%',
          boxSizing: 'border-box',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
          <h2 style={{ fontSize: '2rem', fontWeight: 700, letterSpacing: '-0.03em', color: '#ffffff', marginBottom: '0.6rem' }}>
            Engineered for enterprise telecommunications
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem', maxWidth: '580px', margin: '0 auto' }}>
            Built specifically to solve real customer inquiries, scheduling constraints, and front-desk bottlenecks.
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.25rem' }}>
          <div className="card">
            <div className="stat-icon" style={{ marginBottom: '1rem' }}>
              <Radio size={18} />
            </div>
            <div className="card-title">Acoustic Turn Latency</div>
            <p className="card-desc">
              Bidirectional streaming architecture picks up speech, detects pauses, and answers in under 380ms without awkward lag.
            </p>
          </div>

          <div className="card">
            <div className="stat-icon" style={{ marginBottom: '1rem' }}>
              <Calendar size={18} />
            </div>
            <div className="card-title">Calendar & Inventory Truth</div>
            <p className="card-desc">
              Checks live room, table, or clinic inventory before confirming bookings. Prevents double bookings autonomously.
            </p>
          </div>

          <div className="card">
            <div className="stat-icon" style={{ marginBottom: '1rem' }}>
              <ShieldCheck size={18} />
            </div>
            <div className="card-title">Deterministic Escalation</div>
            <p className="card-desc">
              Guarded policy triggers transfer high-stakes calls, VIP guests, or emergency medical triage instantly to human staff.
            </p>
          </div>

          <div className="card">
            <div className="stat-icon" style={{ marginBottom: '1rem' }}>
              <Globe2 size={18} />
            </div>
            <div className="card-title">Native Bilingual Speech</div>
            <p className="card-desc">
              Fluent in English and Hindi with natural regional accents, colloquial understanding, and seamless code-switching.
            </p>
          </div>
        </div>
      </section>

      {/* 5. Clean Access Portal / Auth Card */}
      <section
        id="auth-section"
        style={{
          maxWidth: '520px',
          margin: '0 auto 6rem',
          padding: '0 1.5rem',
          width: '100%',
          boxSizing: 'border-box',
        }}
      >
        <div className="card" style={{ padding: '2rem 1.75rem' }}>
          {/* Role Tabs: Business vs Operator */}
          <div
            style={{
              display: 'flex',
              background: 'var(--bg-surface-elevated)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '3px',
              marginBottom: '1.5rem',
            }}
          >
            <button
              type="button"
              onClick={() => {
                setAuthRole('business');
                setErrorMsg(null);
              }}
              style={{
                flex: 1,
                padding: '0.45rem',
                borderRadius: 'var(--radius-xs)',
                border: 'none',
                background: authRole === 'business' ? 'var(--bg-card)' : 'transparent',
                color: authRole === 'business' ? '#ffffff' : 'var(--text-secondary)',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all var(--transition-fast)',
              }}
            >
              Business Console
            </button>
            <button
              type="button"
              onClick={() => {
                setAuthRole('admin');
                setErrorMsg(null);
              }}
              style={{
                flex: 1,
                padding: '0.45rem',
                borderRadius: 'var(--radius-xs)',
                border: 'none',
                background: authRole === 'admin' ? 'var(--bg-card)' : 'transparent',
                color: authRole === 'admin' ? '#ffffff' : 'var(--text-secondary)',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all var(--transition-fast)',
              }}
            >
              Operator Portal
            </button>
          </div>

          {errorMsg && (
            <div
              style={{
                background: 'rgba(244, 63, 94, 0.1)',
                border: '1px solid rgba(244, 63, 94, 0.3)',
                color: '#fb7185',
                padding: '0.65rem 0.85rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.8rem',
                marginBottom: '1.25rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              <AlertCircle size={14} />
              <span>{errorMsg}</span>
            </div>
          )}

          {authRole === 'business' ? (
            <>
              {/* Business Mode Switcher: Sign In vs Register */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#ffffff' }}>
                  {businessAuthMode === 'login' ? 'Business Sign In' : 'Provision New Receptionist'}
                </h3>
                <button
                  type="button"
                  onClick={() => {
                    setBusinessAuthMode(businessAuthMode === 'login' ? 'register' : 'login');
                    setErrorMsg(null);
                  }}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--text-secondary)',
                    fontSize: '0.78rem',
                    cursor: 'pointer',
                    textDecoration: 'underline',
                  }}
                >
                  {businessAuthMode === 'login' ? 'Create new workspace' : 'Have an account? Sign In'}
                </button>
              </div>

              {/* 1-Click Demo Fill Button */}
              {businessAuthMode === 'login' && (
                <div
                  style={{
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-subtle)',
                    padding: '0.65rem 0.85rem',
                    borderRadius: 'var(--radius-sm)',
                    marginBottom: '1.25rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                    Evaluating? Use demo credentials:
                  </span>
                  <button
                    type="button"
                    onClick={handleAutoFillDemoBusiness}
                    style={{
                      padding: '0.25rem 0.6rem',
                      borderRadius: 'var(--radius-xs)',
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border-medium)',
                      color: '#ffffff',
                      fontSize: '0.74rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    1-Click Autofill
                  </button>
                </div>
              )}

              {/* Google Sign-in Option */}
              <button
                type="button"
                onClick={() => handleOpenGoogle(businessAuthMode === 'login' ? 'signin' : 'signup')}
                style={{
                  width: '100%',
                  padding: '0.6rem',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-medium)',
                  color: '#ffffff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.6rem',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  marginBottom: '1rem',
                  transition: 'all var(--transition-fast)',
                }}
              >
                <GoogleIcon size={16} />
                <span>Continue with Google</span>
              </button>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  margin: '1rem 0',
                  color: 'var(--text-tertiary)',
                  fontSize: '0.72rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                <span style={{ flex: 1, height: '1px', background: 'var(--border-subtle)' }} />
                <span>or email</span>
                <span style={{ flex: 1, height: '1px', background: 'var(--border-subtle)' }} />
              </div>

              {businessAuthMode === 'login' ? (
                <form onSubmit={handleBusinessLogin} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  <div className="form-group">
                    <label className="form-label">Email ID</label>
                    <input
                      type="email"
                      value={loginEmail}
                      onChange={(e) => setLoginEmail(e.target.value)}
                      placeholder="business@example.com"
                      className="form-input"
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Password</label>
                    <input
                      type="password"
                      value={loginPassword}
                      onChange={(e) => setLoginPassword(e.target.value)}
                      placeholder="••••••••"
                      className="form-input"
                      required
                    />
                  </div>

                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={loading}
                    style={{ width: '100%', padding: '0.65rem', marginTop: '0.5rem' }}
                  >
                    {loading ? 'Authenticating...' : 'Enter Business Workspace'}
                  </button>
                </form>
              ) : (
                <form onSubmit={handleBusinessRegister} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  <div className="form-group">
                    <label className="form-label">Business Name</label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. Haveli Grand Restaurant"
                      className="form-input"
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Industry Domain</label>
                    <select
                      value={industry}
                      onChange={(e) => setIndustry(e.target.value)}
                      className="form-select"
                    >
                      <option value="Restaurant">Restaurant & Dining</option>
                      <option value="Hotel">Hotel & Hospitality</option>
                      <option value="Clinic">Clinic & Healthcare</option>
                      <option value="Salon">Salon & Wellness</option>
                      <option value="Other">General Service Business</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Inbound Phone DID</label>
                    <input
                      type="text"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      className="form-input"
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Email Address</label>
                    <input
                      type="email"
                      value={regEmail}
                      onChange={(e) => setRegEmail(e.target.value)}
                      placeholder="owner@example.com"
                      className="form-input"
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Create Password</label>
                    <input
                      type="password"
                      value={regPassword}
                      onChange={(e) => setRegPassword(e.target.value)}
                      placeholder="At least 4 characters"
                      className="form-input"
                      required
                    />
                  </div>

                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={loading}
                    style={{ width: '100%', padding: '0.65rem', marginTop: '0.5rem' }}
                  >
                    {loading ? 'Deploying Receptionist...' : 'Deploy 24/7 AI Receptionist'}
                  </button>
                </form>
              )}
            </>
          ) : (
            <>
              {/* Operator Portal Mode */}
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#ffffff', marginBottom: '0.45rem' }}>
                Platform Operator Console
              </h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>
                Supervisory access for fleet telephony telemetry and tenant management.
              </p>

              <div
                style={{
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-subtle)',
                  padding: '0.65rem 0.85rem',
                  borderRadius: 'var(--radius-sm)',
                  marginBottom: '1.25rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                  Evaluation Passcode:
                </span>
                <button
                  type="button"
                  onClick={handleAutoFillDemoAdmin}
                  style={{
                    padding: '0.25rem 0.6rem',
                    borderRadius: 'var(--radius-xs)',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-medium)',
                    color: '#ffffff',
                    fontSize: '0.74rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Autofill "admin"
                </button>
              </div>

              <form onSubmit={handleAdminLogin} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                <div className="form-group">
                  <label className="form-label">Operator Passcode</label>
                  <input
                    type="password"
                    value={adminPasscode}
                    onChange={(e) => setAdminPasscode(e.target.value)}
                    placeholder="Enter operator key"
                    className="form-input"
                    required
                  />
                </div>

                <button
                  type="submit"
                  className="btn-primary"
                  style={{ width: '100%', padding: '0.65rem', marginTop: '0.5rem' }}
                >
                  Authenticate Operator
                </button>
              </form>
            </>
          )}
        </div>
      </section>

      {/* 6. Polished Dark Footer */}
      <footer
        style={{
          borderTop: '1px solid var(--border-subtle)',
          padding: '2.5rem 2rem',
          maxWidth: '1100px',
          margin: '0 auto',
          width: '100%',
          boxSizing: 'border-box',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
          fontSize: '0.78rem',
          color: 'var(--text-tertiary)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <div className="brand-icon" style={{ width: 22, height: 22 }}>
            <PhoneCall size={12} strokeWidth={2.5} />
          </div>
          <span style={{ color: '#ffffff', fontWeight: 600 }}>CallMe Platform</span>
          <span>© 2026. All rights reserved.</span>
        </div>

        <div style={{ display: 'flex', gap: '1.25rem' }}>
          <span>English & Hindi Telephony Engine</span>
          <span>WebRTC Low-Latency Voice</span>
          <span>Multi-Tenant Architecture</span>
        </div>
      </footer>

      {/* Google OAuth Modal */}
      <GoogleAuthModal
        isOpen={googleModalOpen}
        onClose={() => setGoogleModalOpen(false)}
        mode={googleModalMode}
        onSuccess={(biz) => onEnterWorkspace(biz)}
      />
    </div>
  );
}
