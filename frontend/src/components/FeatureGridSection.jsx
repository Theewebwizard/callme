import React from 'react';
import {
  Phone,
  CalendarCheck,
  MessageSquare,
  Globe,
  Zap,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';

const FEATURES = [
  {
    icon: Phone,
    title: 'Answers every call',
    text: 'Picks up on the first ring, day or night. Never lose a high-value customer during peak hours or at 3 AM.',
  },
  {
    icon: CalendarCheck,
    title: 'Autonomous reservations & bookings',
    text: 'Queries live database table, room, or doctor suite availability and locks in confirmed bookings without double-booking.',
  },
  {
    icon: MessageSquare,
    title: 'Voice, WebPhone & SMS dispatch',
    text: 'A unified receptionist intelligence accessible through carrier DID telephony, browser audio, and instant SMS confirmations.',
  },
  {
    icon: Globe,
    title: 'Bilingual & accent adaptive',
    text: 'Naturally code-switches between fluent English and Hindi with conversational acoustic turn latency under 380ms.',
  },
  {
    icon: Zap,
    title: 'Live in 10 minutes',
    text: 'Upload your menu or FAQs, configure your business operating hours, pick an agent persona, and start receiving live calls.',
  },
  {
    icon: ShieldCheck,
    title: 'Enterprise safety & escalation',
    text: 'Grounded in deterministic tool execution. High-stakes emergency calls transfer immediately to human staff.',
  },
];

export default function FeatureGridSection() {
  return (
    <section id="features" className="reveal-on-scroll" style={{ maxWidth: '1100px', margin: '0 auto', padding: '5rem 1.5rem', width: '100%', boxSizing: 'border-box' }}>
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
          <Sparkles size={13} />
          <span>Core Capabilities</span>
        </div>
        <h2 style={{ fontSize: 'clamp(1.75rem, 4vw, 2.75rem)', fontWeight: 700, letterSpacing: '-0.03em', color: '#ffffff', margin: '0 auto 0.85rem' }}>
          Everything a front desk does. <span className="text-gradient">Faster.</span>
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.94rem', maxWidth: '600px', margin: '0 auto' }}>
          Built to solve real scheduling bottlenecks, phone tag, and missed business calls without adding overhead.
        </p>
      </div>

      <div
        className="glass"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '1px',
          background: 'var(--border-subtle)',
          borderRadius: 'var(--radius-xl)',
          overflow: 'hidden',
          boxShadow: 'var(--card-shadow)',
        }}
      >
        {FEATURES.map(({ icon: Icon, title, text }) => (
          <div
            key={title}
            className="bg-dots"
            style={{
              background: 'var(--bg-card)',
              padding: '2.25rem',
              display: 'flex',
              flexDirection: 'column',
              transition: 'background 0.25s, transform 0.25s',
            }}
          >
            <div
              style={{
                width: '42px',
                height: '42px',
                borderRadius: 'var(--radius-md)',
                background: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                color: 'var(--color-emerald)',
                display: 'grid',
                placeItems: 'center',
                marginBottom: '1.25rem',
              }}
            >
              <Icon size={20} />
            </div>

            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#ffffff', margin: '0 0 0.5rem' }}>
              {title}
            </h3>

            <p style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
              {text}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
