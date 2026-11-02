import React, { useState } from 'react';
import { CalendarCheck, ShieldCheck, Zap, Radio, PhoneIncoming, RotateCcw } from 'lucide-react';

export default function HeroCallPreview({
  activePreview,
  activeIndustryId,
  onSelectIndustry,
  industries = [],
}) {
  const [demoCycle, setDemoCycle] = useState(0);

  const handleReplay = () => {
    setDemoCycle((c) => c + 1);
  };

  return (
    <div style={{ position: 'relative', width: '100%', maxWidth: '720px', margin: '0 auto' }}>
      {/* 1. Industry Switcher Tabs */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          gap: '0.45rem',
          marginBottom: '1.25rem',
          flexWrap: 'wrap',
        }}
      >
        {industries.map((ind) => {
          const isActive = ind.id === activeIndustryId;
          return (
            <button
              key={ind.id}
              type="button"
              onClick={() => onSelectIndustry && onSelectIndustry(ind.id)}
              style={{
                background: isActive ? '#ffffff' : 'var(--bg-surface-elevated)',
                color: isActive ? '#07080a' : 'var(--text-secondary)',
                border: `1px solid ${isActive ? '#ffffff' : 'var(--border-subtle)'}`,
                padding: '0.35rem 0.85rem',
                borderRadius: 'var(--radius-full)',
                fontSize: '0.78rem',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
            >
              {ind.title.split(' ')[0]}
            </button>
          );
        })}
      </div>

      {/* 2. Floating Call Container with Rotating Radar Circle Halo */}
      <div className="animate-float" style={{ position: 'relative' }}>
        {/* Radar dashed circle */}
        <div
          className="pointer-events-none"
          style={{
            position: 'absolute',
            inset: '-30px',
            zIndex: 0,
            display: 'grid',
            placeItems: 'center',
          }}
        >
          <div
            className="animate-spin-slow"
            style={{
              width: '420px',
              height: '420px',
              borderRadius: '50%',
              border: '1px dashed rgba(16, 185, 129, 0.25)',
            }}
          />
        </div>

        {/* The Glass Call Preview Card */}
        <div
          key={`${activeIndustryId}-${demoCycle}`}
          className="glass border-glow shadow-glow"
          style={{
            position: 'relative',
            zIndex: 1,
            borderRadius: 'var(--radius-2xl, 20px)',
            padding: '1.75rem',
            overflow: 'hidden',
          }}
        >
          {/* Scanning vertical light ray */}
          <div
            className="animate-scan"
            style={{
              position: 'absolute',
              insetInline: 0,
              top: 0,
              height: '35%',
              background: 'linear-gradient(to bottom, transparent, rgba(16, 185, 129, 0.12), transparent)',
              pointerEvents: 'none',
            }}
          />

          {/* Call Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
              <div
                style={{
                  width: '46px',
                  height: '46px',
                  borderRadius: '50%',
                  background: 'var(--gradient-primary)',
                  display: 'grid',
                  placeItems: 'center',
                  fontWeight: 800,
                  fontSize: '1.15rem',
                  fontFamily: 'var(--font-display)',
                  color: '#07080a',
                  boxShadow: 'var(--shadow-glow)',
                }}
              >
                A
              </div>
              <div>
                <p style={{ fontWeight: 700, fontSize: '0.94rem', color: 'var(--text-primary)', margin: 0 }}>
                  Aria · Autonomous Receptionist
                </p>
                <p style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', margin: '2px 0 0', fontFamily: 'var(--font-mono)' }}>
                  {activePreview?.businessName || 'Spice Garden Bistro'} • {activePreview?.phone || '+91 80 4123 5678'}
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  background: 'rgba(16, 185, 129, 0.15)',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  color: 'var(--color-emerald)',
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-full)',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  fontFamily: 'var(--font-mono)',
                }}
              >
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--color-emerald)' }} />
                LIVE
              </span>
              <button
                type="button"
                onClick={handleReplay}
                title="Restart simulated audio"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-tertiary)',
                  cursor: 'pointer',
                  padding: '4px',
                }}
              >
                <RotateCcw size={14} />
              </button>
            </div>
          </div>

          {/* 32-Bar Soundwave Visualizer */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '4px',
              height: '48px',
              margin: '1.25rem 0 1.5rem',
            }}
          >
            {Array.from({ length: 32 }).map((_, i) => (
              <span
                key={i}
                className="animate-wave"
                style={{
                  width: '3.5px',
                  height: '100%',
                  borderRadius: 'var(--radius-full)',
                  background: 'var(--gradient-primary)',
                  animationDelay: `${((i * 7) % 13) * -0.09}s`,
                  animationDuration: `${0.75 + (i % 5) * 0.15}s`,
                }}
              />
            ))}
          </div>

          {/* Dialogue Message Bubbles */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.85rem' }}>
            {/* Caller inquiry */}
            <div
              style={{
                alignSelf: 'flex-start',
                maxWidth: '85%',
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-secondary)',
                padding: '0.65rem 1rem',
                borderRadius: 'var(--radius-lg)',
                lineHeight: 1.45,
              }}
            >
              {activePreview?.dialogue?.[0]?.text || 'Namaste! Do you have a table for 4 tonight around 8 PM outside?'}
            </div>

            {/* AI Voice Receptionist Response */}
            <div
              style={{
                alignSelf: 'flex-end',
                maxWidth: '85%',
                background: 'rgba(16, 185, 129, 0.12)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                color: '#ffffff',
                padding: '0.65rem 1rem',
                borderRadius: 'var(--radius-lg)',
                lineHeight: 1.45,
              }}
            >
              {activePreview?.dialogue?.[3]?.text ||
                activePreview?.dialogue?.[1]?.text ||
                'Namaste! We have a lovely table on our garden patio open at 8:00 PM. Shall I confirm this reservation under your name?'}
            </div>

            {/* Confirmed Booking Event Pill */}
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.45rem 0.85rem',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-subtle)',
                fontSize: '0.75rem',
                color: 'var(--text-secondary)',
                alignSelf: 'flex-start',
              }}
            >
              <CalendarCheck size={14} color="var(--color-emerald)" />
              <span>
                {activePreview?.outcome || 'Booking Confirmed • Table #12 • SMS sent'}
              </span>
            </div>
          </div>

          {/* Live Telemetry Metadata Bar */}
          <div
            style={{
              marginTop: '1.5rem',
              paddingTop: '1rem',
              borderTop: '1px solid var(--border-subtle)',
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '0.5rem',
              fontSize: '0.72rem',
              fontFamily: 'var(--font-mono)',
              color: 'var(--text-tertiary)',
            }}
          >
            <div>
              LATENCY
              <p style={{ margin: '2px 0 0', color: 'var(--color-emerald)', fontSize: '0.85rem', fontWeight: 700 }}>
                180ms
              </p>
            </div>
            <div>
              INTENT
              <p style={{ margin: '2px 0 0', color: 'var(--color-emerald)', fontSize: '0.85rem', fontWeight: 700 }}>
                booking
              </p>
            </div>
            <div>
              SENTIMENT
              <p style={{ margin: '2px 0 0', color: 'var(--color-emerald)', fontSize: '0.85rem', fontWeight: 700 }}>
                +0.94
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
