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
  Bot,
  Calendar,
  MessageSquare,
  Zap,
  Globe2,
  Eye,
  EyeOff,
} from 'lucide-react';
import { api } from '../api';
import GoogleAuthModal, { GoogleIcon } from './GoogleAuthModal';
import InstallAppPrompt from './InstallAppPrompt';
import AmbientAuroraField from './AmbientAuroraField';
import HeroCallPreview from './HeroCallPreview';
import MetricsSocialProofStrip from './MetricsSocialProofStrip';
import AgentPersonasSection from './AgentPersonasSection';
import AgentWorkflowSection from './AgentWorkflowSection';
import FeatureGridSection from './FeatureGridSection';
import ConfigConsoleSection from './ConfigConsoleSection';
import useScrollReveal from './useScrollReveal';
import ThemeToggle from './ThemeToggle';

export const INDUSTRY_PREVIEWS = [
  {
    id: 'Dental',
    title: 'Dental & Clinic',
    businessName: 'Bright Smile Dental',
    phone: '+1 (555) 392-8100',
    dialogue: [
      { speaker: 'caller', text: 'Hi, can I book a cleaning for Friday?' },
      { speaker: 'receptionist', text: 'Of course! I have 10:30 AM or 3:00 PM open on Friday. Which works best?' },
      { speaker: 'tool', text: '⚡ check_hygienist_slots(service: "Cleaning", date: "Friday") → 10:30 AM, 3:00 PM Available' },
      { speaker: 'caller', text: '10:30 AM sounds perfect, thank you!' },
      { speaker: 'receptionist', text: 'You are all set for Friday at 10:30 AM with Dr. Taylor! A confirmation SMS has been dispatched.' },
    ],
    tools: ['check_hygienist_slots', 'book_dental_appointment', 'send_sms_confirmation'],
    outcome: 'Appointment booked · Fri 10:30 AM · SMS sent',
  },
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
    outcome: 'Booking Confirmed • Table #12 • SMS sent',
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
    outcome: 'Reservation Confirmed • Deluxe Suite #304 • SMS sent',
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
    outcome: 'Appointment Booked • Stylist Priya • SMS sent',
  },
];

