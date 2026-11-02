import React from 'react';
import {
  Phone,
  CalendarCheck,
  MessageSquare,
  Globe,
  Zap,
  ShieldCheck,
} from 'lucide-react';

const features = [
  { icon: Phone, title: 'Answers every call', text: 'Picks up in under a second, day or night.' },
  { icon: CalendarCheck, title: 'Books appointments', text: 'Syncs with your calendar and confirms by SMS.' },
  { icon: MessageSquare, title: 'Chat & WhatsApp', text: 'One receptionist across voice, web and messaging.' },
  { icon: Globe, title: '30+ languages', text: 'Speaks to customers in the language they prefer.' },
  { icon: Zap, title: 'Live in 10 minutes', text: 'Upload your FAQs, pick a voice, forward your number.' },
  { icon: ShieldCheck, title: 'Secure by default', text: 'Encrypted call logs and role-based access.' },
];

export default function FeatureGridSection() {
  return (
    <section
      id="features"
      className="reveal-on-scroll"
      style={{
        maxWidth: '1152px',
        margin: '0 auto',
        padding: '0 1.5rem 6rem',
        width: '100%',
        boxSizing: 'border-box',
      }}
    >
      <h2
        style={{
          fontSize: 'clamp(1.75rem, 4vw, 2.5rem)',
          fontWeight: 700,
          letterSpacing: '-0.025em',
          color: 'var(--text-primary)',
          margin: '0 0 2.5rem',
        }}
      >
        Everything a front desk does. <span className="text-gradient">Faster.</span>
      </h2>

      <div className="feature-grid-matrix">
        {features.map(({ icon: Icon, title, text }) => (
          <div key={title} className="feature-grid-cell">
            <div className="feature-grid-dots bg-dots" />

            <div
              style={{
                position: 'relative',
                width: '40px',
                height: '40px',
                borderRadius: '8px',
                border: '1px solid color-mix(in oklab, var(--color-primary) 35%, transparent)',
                background: 'color-mix(in oklab, var(--color-primary) 10%, transparent)',
                color: 'var(--color-primary)',
                display: 'grid',
                placeItems: 'center',
              }}
            >
              <Icon size={18} />
            </div>

            <h3
              style={{
                marginTop: '1rem',
                marginBottom: '0.35rem',
                fontSize: '1.05rem',
                fontWeight: 600,
                color: 'var(--text-primary)',
              }}
            >
              {title}
            </h3>

            <p
              style={{
                margin: 0,
                fontSize: '0.875rem',
                color: 'var(--text-secondary)',
                lineHeight: 1.5,
              }}
            >
              {text}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
