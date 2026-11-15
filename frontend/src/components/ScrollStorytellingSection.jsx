import React, { useState, useEffect, useRef } from 'react';
import {
  PhoneCall,
  Phone,
  Radio,
  Zap,
  CheckCircle2,
  Calendar,
  Layers,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Clock,
  MessageSquare,
  Bot,
  Database,
} from 'lucide-react';

const STORY_STEPS = [
  {
    step: '01',
    badge: 'INBOUND TELEPHONY',
    title: 'A call arrives on the first ring',
    desc: 'Never lose a high-value customer, whether during the dinner peak rush or at 3 AM when the front desk is closed. Answerly monitors your business DID line 24/7 with a sub-380ms pickup guarantee.',
    highlights: ['Picks up on the 1st ring', 'Zero dropped calls', 'Direct carrier DID binding'],
  },
  {
    step: '02',
    badge: 'MULTILINGUAL INDIC VOICE ENGINE',
    title: 'Answerly answers with natural human warmth',
    desc: 'No frustrating "press 1 for reservations" IVR phone trees. Answerly immediately greets callers across 12+ Indic languages and dialects, detecting speech pauses and accents with ultra-low acoustic turn latency.',
    highlights: ['12+ Indic languages & code-switching', 'No robotic phone trees', '380ms conversational turn time'],
  },
  {
    step: '03',
    badge: 'SEMANTIC INTENT EXTRACTION',
    title: 'Answerly extracts the exact customer request',
    desc: 'As callers speak naturally—"Hi, can we get a table for 4 tonight around 8 PM outside?"—Answerly accurately parses party size, time, date, dietary needs, or clinical symptoms grounded in your business policies.',
    highlights: ['Entity extraction (party, time, date)', 'FAQ knowledge grounding', 'Conversational context retention'],
  },
  {
    step: '04',
    badge: 'CALENDAR & INVENTORY TRUTH',
    title: 'Answerly verifies live database availability',
    desc: 'Answerly executes real-time database queries against your live room nights, restaurant tables, or doctor consultation chairs. It checks genuine availability, enforces party limits, and prevents double bookings.',
    highlights: ['Authoritative database lookup', 'Zero double-booking guarantee', 'Turnaround time calculation'],
  },
  {
    step: '05',
    badge: 'WORKFLOW RESOLUTION',
    title: 'Answerly confirms and logs the entire transaction',
    desc: 'The booking is committed to your authoritative database, a confirmation SMS with directions is dispatched to the caller’s mobile, and full turn-by-turn audio transcripts are synced to your cockpit.',
    highlights: ['Instant SMS voucher dispatch', 'Structured Cockpit Audit Trail', '100% Autonomous Resolution'],
  },
];

/**
 * StoryConsoleView
 * The sticky/responsive visual console that morphs based on the active scroll step.
 */
