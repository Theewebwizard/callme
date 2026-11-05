import React, { useState } from 'react';
import {
  Calendar,
  CalendarCheck,
  Sparkles,
  PhoneCall,
  Clock,
  CheckCircle2,
  Volume2,
  ShieldCheck,
  MessageSquare,
  Zap,
  Globe,
  Bell,
  Utensils,
  Stethoscope,
  Hotel,
  Check,
} from 'lucide-react';

const INDUSTRY_DATA = {
  clinic: {
    id: 'clinic',
    label: 'Health & Clinic',
    icon: Stethoscope,
    ownerName: 'Dr. Robert',
    avatarInitial: 'R',
    avatarBg: 'linear-gradient(135deg, #0284c7 0%, #38bdf8 100%)',
    businessName: 'Apex Dental & Aesthetics',
    greetingNote: 'You have a full day ahead · 14 calls resolved overnight.',
    confirmedCount: '4 Bookings',
    schedule: [
      {
        month: 'OCT',
        day: '24',
        time: 'Monday · 10:00 AM - 11:00 AM',
        title: 'Comprehensive Dental Cleaning',
        patient: 'Sarah Jenkins',
        source: 'Inbound Voice Call (Aria)',
        tag: 'Confirmed · SMS Sent',
      },
      {
        month: 'OCT',
        day: '24',
        time: 'Monday · 1:30 PM - 2:30 PM',
        title: 'Orthodontic Aligners Consult',
        patient: 'Michael Chang',
        source: 'After-hours Voice DID',
        tag: 'Calendar Locked',
      },
      {
        month: 'OCT',
        day: '24',
        time: 'Monday · 4:00 PM - 4:45 PM',
        title: 'Emergency Toothache Triage',
        patient: 'Priya Sharma',
        source: 'Voice AI Triage + Notes',
        tag: 'Pre-triaged',
      },
    ],
  },
  restaurant: {
    id: 'restaurant',
    label: 'Restaurant & Dining',
    icon: Utensils,
    ownerName: 'Chef Marco',
    avatarInitial: 'M',
    avatarBg: 'linear-gradient(135deg, #f59e0b 0%, #ea580c 100%)',
    businessName: 'Trattoria Bella Vista',
    greetingNote: '34 table inquiries handled · 8 reservations confirmed.',
    confirmedCount: '8 Tables',
    schedule: [
      {
        month: 'OCT',
        day: '24',
        time: 'Tonight · 6:30 PM - 8:30 PM',
        title: 'Patio Table for 6 (Birthday)',
        patient: 'Kavita Rao',
        source: 'Voice Call at 1:45 AM',
        tag: 'Deposit Verified',
      },
      {
        month: 'OCT',
        day: '24',
        time: 'Tonight · 7:45 PM - 9:30 PM',
        title: 'Booth Table for 2 (Tasting)',
        patient: 'David Miller',
        source: 'Autonomous DID',
        tag: 'Confirmed',
      },
      {
        month: 'OCT',
        day: '24',
        time: 'Tonight · 9:00 PM - 11:00 PM',
        title: "Chef's Table VIP for 4",
        patient: 'Ananya Roy',
        source: 'Aria Receptionist',
        tag: 'Wine Pairing Note',
      },
    ],
  },
  hotel: {
    id: 'hotel',
    label: 'Hotel & Hospitality',
    icon: Hotel,
    ownerName: 'Manager Elena',
    avatarInitial: 'E',
    avatarBg: 'linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%)',
    businessName: 'The Grand Azure Suites',
    greetingNote: '22 guest inquiries handled · 3 suite check-ins locked in.',
    confirmedCount: '3 Suites',
    schedule: [
      {
        month: 'OCT',
        day: '24',
        time: 'Today · 2:00 PM Check-in',
        title: 'Deluxe Penthouse Suite 402',
        patient: 'Alexander Vance',
        source: 'Direct Voice Inbound',
        tag: 'Early Arrival',
      },
      {
        month: 'OCT',
        day: '24',
        time: 'Today · 4:00 PM Check-in',
        title: 'Executive King Suite 308',
        patient: 'Rachel Adams',
        source: 'Voice DID Booking',
        tag: 'Shuttle Arranged',
      },
      {
        month: 'OCT',
        day: '24',
        time: 'Today · 6:30 PM Check-in',
        title: 'Ocean View Corner Room 214',
        patient: 'Kenji Sato',
        source: 'Bilingual Voice Agent',
        tag: 'SMS Key Sent',
      },
    ],
  },
};

