import React from 'react';
import { Check } from 'lucide-react';

export const AGENT_PERSONAS = [
  {
    name: 'Aria',
    role: 'Front Desk',
    voice: 'Warm · English, Hindi',
    rate: '$149',
    features: ['Unlimited calls', 'Calendar & CRM sync', 'Call summaries'],
    industryPreset: 'Restaurant',
  },
  {
    name: 'Leo',
    role: 'Clinic & Appointments',
    voice: 'Calm · 12 languages',
    rate: '$199',
    features: ['Unlimited calls', 'Calendar & CRM sync', 'Call summaries'],
    industryPreset: 'Clinic',
  },
  {
    name: 'Nova',
    role: 'Sales & Lead Qualifier',
    voice: 'Energetic · English',
    rate: '$249',
    features: ['Unlimited calls', 'Calendar & CRM sync', 'Call summaries'],
    industryPreset: 'Hotel',
  },
];

export default function AgentPersonasSection({ onSelectPersona }) {
  return (
    <section id="agents" className="reveal-on-scroll" style={{ maxWidth: '1140px', margin: '0 auto', padding: '4rem 1.5rem', width: '100%', boxSizing: 'border-box' }}>
      <h2 style={{ fontSize: 'clamp(1.85rem, 3.5vw, 2.5rem)', fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--text-primary)', margin: '0 0 0.5rem', fontFamily: 'var(--font-display)' }}>
        Meet your next hire
      </h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.98rem', maxWidth: '640px', margin: '0 0 2.5rem' }}>
        Each receptionist is pre-trained for a role. Customize voice, script and hours.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: '1.5rem' }}>
        {AGENT_PERSONAS.map((a) => (
          <div
            key={a.name}
            className="agent-card glass"
            style={{
              borderRadius: '20px',
              padding: '1.75rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-medium)',
              boxShadow: 'var(--card-shadow)',
              transition: 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          >
            <div>
              {/* Monogram Squircle Avatar with crisp border matching Image 1 */}
              <div
                style={{
                  width: '52px',
                  height: '52px',
                  borderRadius: '14px',
                  background: 'var(--primary)',
                  border: '1px solid color-mix(in oklab, var(--color-primary) 35%, transparent)',
                  display: 'grid',
                  placeItems: 'center',
                  fontFamily: 'var(--font-display)',
                  fontSize: '1.35rem',
                  fontWeight: 700,
                  color: '#ffffff',
                  marginBottom: '1.25rem',
                  boxShadow: '0 4px 14px color-mix(in oklab, var(--color-primary) 25%, transparent)',
                }}
              >
                {a.name[0]}
              </div>

              <h3 style={{ fontSize: '1.35rem', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 4px', fontFamily: 'var(--font-display)' }}>
                {a.name}
              </h3>
              <p style={{ fontSize: '0.88rem', fontWeight: 500, color: 'var(--color-primary)', margin: '0 0 4px' }}>
                {a.role}
              </p>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0 0 1.25rem' }}>
                {a.voice}
              </p>

              {/* 3 Bullets with Blue Checkmarks matching Image 1 */}
              <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 1.75rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                {a.features.map((f) => (
                  <li key={f} style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
                    <Check size={14} color="var(--color-primary)" style={{ flexShrink: 0 }} />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Bottom Row matching Image 1 */}
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', borderTop: '1px solid var(--border-medium)', paddingTop: '1.25rem' }}>
              <p style={{ margin: 0 }}>
                <span style={{ fontFamily: 'var(--font-display)', fontSize: '1.85rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {a.rate}
                </span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>/mo</span>
              </p>
              <button
                type="button"
                onClick={() => onSelectPersona && onSelectPersona(a)}
                className="hire-btn"
                style={{
                  padding: '0.5rem 1.25rem',
                  borderRadius: '10px',
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-medium)',
                  color: 'var(--text-primary)',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'var(--color-primary)';
                  e.currentTarget.style.background = 'var(--bg-surface-elevated)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border-medium)';
                  e.currentTarget.style.background = 'var(--bg-card)';
                }}
              >
                Hire {a.name}
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