function StoryConsoleView({ activeStep }) {
  return (
    <div
      className="story-console"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-medium)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: '0 24px 60px rgba(0, 0, 0, 0.75), var(--specular-top)',
        overflow: 'hidden',
        width: '100%',
        transition: 'all 0.35s cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      {/* Console Top Bar */}
      <div
        style={{
          padding: '0.85rem 1.25rem',
          borderBottom: '1px solid var(--border-medium)',
          background: 'var(--bg-surface-elevated)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: activeStep === 0 ? 'var(--amber-500)' : 'var(--mint-500)',
              boxShadow: activeStep === 0 ? '0 0 10px rgba(245, 158, 11, 0.7)' : '0 0 10px rgba(16, 185, 129, 0.7)',
            }}
          />
          <span style={{ fontSize: '0.78rem', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-primary)' }}>
            {activeStep === 0 ? 'RINGING INBOUND DID' : 'ACTIVE WEBRTC SESSION'}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span
            style={{
              fontSize: '0.7rem',
              fontFamily: 'var(--font-mono)',
              background: 'rgba(255, 255, 255, 0.06)',
              border: '1px solid var(--border-medium)',
              padding: '2px 8px',
              borderRadius: 'var(--radius-full)',
              color: 'var(--text-secondary)',
            }}
          >
            STAGE {activeStep + 1} OF 5
          </span>
        </div>
      </div>

      {/* Dynamic State Views */}
      <div style={{ padding: '1.5rem', minHeight: '380px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        {/* Step 1: Inbound Call Ringing */}
        {activeStep === 0 && (
          <div style={{ textAlign: 'center', animation: 'fadeInUp 0.35s ease both' }}>
            <div
              style={{
                width: '72px',
                height: '72px',
                borderRadius: '50%',
                background: 'rgba(245, 158, 11, 0.12)',
                border: '1px solid rgba(245, 158, 11, 0.35)',
                color: 'var(--amber-500)',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: '1.25rem',
                boxShadow: '0 0 30px rgba(245, 158, 11, 0.25)',
              }}
            >
              <PhoneCall size={32} className="pulse-ring" />
            </div>

            <div style={{ fontSize: '0.72rem', color: 'var(--amber-500)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '4px' }}>
              ● Carrier Signal Detected
            </div>
            <div style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.02em', marginBottom: '4px' }}>
              +91 98201 44102
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', marginBottom: '1.5rem' }}>
              Target: Spice Garden Bistro DID • Line 01
            </div>

            <div
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '0.76rem',
                color: 'var(--mint-400)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              <Zap size={14} />
              <span>Auto-answering on 1st ring in 0.18s...</span>
            </div>
          </div>
        )}

        {/* Step 2: Call Answered & Bilingual Voice */}
        {activeStep === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', animation: 'fadeInUp 0.35s ease both' }}>
            <div
              style={{
                background: 'rgba(16, 185, 129, 0.08)',
                border: '1px solid rgba(16, 185, 129, 0.22)',
                padding: '0.65rem 1rem',
                borderRadius: 'var(--radius-sm)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span style={{ fontSize: '0.76rem', color: 'var(--mint-400)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                ● WebRTC Audio Stream Active (280ms Latency)
              </span>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                EN + HI SPEECH
              </span>
            </div>

            {/* Simulated Voice Waveform */}
            <div style={{ padding: '1rem 0' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginBottom: '8px' }}>
                SPEECH SYNTHESIS SPECTRUM (SIMULATED)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '3px', height: '48px' }}>
                {Array.from({ length: 24 }).map((_, i) => (
                  <div
                    key={i}
                    style={{
                      flex: 1,
                      height: `${Math.sin(i * 0.45) * 35 + 50}%`,
                      background: 'var(--mint-400)',
                      borderRadius: '1px',
                      opacity: 0.85,
                      transition: 'height 0.2s ease',
                    }}
                  />
                ))}
              </div>
            </div>

            <div
              style={{
                background: '#ffffff',
                color: '#07080a',
                padding: '0.85rem 1rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.86rem',
                lineHeight: 1.5,
                fontWeight: 500,
                boxShadow: '0 4px 16px rgba(0, 0, 0, 0.4)',
              }}
            >
              "Namaste! Welcome to Spice Garden Bistro. How can I assist you with reservations or our menu today?"
            </div>
          </div>
        )}

        {/* Step 3: Intent & Entity Extraction */}
        {activeStep === 2 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', animation: 'fadeInUp 0.35s ease both' }}>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Real-Time Conversational Entity Extraction
            </div>

            {/* Caller Utterance */}
            <div
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.84rem',
                color: 'var(--text-primary)',
              }}
            >
              "Do you have a table for 4 tonight around 8 PM? Also is outdoor seating available?"
            </div>

            {/* Extracted JSON schema pills */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginTop: '0.5rem' }}>
              <div style={{ background: 'rgba(255, 255, 255, 0.04)', border: '1px solid var(--border-medium)', padding: '0.6rem 0.8rem', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>INTENT</div>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--mint-400)', fontFamily: 'var(--font-mono)' }}>book_table</div>
              </div>
              <div style={{ background: 'rgba(255, 255, 255, 0.04)', border: '1px solid var(--border-medium)', padding: '0.6rem 0.8rem', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>PARTY SIZE</div>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>4 Guests</div>
              </div>
              <div style={{ background: 'rgba(255, 255, 255, 0.04)', border: '1px solid var(--border-medium)', padding: '0.6rem 0.8rem', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>REQUESTED TIME</div>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>Tonight • 20:00</div>
              </div>
              <div style={{ background: 'rgba(255, 255, 255, 0.04)', border: '1px solid var(--border-medium)', padding: '0.6rem 0.8rem', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>PREFERENCE</div>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--sky-400)', fontFamily: 'var(--font-mono)' }}>Patio Garden</div>
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Availability Check Radar */}
        {activeStep === 3 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', animation: 'fadeInUp 0.35s ease both' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase' }}>
                LIVE INVENTORY AUDIT RADAR
              </span>
              <span style={{ fontSize: '0.72rem', color: 'var(--mint-400)', fontFamily: 'var(--font-mono)' }}>
                QUERY EXECUTION: 12ms
              </span>
            </div>

            {/* Inventory Inspection Matrix */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div
                style={{
                  background: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.35)',
                  padding: '0.75rem 1rem',
                  borderRadius: 'var(--radius-sm)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontSize: '0.84rem', fontWeight: 700, color: 'var(--text-primary)' }}>Table #12 (Cover 4 • Garden Patio)</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>20:00–21:30 Slot Available • Matches Seating Preference</div>
                </div>
                <span style={{ fontSize: '0.74rem', background: 'var(--mint-500)', color: '#07080a', padding: '2px 8px', borderRadius: 'var(--radius-full)', fontWeight: 700 }}>
                  AVAILABLE
                </span>
              </div>

              <div
                style={{
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-medium)',
                  padding: '0.65rem 1rem',
                  borderRadius: 'var(--radius-sm)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  opacity: 0.6,
                }}
              >
                <div>
                  <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Table #04 (Cover 4 • Main Hall)</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>Reserved by Customer #BK-8819</div>
                </div>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                  BOOKED
                </span>
              </div>
            </div>

            {/* Autonomous Spoken Confirmation to Caller */}
            <div
              style={{
                marginTop: '0.5rem',
                background: '#ffffff',
                color: '#07080a',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.84rem',
                lineHeight: 1.5,
                fontWeight: 500,
              }}
            >
              "We have a lovely table on our garden patio open at 8:00 PM. Shall I confirm this reservation under your name?"
            </div>
          </div>
        )}

        {/* Step 5: Confirmed Booking Ticket */}
        {activeStep === 4 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', animation: 'fadeInUp 0.35s ease both' }}>
            <div
              style={{
                background: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid rgba(16, 185, 129, 0.35)',
                borderRadius: 'var(--radius-md)',
                padding: '1.25rem',
                textAlign: 'center',
              }}
            >
              <div
                style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '50%',
                  background: 'var(--mint-500)',
                  color: '#07080a',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '0.65rem',
                }}
              >
                <CheckCircle2 size={24} />
              </div>

              <div style={{ fontSize: '0.72rem', color: 'var(--mint-400)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Reservation Confirmed
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', margin: '2px 0 6px' }}>
                Token #BK-8821
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                Rohit Verma • Table #12 • Tonight at 8:00 PM (4 Guests)
              </div>
            </div>

            {/* Instant SMS Dispatch simulation */}
            <div
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-sm)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <MessageSquare size={16} style={{ color: 'var(--mint-400)' }} />
                <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                  SMS Voucher Dispatched to <strong style={{ color: 'var(--text-primary)' }}>+91 98201 44102</strong>
                </span>
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--mint-400)', fontFamily: 'var(--font-mono)' }}>
                SENT 0.4s
              </span>
            </div>

            {/* Telemetry Footprint */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
              <span>Total Duration: 42s</span>
              <span>Autonomous Resolution: 100%</span>
              <span>Human Staff Time Saved: 100%</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ScrollStorytellingSection() {
  const [activeStep, setActiveStep] = useState(0);
  const stepRefs = useRef([]);

  useEffect(() => {
    // Intersection observer to track which step is centrally in view
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const index = Number(entry.target.getAttribute('data-step-index'));
            if (!isNaN(index)) {
              setActiveStep(index);
            }
          }
        });
      },
      {
        rootMargin: '-30% 0px -40% 0px', // Triggers when the item is in the middle reading area
        threshold: 0.2,
      }
    );

    stepRefs.current.forEach((el) => {
      if (el) observer.observe(el);
    });

    return () => observer.disconnect();
  }, []);

  return (
    <section
      id="workflow"
      className="scroll-story-section"
      style={{
        maxWidth: '1100px',
        margin: '0 auto',
        padding: '6rem 1.5rem',
        width: '100%',
        boxSizing: 'border-box',
        position: 'relative',
      }}
    >
      {/* Section Header */}
      <div style={{ textAlign: 'center', marginBottom: '4.5rem' }}>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '3px 12px',
            borderRadius: 'var(--radius-full)',
            background: 'rgba(16, 185, 129, 0.08)',
            border: '1px solid rgba(16, 185, 129, 0.25)',
            fontSize: '0.74rem',
            color: 'var(--mint-400)',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            marginBottom: '1rem',
          }}
        >
          <Sparkles size={12} />
          <span>Interactive Telephony Lifecycle</span>
        </div>

        <h2 style={{ fontSize: 'clamp(1.8rem, 3.5vw, 2.6rem)', fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text-primary)', marginBottom: '0.75rem' }}>
          How Answerly handles a call from first ring to confirmed booking
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', maxWidth: '640px', margin: '0 auto', lineHeight: 1.6 }}>
          Scroll through an autonomous inbound call journey. Observe how Answerly extracts intent, verifies live database inventory, and finalizes workflows with zero human delay.
        </p>
      </div>

      {/* Two-Column Layout on Desktop: Story Cards (Left) & Sticky Showcase (Right) */}
      <div className="story-layout-grid">
        {/* Left Column: 5 Narrative Steps */}
        <div className="story-steps-container">
          {STORY_STEPS.map((s, idx) => {
            const isActive = activeStep === idx;
            return (
              <div
                key={s.step}
                ref={(el) => (stepRefs.current[idx] = el)}
                data-step-index={idx}
                className={`story-step-card ${isActive ? 'is-active' : ''}`}
                style={{
                  padding: '2.5rem 1.75rem',
                  borderRadius: 'var(--radius-lg)',
                  background: isActive ? 'var(--bg-card)' : 'transparent',
                  border: '1px solid',
                  borderColor: isActive ? 'var(--border-medium)' : 'transparent',
                  transition: 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
                  marginBottom: '2rem',
                  boxShadow: isActive ? 'var(--shadow-md), var(--specular-top)' : 'none',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.65rem' }}>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      color: isActive ? 'var(--mint-400)' : 'var(--text-tertiary)',
                      background: isActive ? 'rgba(16, 185, 129, 0.12)' : 'rgba(255, 255, 255, 0.04)',
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-full)',
                      border: `1px solid ${isActive ? 'rgba(16, 185, 129, 0.3)' : 'var(--border-medium)'}`,
                    }}
                  >
                    STEP {s.step}
                  </span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    {s.badge}
                  </span>
                </div>

                <h3
                  style={{
                    fontSize: '1.35rem',
                    fontWeight: 700,
                    letterSpacing: '-0.02em',
                    color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                    marginBottom: '0.75rem',
                    transition: 'color 0.25s ease',
                  }}
                >
                  {s.title}
                </h3>

                <p
                  style={{
                    fontSize: '0.88rem',
                    color: isActive ? 'var(--text-secondary)' : 'var(--text-tertiary)',
                    lineHeight: 1.6,
                    marginBottom: '1.25rem',
                  }}
                >
                  {s.desc}
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                  {s.highlights.map((h, hIdx) => (
                    <div key={hIdx} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem', color: isActive ? 'var(--text-primary)' : 'var(--text-tertiary)' }}>
                      <CheckCircle2 size={13} style={{ color: isActive ? 'var(--mint-400)' : 'var(--text-tertiary)' }} />
                      <span>{h}</span>
                    </div>
                  ))}
                </div>

                {/* Mobile Inline Visual Preview */}
                <div className="mobile-only-preview" style={{ marginTop: '1.5rem', display: 'none' }}>
                  <StoryConsoleView activeStep={idx} />
                </div>
              </div>
            );
          })}
        </div>

        {/* Right Column: Sticky Device Showcase */}
        <div className="story-sticky-container">
          <div className="story-sticky-inner" style={{ position: 'sticky', top: '100px' }}>
            <StoryConsoleView activeStep={activeStep} />
          </div>
        </div>
      </div>
    </section>
  );
}