const BACKGROUND_PILLS_ROW_1 = [
  { icon: PhoneCall, text: '24/7 Voice DID Inbound' },
  { icon: MessageSquare, text: 'WhatsApp & SMS Dispatch' },
  { icon: Calendar, text: 'Google Calendar & Outlook Sync' },
  { icon: Zap, text: 'Sub-380ms Acoustic Latency' },
  { icon: ShieldCheck, text: 'Encrypted Caller Transcripts' },
];

const BACKGROUND_PILLS_ROW_2 = [
  { icon: Utensils, text: 'Table & Room Inventory Lock' },
  { icon: Bell, text: 'Real-time Owner SMS Alerts' },
  { icon: Globe, text: '30+ Languages & Regional Accents' },
  { icon: CheckCircle2, text: 'Zero Double-Booking Guarantee' },
  { icon: Sparkles, text: 'Autonomous LangGraph Pipeline' },
];

const BACKGROUND_PILLS_ROW_3 = [
  { icon: Clock, text: '3:00 AM Call Handling' },
  { icon: CheckCircle2, text: 'Deterministic Database Tools' },
  { icon: MessageSquare, text: 'Instant Appointment Confirmations' },
  { icon: Volume2, text: 'Natural Human Acoustic Inflection' },
  { icon: ShieldCheck, text: 'HIPAA & Enterprise Safe' },
];

