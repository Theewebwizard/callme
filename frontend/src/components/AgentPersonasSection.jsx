import React from 'react';
import { Check, Bot, Sparkles, ArrowRight } from 'lucide-react';

export const AGENT_PERSONAS = [
  {
    name: 'Aria',
    role: 'Front Desk & Hospitality',
    voice: 'Warm & Natural · English, Hindi',
    rate: '$149',
    industryPreset: 'Restaurant',
    demoBusiness: 'Spice Garden Bistro',
    greeting: 'Namaste! Welcome to Spice Garden Bistro. How can I assist you with reservations or dining today?',
    features: [
      'Unlimited inbound voice calls',
      'Live table inventory & seat booking',
      'Semantic menu pricing & dish lookup',
      'Instant SMS voucher dispatch',
    ],
  },
  {
    name: 'Leo',
    role: 'Clinic & Healthcare',
    voice: 'Calm & Reassuring · 12 languages',
    rate: '$199',
    industryPreset: 'Clinic',
    demoBusiness: 'Apex Multi-Specialty Clinic',
    greeting: 'Good day! Welcome to Apex Clinic. Would you like to schedule an appointment with one of our doctors?',
    features: [
      'Doctor consultation schedule check',
      'Clinical symptom safety triage transfer',
      'Patient appointment SMS reminders',
      'Encrypted & confidential call audit',
    ],
  },
  {
    name: 'Nova',
    role: 'Luxury Hotel & Hospitality',
    voice: 'Polished & Welcoming · English, Hindi',
    rate: '$249',
    industryPreset: 'Hotel',
    demoBusiness: 'The Heritage Palace Resort',
    greeting: 'Hello and welcome to The Heritage Palace Resort. May I assist you with suite bookings or amenities?',
    features: [
      'Real-time room & suite availability',
      'Check-in & amenities guidance',
      'VIP guest priority transfer',
      'Direct carrier DID line binding',
    ],
  },
];

export default function AgentPersonasSection({ onSelectPersona }) {
  return (
    <section id="agents" className="reveal-on-scroll" style={{ maxWidth: '1100px', margin: '0 auto', padding: '5rem 1.5rem', width: '100%', boxSizing: 'border-box' }}>
      <div style={{ textAlign: 'center', marginBottom: '3.5rem' }}>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.45rem',
            padding: '0.28rem 0.8rem',
            borderRadius: 'var(--radius-full)',
            background: 'rgba(16, 185, 129, 0.1)',
            border: '1px solid rgba(16, 185, 129, 0.25)',
            color: 'var(--color-emerald)',
            fontSize: '0.74rem',
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
            marginBottom: '0.85rem',
          }}
        >
          <Bot size={13} />
          <span>Pre-Trained Receptionists</span>
        </div>
        <h2 style={{ fontSize: 'clamp(1.75rem, 4vw, 2.75rem)', fontWeight: 700, letterSpacing: '-0.03em', color: '#ffffff', margin: '0 auto 0.85rem' }}>
          Meet your next hire
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.94rem', maxWidth: '600px', margin: '0 auto' }}>
          Each autonomous receptionist is pre-trained for a specific industry domain. Tailor voice, script, and operating policies in minutes.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(310px, 1fr))', gap: '1.5rem' }}>
        {AGENT_PERSONAS.map((agent) => (
          <div
            key={agent.name}
            className="agent-card glass"
            style={{
              padding: '1.85rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
            }}
          >
            <div>
              {/* Header with Monogram Icon */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.25rem' }}>
                <div
                  style={{
                    width: '54px',
                    height: '54px',
                    borderRadius: 'var(--radius-lg)',
                    background: 'var(--gradient-primary)',
                    color: '#07080a',
                    display: 'grid',
                    placeItems: 'center',
                    fontSize: '1.35rem',
                    fontWeight: 800,
                    fontFamily: 'var(--font-display)',
                    boxShadow: 'var(--shadow-glow)',
                  }}
                >
                  {agent.name[0]}
                </div>
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontFamily: 'var(--font-mono)',
                    padding: '2px 8px',
                    borderRadius: 'var(--radius-full)',
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-tertiary)',
                  }}
                >
                  {agent.industryPreset}
                </span>
              </div>

              <h3 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#ffffff', margin: '0 0 4px' }}>
                {agent.name}
              </h3>
              <p style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--color-emerald)', margin: '0 0 4px' }}>
                {agent.role}
              </p>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '0 0 1.25rem' }}>
                {agent.voice}
              </p>

              {/* Feature Highlights */}
              <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 1.5rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                {agent.features.map((feat) => (
                  <li key={feat} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    <Check size={14} color="var(--color-emerald)" style={{ flexShrink: 0 }} />
                    <span>{feat}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Pricing & CTA */}
            <div style={{ paddingTop: '1.25rem', borderTop: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <span style={{ fontSize: '1.75rem', fontWeight: 800, color: '#ffffff', fontFamily: 'var(--font-display)' }}>
                  {agent.rate}
                </span>
                <span style={{ fontSize: '0.76rem', color: 'var(--text-tertiary)', marginLeft: '3px' }}>
                  /mo
                </span>
              </div>

              <button
                type="button"
                className="btn-primary"
                onClick={() => onSelectPersona && onSelectPersona(agent)}
                style={{
                  padding: '0.45rem 1rem',
                  fontSize: '0.82rem',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <span>Hire {agent.name}</span>
                <ArrowRight size={13} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
