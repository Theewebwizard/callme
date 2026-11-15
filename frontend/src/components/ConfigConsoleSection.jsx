import React from 'react';
import { Terminal, Zap, CheckCircle2 } from 'lucide-react';

export default function ConfigConsoleSection() {
  return (
    <section className="reveal-on-scroll" style={{ maxWidth: '1080px', margin: '0 auto', padding: '4rem 1.5rem', width: '100%', boxSizing: 'border-box' }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '2.5rem',
          alignItems: 'center',
        }}
      >
        {/* Left: Headline & Explanation */}
        <div>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.45rem',
              padding: '0.28rem 0.8rem',
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
            <Zap size={13} />
            <span>Instant Deployment</span>
          </div>

          <h2 style={{ fontSize: 'clamp(1.75rem, 3.5vw, 2.5rem)', fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--text-primary)', margin: '0 0 1rem' }}>
            Configure in plain English. <span className="text-gradient">Ship in minutes.</span>
          </h2>

          <p style={{ color: 'var(--text-secondary)', fontSize: '0.94rem', lineHeight: 1.6, maxWidth: '480px', margin: '0 0 1.5rem' }}>
            Tell your receptionist how your business operates. It connects directly to your table or room inventory, menu store, and DID carrier line without engineering overhead.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', fontSize: '0.85rem', color: 'var(--text-primary)' }}>
              <CheckCircle2 size={16} color="var(--color-primary)" />
              <span>Zero-code declarative policy setup</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', fontSize: '0.85rem', color: 'var(--text-primary)' }}>
              <CheckCircle2 size={16} color="var(--color-primary)" />
              <span>Direct Twilio / SIP DID trunk integration</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', fontSize: '0.85rem', color: 'var(--text-primary)' }}>
              <CheckCircle2 size={16} color="var(--color-primary)" />
              <span>Built-in multi-tenant inventory & pricing databases</span>
            </div>
          </div>
        </div>

        {/* Right: macOS Terminal Box */}
        <div className="config-console glass" style={{ overflow: 'hidden', border: '1px solid var(--border-medium)', borderRadius: '1.25rem', boxShadow: 'var(--card-shadow)' }}>
          {/* Window Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '0.75rem 1rem',
              borderBottom: '1px solid var(--border-medium)',
              background: 'var(--bg-surface-elevated)',
            }}
          >
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#ef4444' }} />
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#f59e0b' }} />
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#10b981' }} />
            <span style={{ marginLeft: '8px', fontSize: '0.72rem', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>
              answerly.config.yaml
            </span>
          </div>

          {/* Terminal Code Body */}
          <pre
            style={{
              padding: '1.25rem 1.5rem',
              margin: 0,
              fontSize: '0.82rem',
              fontFamily: 'var(--font-mono)',
              lineHeight: 1.7,
              color: 'var(--text-secondary)',
              overflowX: 'auto',
            }}
          >
            <span>receptionist: </span><span style={{ color: 'var(--color-primary)', fontWeight: 600 }}>"Aria"</span>{'\n'}
            <span>tenant_domain: </span><span style={{ color: 'var(--color-primary)', fontWeight: 600 }}>"Spice Garden Bistro"</span>{'\n'}
            <span>voice_persona: </span><span style={{ color: 'var(--color-primary)', fontWeight: 600 }}>"warm-hi-en"</span>{'\n'}
            <span>operating_hours: </span><span style={{ color: 'var(--color-primary)', fontWeight: 600 }}>"24/7 autonomous"</span>{'\n'}
            <span>authoritative_tools: </span>{'\n'}
            <span>  - </span><span style={{ color: '#0ea5e9' }}>table_inventory_engine</span>{'\n'}
            <span>  - </span><span style={{ color: '#0ea5e9' }}>semantic_menu_pricing</span>{'\n'}
            <span>  - </span><span style={{ color: '#0ea5e9' }}>sms_voucher_dispatch</span>{'\n'}
            <span style={{ color: 'var(--color-primary)', fontWeight: 700 }}>{'> answerly deploy --live --verify'}</span>{'\n'}
            <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>✓ DID Line Bound · Receptionist Online · 380ms Latency</span>
            <span className="animate-blink" style={{ color: 'var(--color-primary)', fontWeight: 800 }}>▍</span>
          </pre>
        </div>
      </div>
    </section>
  );
}
