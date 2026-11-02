import React from 'react';

const METRICS = [
  { value: '99.98%', label: 'telephony uptime' },
  { value: '<380ms', label: 'conversational pickup' },
  { value: '1.2M+', label: 'autonomous calls handled' },
  { value: '30+', label: 'languages & regional accents' },
];

export default function MetricsSocialProofStrip() {
  return (
    <section className="reveal-on-scroll" style={{ maxWidth: '1080px', margin: '0 auto', padding: '0 1.5rem 3rem', width: '100%', boxSizing: 'border-box' }}>
      <div
        className="glass"
        style={{
          borderRadius: 'var(--radius-xl)',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          border: '1px solid var(--border-medium)',
          boxShadow: 'var(--card-shadow)',
          overflow: 'hidden',
        }}
      >
        {METRICS.map((m, index) => (
          <div
            key={m.label}
            style={{
              padding: '1.75rem 1.5rem',
              textAlign: 'center',
              borderRight: index < METRICS.length - 1 ? '1px solid var(--border-medium)' : 'none',
              borderBottom: 'none',
            }}
          >
            <p
              className="text-gradient"
              style={{
                fontSize: '2.25rem',
                fontWeight: 800,
                fontFamily: 'var(--font-display)',
                margin: '0 0 4px',
                letterSpacing: '-0.02em',
              }}
            >
              {m.value}
            </p>
            <p
              style={{
                fontSize: '0.72rem',
                fontFamily: 'var(--font-mono)',
                textTransform: 'uppercase',
                color: 'var(--text-tertiary)',
                margin: 0,
                letterSpacing: '0.04em',
              }}
            >
              {m.label}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