export default function MobileBriefingSection() {
  const [selectedIndustry, setSelectedIndustry] = useState('clinic');
  const current = INDUSTRY_DATA[selectedIndustry] || INDUSTRY_DATA.clinic;

  return (
    <section
      id="mobile-briefing"
      className="reveal-on-scroll"
      style={{
        maxWidth: '1240px',
        margin: '0 auto',
        padding: '2rem 1.5rem 6.5rem',
        width: '100%',
        boxSizing: 'border-box',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* 1. Header with Eyebrow, Title & Subtitle */}
      <div style={{ textAlign: 'center', marginBottom: '2.5rem', position: 'relative', zIndex: 10 }}>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.45rem',
            padding: '0.3rem 0.85rem',
            borderRadius: 'var(--radius-full)',
            background: 'color-mix(in oklab, var(--color-primary) 12%, transparent)',
            border: '1px solid color-mix(in oklab, var(--color-primary) 30%, transparent)',
            color: 'var(--color-primary)',
            fontSize: '0.74rem',
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
            marginBottom: '0.85rem',
          }}
        >
          <CalendarCheck size={13} />
          <span>Autonomous Morning Briefing</span>
        </div>

        <h2
          style={{
            fontSize: 'clamp(2rem, 4.2vw, 3rem)',
            fontWeight: 800,
            letterSpacing: '-0.03em',
            color: 'var(--text-primary)',
            margin: '0 auto 0.85rem',
            maxWidth: '820px',
            fontFamily: 'var(--font-display)',
          }}
        >
          Wake up to a full calendar.{' '}
          <span className="text-gradient">Not missed calls.</span>
        </h2>

        <p
          style={{
            color: 'var(--text-secondary)',
            fontSize: '1rem',
            maxWidth: '640px',
            margin: '0 auto 1.75rem',
            lineHeight: 1.6,
          }}
        >
          While you sleep, your AI receptionist answers every inbound call, locks confirmed bookings directly into your calendar, and prepares your morning schedule on your phone.
        </p>

        {/* Industry Switcher Tabs */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            background: 'var(--bg-surface-elevated)',
            border: '1px solid var(--border-medium)',
            padding: '4px',
            borderRadius: 'var(--radius-full)',
            flexWrap: 'wrap',
            justifyContent: 'center',
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.04)',
          }}
        >
          {Object.values(INDUSTRY_DATA).map((ind) => {
            const Icon = ind.icon;
            const isActive = ind.id === selectedIndustry;
            return (
              <button
                key={ind.id}
                type="button"
                onClick={() => setSelectedIndustry(ind.id)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 14px',
                  borderRadius: 'var(--radius-full)',
                  border: isActive ? '1px solid var(--color-primary)' : '1px solid transparent',
                  background: isActive ? 'var(--gradient-primary)' : 'transparent',
                  color: isActive ? 'var(--text-inverse)' : 'var(--text-secondary)',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                  boxShadow: isActive ? '0 2px 8px color-mix(in oklab, var(--color-primary) 30%, transparent)' : 'none',
                }}
              >
                <Icon size={14} />
                <span>{ind.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. Interactive Phone Mockup with Layered Floating Pills Behind It */}
      <div
        style={{
          position: 'relative',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '680px',
          padding: '1rem 0',
        }}
      >
        {/* Layer A: Floating Integration Pills Background (matching the screenshot reference) */}
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: 0,
            overflow: 'hidden',
            pointerEvents: 'none',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-around',
            zIndex: 0,
            opacity: 0.75,
            maskImage: 'linear-gradient(to right, transparent, black 15%, black 85%, transparent)',
            WebkitMaskImage: 'linear-gradient(to right, transparent, black 15%, black 85%, transparent)',
          }}
        >
          {/* Row 1: drifting slightly left */}
          <div
            className="animate-drift-left"
            style={{
              display: 'flex',
              gap: '1.25rem',
              whiteSpace: 'nowrap',
              transform: 'translateX(-5%)',
            }}
          >
            {[...BACKGROUND_PILLS_ROW_1, ...BACKGROUND_PILLS_ROW_1].map((pill, idx) => {
              const Icon = pill.icon;
              return (
                <div
                  key={idx}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.6rem',
                    padding: '0.55rem 1.15rem',
                    borderRadius: 'var(--radius-full)',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-medium)',
                    boxShadow: 'var(--card-shadow)',
                    color: 'var(--text-tertiary)',
                    fontSize: '0.78rem',
                    fontWeight: 500,
                  }}
                >
                  <Icon size={14} color="var(--color-primary)" />
                  <span>{pill.text}</span>
                </div>
              );
            })}
          </div>

          {/* Row 2: drifting slightly right */}
          <div
            className="animate-drift-right"
            style={{
              display: 'flex',
              gap: '1.25rem',
              whiteSpace: 'nowrap',
              transform: 'translateX(2%)',
            }}
          >
            {[...BACKGROUND_PILLS_ROW_2, ...BACKGROUND_PILLS_ROW_2].map((pill, idx) => {
              const Icon = pill.icon;
              return (
                <div
                  key={idx}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.6rem',
                    padding: '0.55rem 1.15rem',
                    borderRadius: 'var(--radius-full)',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-medium)',
                    boxShadow: 'var(--card-shadow)',
                    color: 'var(--text-tertiary)',
                    fontSize: '0.78rem',
                    fontWeight: 500,
                  }}
                >
                  <Icon size={14} color="var(--color-primary)" />
                  <span>{pill.text}</span>
                </div>
              );
            })}
          </div>

          {/* Row 3: drifting slightly left */}
          <div
            className="animate-drift-left"
            style={{
              display: 'flex',
              gap: '1.25rem',
              whiteSpace: 'nowrap',
              transform: 'translateX(-8%)',
            }}
          >
            {[...BACKGROUND_PILLS_ROW_3, ...BACKGROUND_PILLS_ROW_3].map((pill, idx) => {
              const Icon = pill.icon;
              return (
                <div
                  key={idx}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.6rem',
                    padding: '0.55rem 1.15rem',
                    borderRadius: 'var(--radius-full)',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-medium)',
                    boxShadow: 'var(--card-shadow)',
                    color: 'var(--text-tertiary)',
                    fontSize: '0.78rem',
                    fontWeight: 500,
                  }}
                >
                  <Icon size={14} color="var(--color-primary)" />
                  <span>{pill.text}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Layer B: Sleek iPhone Smartphone Mockup in Crisp Foreground */}
        <div
          className="iphone-mockup"
          style={{
            position: 'relative',
            zIndex: 10,
            width: '100%',
            maxWidth: '350px',
            borderRadius: '48px',
            background: 'var(--bg-card)',
            border: '9px solid #1e293b',
            boxShadow: '0 30px 80px -15px rgba(2, 132, 199, 0.32), 0 0 0 1px rgba(0, 0, 0, 0.15)',
            overflow: 'hidden',
          }}
        >
          {/* Smartphone Ambient Lighting Header */}
          <div
            style={{
              background: 'linear-gradient(180deg, color-mix(in oklab, var(--color-primary) 12%, var(--bg-card)) 0%, var(--bg-card) 60%)',
              padding: '0.75rem 1.15rem 1rem',
              borderBottom: '1px solid var(--border-medium)',
            }}
          >
            {/* Dynamic Island Capsule */}
            <div
              style={{
                width: '88px',
                height: '22px',
                background: '#090d16',
                borderRadius: '20px',
                margin: '0 auto 0.65rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0 8px',
                boxShadow: 'inset 0 0 0 1px rgba(255, 255, 255, 0.12)',
              }}
            >
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#1e293b' }} />
              <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: '#0284c7', opacity: 0.8 }} />
            </div>

            {/* iOS Status Bar */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                fontSize: '0.7rem',
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-tertiary)',
                fontWeight: 600,
                marginBottom: '1rem',
              }}
            >
              <span>9:41</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                <span style={{ fontSize: '10px' }}>5G</span>
                <span>●●●</span>
                <div
                  style={{
                    width: '18px',
                    height: '9px',
                    borderRadius: '2.5px',
                    border: '1px solid var(--text-tertiary)',
                    padding: '1px',
                    display: 'flex',
                    alignItems: 'center',
                  }}
                >
                  <div style={{ width: '80%', height: '100%', background: 'var(--color-primary)', borderRadius: '1px' }} />
                </div>
              </div>
            </div>

            {/* In-App Header: Brand Logo & User Avatar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '7px',
                    background: 'var(--gradient-primary)',
                    display: 'grid',
                    placeItems: 'center',
                    color: '#ffffff',
                  }}
                >
                  <PhoneCall size={12} strokeWidth={2.6} />
                </div>
                <span style={{ fontWeight: 800, fontSize: '0.92rem', color: 'var(--text-primary)', fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}>
                  CALL<span style={{ color: 'var(--color-primary)' }}>ME</span>
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    background: 'color-mix(in oklab, var(--color-primary) 12%, transparent)',
                    border: '1px solid color-mix(in oklab, var(--color-primary) 30%, transparent)',
                    padding: '2px 7px',
                    borderRadius: 'var(--radius-full)',
                    fontSize: '0.66rem',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--color-primary)',
                    fontWeight: 700,
                  }}
                >
                  <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: '#10b981' }} />
                  <span>ONLINE</span>
                </div>

                <div
                  style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: '50%',
                    background: current.avatarBg,
                    display: 'grid',
                    placeItems: 'center',
                    fontWeight: 700,
                    fontSize: '0.78rem',
                    color: '#ffffff',
                    boxShadow: '0 2px 6px rgba(0, 0, 0, 0.15)',
                  }}
                >
                  {current.avatarInitial}
                </div>
              </div>
            </div>

            {/* Cute Smiling AI Cloud Spirit Character (1:1 with reference idea) */}
            <div style={{ textAlign: 'center', margin: '1.25rem 0 0.5rem' }}>
              <div
                className="animate-float"
                style={{
                  display: 'inline-block',
                  position: 'relative',
                  filter: 'drop-shadow(0 10px 18px color-mix(in oklab, var(--color-primary) 28%, transparent))',
                }}
              >
                {/* Radial Glow Aura behind Cloud */}
                <div
                  style={{
                    position: 'absolute',
                    inset: '-12px',
                    borderRadius: '50%',
                    background: 'radial-gradient(circle, color-mix(in oklab, var(--color-primary) 35%, transparent) 0%, transparent 70%)',
                    zIndex: 0,
                  }}
                />

                {/* Expressive Smiling Cloud SVG */}
                <svg
                  width="86"
                  height="64"
                  viewBox="0 0 86 64"
                  fill="none"
                  style={{ position: 'relative', zIndex: 1 }}
                >
                  <defs>
                    <linearGradient id="cloudWhiteGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#ffffff" />
                      <stop offset="55%" stopColor="#f4f9fd" />
                      <stop offset="100%" stopColor="#dbeafe" />
                    </linearGradient>
                  </defs>
                  {/* Organic Puffy Cloud Shape */}
                  <path
                    d="M24 50h38a15 15 0 0 0 6-29 17 17 0 0 0-32-8 14 14 0 0 0-21 17A14 14 0 0 0 24 50z"
                    fill="url(#cloudWhiteGrad)"
                    stroke="color-mix(in oklab, var(--color-primary) 30%, transparent)"
                    strokeWidth="1.5"
                  />
                  {/* Friendly Eyes */}
                  <circle cx="35" cy="35" r="3" fill="#0f172a" />
                  <circle cx="36" cy="34" r="1" fill="#ffffff" />
                  <circle cx="51" cy="35" r="3" fill="#0f172a" />
                  <circle cx="52" cy="34" r="1" fill="#ffffff" />
                  {/* Blushing Cheeks */}
                  <ellipse cx="29" cy="39" rx="3.5" ry="2" fill="#fb7185" opacity="0.6" />
                  <ellipse cx="57" cy="39" rx="3.5" ry="2" fill="#fb7185" opacity="0.6" />
                  {/* Sweet Smile */}
                  <path
                    d="M40 39c1.5 2 4.5 2 6 0"
                    stroke="#0f172a"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                  />
                </svg>
              </div>

              {/* Friendly Personalized Morning Greeting */}
              <h3
                style={{
                  fontSize: '1.35rem',
                  fontWeight: 800,
                  color: 'var(--text-primary)',
                  margin: '0.45rem 0 0.2rem',
                  fontFamily: 'var(--font-display)',
                  letterSpacing: '-0.02em',
                }}
              >
                Morning {current.ownerName}!
              </h3>
              <p
                style={{
                  fontSize: '0.78rem',
                  color: 'var(--text-secondary)',
                  margin: 0,
                  lineHeight: 1.4,
                  maxWidth: '260px',
                  marginInline: 'auto',
                }}
              >
                {current.greetingNote}
              </p>
            </div>
          </div>

          {/* Schedule List Content (Matching Today Schedule Cards in the reference screenshot) */}
          <div style={{ padding: '1rem 1.15rem 1.5rem', background: 'var(--bg-card)' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: '0.75rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Calendar size={14} color="var(--color-primary)" />
                <span style={{ fontSize: '0.84rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Today Schedule
                </span>
              </div>
              <span
                style={{
                  fontSize: '0.68rem',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--color-primary)',
                  fontWeight: 600,
                  background: 'color-mix(in oklab, var(--color-primary) 10%, transparent)',
                  border: '1px solid color-mix(in oklab, var(--color-primary) 25%, transparent)',
                  padding: '2px 7px',
                  borderRadius: 'var(--radius-full)',
                }}
              >
                {current.confirmedCount}
              </span>
            </div>

            {/* List of 3 Booking Cards */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
              {current.schedule.map((item, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    padding: '0.65rem 0.75rem',
                    borderRadius: '14px',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-medium)',
                    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
                    transition: 'all 0.2s ease',
                  }}
                >
                  {/* Mini Calendar Date Block */}
                  <div
                    style={{
                      width: '42px',
                      borderRadius: '8px',
                      overflow: 'hidden',
                      border: '1px solid var(--border-medium)',
                      textAlign: 'center',
                      flexShrink: 0,
                      background: 'var(--bg-surface-elevated)',
                    }}
                  >
                    <div
                      style={{
                        background: 'var(--gradient-primary)',
                        color: '#ffffff',
                        fontSize: '8px',
                        fontWeight: 700,
                        padding: '1px 0',
                        letterSpacing: '0.04em',
                      }}
                    >
                      {item.month}
                    </div>
                    <div
                      style={{
                        fontSize: '0.86rem',
                        fontWeight: 800,
                        fontFamily: 'var(--font-display)',
                        color: 'var(--text-primary)',
                        padding: '2px 0 3px',
                      }}
                    >
                      {item.day}
                    </div>
                  </div>

                  {/* Card Event Content */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: '0.68rem',
                        color: 'var(--text-tertiary)',
                        fontFamily: 'var(--font-mono)',
                        marginBottom: '1px',
                      }}
                    >
                      {item.time}
                    </div>
                    <div
                      style={{
                        fontSize: '0.82rem',
                        fontWeight: 700,
                        color: 'var(--text-primary)',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {item.title}
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        marginTop: '3px',
                      }}
                    >
                      <span
                        style={{
                          fontSize: '0.7rem',
                          color: 'var(--text-secondary)',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {item.patient}
                      </span>
                      <span
                        style={{
                          fontSize: '0.64rem',
                          color: 'var(--color-primary)',
                          fontWeight: 600,
                          flexShrink: 0,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '2px',
                        }}
                      >
                        <Check size={10} strokeWidth={3} /> {item.tag}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* iOS Home Indicator Bar */}
            <div
              style={{
                width: '110px',
                height: '4px',
                borderRadius: '999px',
                background: 'var(--border-strong)',
                margin: '1.25rem auto 0',
                opacity: 0.6,
              }}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