export default function LandingPage({ onEnterWorkspace, onEnterAdmin }) {
  // Auth state
  const [authRole, setAuthRole] = useState('business'); // 'business' | 'admin'
  const [businessAuthMode, setBusinessAuthMode] = useState('login'); // 'login' | 'register'
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  // Active industry tab for hero simulation
  const [activeIndustryId, setActiveIndustryId] = useState('Dental');
  const [callCycle, setCallCycle] = useState(0);
  const activePreview = INDUSTRY_PREVIEWS.find((p) => p.id === activeIndustryId) || INDUSTRY_PREVIEWS[0];

  // Initialize IntersectionObserver scroll reveals
  useScrollReveal('.reveal-on-scroll');

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

  const handleSelectPersona = (persona) => {
    setAuthRole('business');
    setBusinessAuthMode('register');
    if (persona.demoBusiness) setName(persona.demoBusiness);
    if (persona.industryPreset) setIndustry(persona.industryPreset);
    if (persona.name) setRegEmail(`${persona.name.toLowerCase()}.receptionist@gmail.com`);
    setErrorMsg(null);
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
    <div style={{ minHeight: '100vh', background: 'var(--bg-app)', color: 'var(--text-primary)', display: 'flex', flexDirection: 'column', position: 'relative' }}>
      {/* Ambient Aurora Light Field Background */}
      <AmbientAuroraField />

      {/* 1. Sticky Navigation Bar with Entrance Animation */}
      <header className="landing-nav hero-enter-nav" role="banner" style={{ position: 'sticky', top: 0, zIndex: 100 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <div className="brand-icon" title="CallMe AI Voice Platform">
            <PhoneCall size={16} strokeWidth={2.5} />
          </div>
          <span style={{ fontWeight: 700, fontSize: '1.05rem', letterSpacing: '-0.03em', color: 'var(--text-primary)', fontFamily: 'var(--font-display)' }}>
            Call<span style={{ color: 'var(--color-emerald)' }}>Me</span>
          </span>
          <span
            style={{
              fontSize: '0.72rem',
              fontFamily: 'var(--font-mono)',
              background: 'var(--bg-surface-elevated)',
              border: '1px solid var(--border-medium)',
              padding: '2px 7px',
              borderRadius: 'var(--radius-full)',
              color: 'var(--text-secondary)',
            }}
          >
            v2.4
          </span>
        </div>

        <nav className="landing-nav-links" aria-label="Main Navigation">
          <a href="#agents">01 · Agents</a>
          <a href="#workflow">02 · Workflow</a>
          <a href="#features">03 · Features</a>
          <a href="#auth-section">04 · Portal</a>
        </nav>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <ThemeToggle />
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

      {/* 2. Hero Section: 2-Column Responsive Layout matching reference screenshot */}
      <section className="landing-hero" id="overview">
        <div className="landing-hero-grid">
          {/* Left Column: Headline, Copy & Action CTAs */}
          <div className="hero-content hero-entrance">
            <h1 className="hero-title">
              Hire a<br />
              receptionist <span className="text-gradient">that<br />never sleeps.</span>
            </h1>

            <p className="hero-subtitle">
              Pick an AI receptionist, train it on your business in minutes, and let it answer calls, book appointments and greet every customer — 24/7.
            </p>

            <div className="hero-actions">
              <button
                type="button"
                className="hero-btn-primary motion-cta"
                onClick={() => {
                  const el = document.getElementById('agents');
                  if (el) el.scrollIntoView({ behavior: 'smooth' });
                }}
              >
                <span>Browse receptionists</span>
                <ArrowRight size={17} />
              </button>

              <button
                type="button"
                className="hero-btn-secondary"
                onClick={() => setCallCycle((c) => c + 1)}
              >
                <span>Replay call preview</span>
              </button>
            </div>
          </div>

          {/* Right Column: Floating Call Card Preview with Dashed Radar Halo */}
          <div className="hero-card-col hero-entrance">
            <HeroCallPreview
              key={callCycle}
              activePreview={activePreview}
              activeIndustryId={activeIndustryId}
              onSelectIndustry={(id) => setActiveIndustryId(id)}
              industries={INDUSTRY_PREVIEWS}
              onReplay={() => setCallCycle((c) => c + 1)}
            />
          </div>
        </div>
      </section>

      {/* 3. Metrics & Social Proof Strip (99.98% uptime, <380ms pickup, etc.) */}
      <MetricsSocialProofStrip />

      {/* 4. Pre-Trained Receptionist Personas ("Meet your next hire") */}
      <AgentPersonasSection onSelectPersona={handleSelectPersona} />

      {/* 5. 5-Stage Agent Orchestration Workflow with Live Execution Trace */}
      <AgentWorkflowSection />

      {/* 6. Enterprise Feature Matrix ("Everything a front desk does. Faster.") */}
      <FeatureGridSection />

      {/* 7. Config Console ("Configure in plain English. Ship in minutes.") */}
      <ConfigConsoleSection />

      {/* 8. Access Portal & Authentication Section */}
      <section
        id="auth-section"
        className="reveal-on-scroll"
        style={{
          maxWidth: '520px',
          margin: '3rem auto 5rem',
          padding: '0 1.5rem',
          width: '100%',
          boxSizing: 'border-box',
        }}
      >
        <div className="card glass" style={{ padding: '2rem 1.75rem', borderRadius: 'var(--radius-xl)', border: '1px solid var(--border-medium)', boxShadow: 'var(--card-shadow)' }}>
          {/* Role Tabs: Business vs Operator */}
          <div
            style={{
              display: 'flex',
              background: 'var(--bg-surface-elevated)',
              border: '1px solid var(--border-medium)',
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
                border: authRole === 'business' ? '1px solid var(--border-medium)' : '1px solid transparent',
                color: authRole === 'business' ? 'var(--text-primary)' : 'var(--text-secondary)',
                boxShadow: authRole === 'business' ? '0 1px 3px rgba(0, 0, 0, 0.08)' : 'none',
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
                border: authRole === 'admin' ? '1px solid var(--border-medium)' : '1px solid transparent',
                color: authRole === 'admin' ? 'var(--text-primary)' : 'var(--text-secondary)',
                boxShadow: authRole === 'admin' ? '0 1px 3px rgba(0, 0, 0, 0.08)' : 'none',
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
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
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
                    color: 'var(--color-primary)',
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
                    border: '1px solid var(--border-medium)',
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
                      padding: '0.28rem 0.65rem',
                      borderRadius: 'var(--radius-xs)',
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border-medium)',
                      color: 'var(--color-primary)',
                      fontSize: '0.74rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                      boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
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
                  padding: '0.65rem',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-medium)',
                  color: 'var(--text-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.65rem',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  marginBottom: '1rem',
                  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
                  transition: 'all var(--transition-fast)',
                }}
              >
                <GoogleIcon size={18} />
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
                <span style={{ flex: 1, height: '1px', background: 'var(--border-medium)' }} />
                <span>or email</span>
                <span style={{ flex: 1, height: '1px', background: 'var(--border-medium)' }} />
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
                    <div style={{ position: 'relative' }}>
                      <input
                        type={showLoginPassword ? 'text' : 'password'}
                        value={loginPassword}
                        onChange={(e) => setLoginPassword(e.target.value)}
                        placeholder="••••••••"
                        className="form-input"
                        style={{ paddingRight: '2.5rem' }}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowLoginPassword(!showLoginPassword)}
                        style={{
                          position: 'absolute',
                          right: '0.65rem',
                          top: '50%',
                          transform: 'translateY(-50%)',
                          background: 'none',
                          border: 'none',
                          color: 'var(--text-tertiary)',
                          cursor: 'pointer',
                        }}
                      >
                        {showLoginPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                      </button>
                    </div>
                  </div>

                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={loading}
                    style={{ width: '100%', padding: '0.65rem', marginTop: '0.5rem' }}
                  >
                    {loading ? 'Authenticating...' : 'Sign In to Workspace'}
                  </button>
                </form>
              ) : (
                <form onSubmit={handleBusinessRegister} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  <div className="form-group">
                    <label className="form-label">Business Name *</label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. Spice Garden Bistro"
                      className="form-input"
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Domain / Industry</label>
                    <select
                      value={industry}
                      onChange={(e) => setIndustry(e.target.value)}
                      className="form-input"
                    >
                      <option value="Restaurant">Restaurant & Dining</option>
                      <option value="Clinic">Clinic & Healthcare</option>
                      <option value="Hotel">Hotel & Hospitality</option>
                      <option value="Salon">Salon & Wellness</option>
                      <option value="General Services">General Professional Services</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Business Work Email *</label>
                    <input
                      type="email"
                      value={regEmail}
                      onChange={(e) => setRegEmail(e.target.value)}
                      placeholder="owner@yourdomain.com"
                      className="form-input"
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Password *</label>
                    <div style={{ position: 'relative' }}>
                      <input
                        type={showRegPassword ? 'text' : 'password'}
                        value={regPassword}
                        onChange={(e) => setRegPassword(e.target.value)}
                        placeholder="At least 4 characters"
                        className="form-input"
                        style={{ paddingRight: '2.5rem' }}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowRegPassword(!showRegPassword)}
                        style={{
                          position: 'absolute',
                          right: '0.65rem',
                          top: '50%',
                          transform: 'translateY(-50%)',
                          background: 'none',
                          border: 'none',
                          color: 'var(--text-tertiary)',
                          cursor: 'pointer',
                        }}
                      >
                        {showRegPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                      </button>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                    <div className="form-group">
                      <label className="form-label">Opens At</label>
                      <input
                        type="time"
                        value={openTime}
                        onChange={(e) => setOpenTime(e.target.value)}
                        className="form-input"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Closes At</label>
                      <input
                        type="time"
                        value={closeTime}
                        onChange={(e) => setCloseTime(e.target.value)}
                        className="form-input"
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={loading}
                    style={{ width: '100%', padding: '0.65rem', marginTop: '0.5rem' }}
                  >
                    {loading ? 'Provisioning...' : 'Activate AI Receptionist'}
                  </button>
                </form>
              )}
            </>
          ) : (
            <>
              <div style={{ marginBottom: '1.25rem' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                  Operator Admin Access
                </h3>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '4px 0 0' }}>
                  Manage global telephony trunks, multi-tenant businesses, and tool telemetry.
                </p>
              </div>

              <div
                style={{
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-medium)',
                  padding: '0.65rem 0.85rem',
                  borderRadius: 'var(--radius-sm)',
                  marginBottom: '1.25rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                  Local operator key default is <strong>admin</strong>:
                </span>
                <button
                  type="button"
                  onClick={() => setAdminPasscode('admin')}
                  style={{
                    padding: '0.28rem 0.65rem',
                    borderRadius: 'var(--radius-xs)',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-medium)',
                    color: 'var(--color-primary)',
                    fontSize: '0.74rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
                  }}
                >
                  Autofill
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

      {/* 9. High-Converting Bottom CTA Banner */}
      <section className="reveal-on-scroll" style={{ maxWidth: '1152px', margin: '0 auto', padding: '0 1.5rem 6rem', width: '100%', boxSizing: 'border-box' }}>
        <div className="glass border-glow shadow-glow" style={{ borderRadius: '1.5rem', padding: '3.5rem 2rem', textAlign: 'center', border: '1px solid var(--border-medium)' }}>
          <h2 style={{ fontSize: 'clamp(2rem, 4vw, 2.5rem)', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 0.75rem', letterSpacing: '-0.025em' }}>
            Your receptionist can start today.
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1rem', maxWidth: '440px', margin: '0 auto 2rem' }}>
            14-day free trial. No contracts. Cancel anytime.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center', gap: '1rem' }}>
            <button
              type="button"
              className="landing-btn-primary"
              onClick={() => scrollToAuth('business', 'register')}
              style={{ padding: '0.75rem 2rem', fontSize: '0.95rem', fontWeight: 600, borderRadius: '8px' }}
            >
              Start free trial
            </button>
            <button
              type="button"
              onClick={() => scrollToAuth('business', 'login')}
              style={{
                padding: '0.75rem 2rem',
                fontSize: '0.95rem',
                fontWeight: 600,
                borderRadius: '8px',
                border: '1px solid var(--border-medium)',
                background: 'transparent',
                color: 'var(--text-primary)',
                cursor: 'pointer',
                transition: 'border-color 0.2s, background 0.2s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--color-primary)';
                e.currentTarget.style.background = 'var(--bg-subtle)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-medium)';
                e.currentTarget.style.background = 'transparent';
              }}
            >
              Log in
            </button>
          </div>
          <p style={{ marginTop: '1.25rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            Already a customer?{' '}
            <button
              type="button"
              onClick={() => scrollToAuth('business', 'login')}
              style={{ background: 'none', border: 'none', color: 'var(--color-primary)', fontWeight: 600, cursor: 'pointer', textDecoration: 'underline', padding: 0 }}
            >
              Log in to your dashboard
            </button>
          </p>
        </div>
      </section>

      {/* 10. Polished Dark Footer */}
      <footer
        style={{
          borderTop: '1px solid var(--border-medium)',
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
          <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontFamily: 'var(--font-display)' }}>CallMe Platform</span>
          <span>© 2026. All rights reserved.</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', fontFamily: 'var(--font-mono)', fontSize: '0.72rem' }}>
          <span>● all systems operational</span>
          <span style={{ color: 'var(--color-emerald)' }}>380ms Turn Latency</span>
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
