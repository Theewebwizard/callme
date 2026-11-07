import React, { useState, useEffect } from 'react';
import { api } from '../api';

const DEFAULT_METRICS = [
  { value: '99.98%', label: 'telephony uptime' },
  { value: '<380ms', label: 'conversational pickup' },
  { value: 'Bilingual', label: 'English & Hindi accents' },
];

export default function MetricsSocialProofStrip() {
  const [metrics, setMetrics] = useState(DEFAULT_METRICS);

  useEffect(() => {
    let isMounted = true;
    api.getPlatformMetrics().then((data) => {
      if (isMounted && data) {
        setMetrics([
          { value: data.telephony_uptime || '99.98%', label: 'telephony uptime' },
          { value: data.conversational_pickup || '<380ms', label: 'conversational pickup' },
          { value: data.languages_label || 'Bilingual', label: data.languages_sublabel ? `${data.languages_sublabel} accents` : 'English & Hindi accents' },
        ]);
      }
    }).catch(() => {});

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <section className="reveal-on-scroll" style={{ maxWidth: '1080px', margin: '0 auto', padding: '0 1.5rem 3rem', width: '100%', boxSizing: 'border-box' }}>
      <div
        className="glass"
        style={{
          borderRadius: 'var(--radius-xl)',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          border: '1px solid var(--border-medium)',
          boxShadow: 'var(--card-shadow)',
          overflow: 'hidden',
        }}
      >
        {metrics.map((m, index) => (
          <div
            key={m.label}
            style={{
              padding: '1.85rem 1.5rem',
              textAlign: 'center',
              borderRight: index < metrics.length - 1 ? '1px solid var(--border-medium)' : 'none',
              borderBottom: 'none',
            }}
          >
            <p
              className="text-gradient"
              style={{
                fontSize: m.value.length > 6 ? '1.85rem' : '2.25rem',
                fontWeight: 800,
                fontFamily: 'var(--font-display)',
                margin: '0 0 4px',
                letterSpacing: '-0.02em',
                lineHeight: 1.15,
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
