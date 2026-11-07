import React, { useState } from 'react';
import { CalendarCheck, RotateCcw } from 'lucide-react';

export default function HeroCallPreview({
  activePreview,
  activeIndustryId,
  onSelectIndustry,
  industries = [],
  onReplay,
}) {
  const [internalCycle, setInternalCycle] = useState(0);

  const handleReplay = () => {
    setInternalCycle((c) => c + 1);
    if (onReplay) onReplay();
  };

  return (
    <div className="hero-call-preview-wrapper" style={{ position: 'relative', width: '100%', maxWidth: '520px', margin: '0 auto' }}>
      {/* 1. Rotating Dashed Radar Circle Halo behind the card */}
      <div
        className="pointer-events-none"
        style={{
          position: 'absolute',
          inset: '-36px',
          zIndex: 0,
          display: 'grid',
          placeItems: 'center',
        }}
        aria-hidden="true"
      >
        <div
          className="animate-spin-slow"
          style={{
            width: '460px',
            height: '460px',
            borderRadius: '50%',
            border: '1px dashed color-mix(in oklab, var(--color-primary) 30%, transparent)',
          }}
        />
      </div>

      {/* 2. Floating Call Card */}
      <div className="animate-float" style={{ position: 'relative', zIndex: 1 }}>
        <div
          key={`${activeIndustryId}-${internalCycle}`}
          className="call-preview glass border-glow shadow-glow"
          style={{
            position: 'relative',
            borderRadius: '22px',
            padding: '1.75rem',
            overflow: 'hidden',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-medium)',
            boxShadow: 'var(--card-shadow)',
          }}
        >
          {/* Scanning light ray */}
          <div
            className="animate-scan pointer-events-none"
            style={{
              position: 'absolute',
              insetInline: 0,
              top: 0,
              height: '34%',
              background: 'linear-gradient(to bottom, transparent, color-mix(in oklab, var(--color-primary) 12%, transparent), transparent)',
            }}
          />

          {/* Call Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
              <div
                style={{
                  width: '46px',
                  height: '46px',
                  borderRadius: '50%',
                  background: 'var(--gradient-primary)',
                  display: 'grid',
                  placeItems: 'center',
                  fontWeight: 700,
                  fontSize: '1.25rem',
                  fontFamily: 'var(--font-display)',
                  color: '#ffffff',
                  boxShadow: '0 4px 14px color-mix(in oklab, var(--color-primary) 35%, transparent)',
                }}
              >
                A
              </div>
              <div>
                <p style={{ fontWeight: 700, fontSize: '0.98rem', color: 'var(--text-primary)', margin: 0 }}>
                  Aria · On a live call
                </p>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '2px 0 0', fontFamily: 'var(--font-mono)' }}>
                  {activePreview?.businessName || 'Bright Smile Dental'} · 00:42
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  background: 'color-mix(in oklab, var(--color-primary) 14%, transparent)',
                  border: '1px solid color-mix(in oklab, var(--color-primary) 28%, transparent)',
                  color: 'var(--color-primary)',
                  padding: '3px 9px',
                  borderRadius: 'var(--radius-full)',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  fontFamily: 'var(--font-mono)',
                  letterSpacing: '0.04em',
                }}
              >
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--color-primary)' }} />
                LIVE
              </span>
              <button
                type="button"
                onClick={handleReplay}
                title="Restart simulated audio"
                style={{
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: '6px',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  padding: '4px 6px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'all 0.2s ease',
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
              height: '46px',
              margin: '1.35rem 0 1.5rem',
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.88rem' }}>
            {/* Caller inquiry */}
            <div
              style={{
                alignSelf: 'flex-start',
                maxWidth: '85%',
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                color: 'var(--text-primary)',
                padding: '0.65rem 1.05rem',
                borderRadius: '14px',
                lineHeight: 1.45,
              }}
            >
              {activePreview?.dialogue?.[0]?.text || 'Hi, can I book a cleaning for Friday?'}
            </div>

            {/* AI Voice Receptionist Response */}
            <div
              style={{
                alignSelf: 'flex-end',
                maxWidth: '85%',
                background: 'color-mix(in oklab, var(--color-primary) 13%, transparent)',
                border: '1px solid color-mix(in oklab, var(--color-primary) 24%, transparent)',
                color: 'var(--text-primary)',
                padding: '0.65rem 1.05rem',
                borderRadius: '14px',
                lineHeight: 1.45,
              }}
            >
              {activePreview?.dialogue?.[1]?.text ||
                'Of course! I have 10:30 AM or 3:00 PM open on Friday. Which works best?'}
            </div>

            {/* Confirmed Booking Event Pill */}
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '0.35rem 0.75rem',
                borderRadius: '10px',
                background: 'var(--bg-card)',
                border: '1px solid var(--border-medium)',
                fontSize: '0.75rem',
                color: 'var(--text-secondary)',
                alignSelf: 'flex-start',
                marginTop: '2px',
              }}
            >
              <CalendarCheck size={14} color="var(--color-primary)" />
              <span>
                {activePreview?.outcome || 'Appointment booked · Fri 10:30 AM · SMS sent'}
              </span>
            </div>
          </div>

          {/* Live Telemetry Metadata Bar */}
          <div
            style={{
              marginTop: '1.4rem',
              paddingTop: '1rem',
              borderTop: '1px solid var(--border-medium)',
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '0.5rem',
              fontSize: '0.72rem',
              fontFamily: 'var(--font-mono)',
              color: 'var(--text-secondary)',
            }}
          >
            <div>
              <div style={{ letterSpacing: '0.06em', fontSize: '10px' }}>LATENCY</div>
              <p style={{ margin: '3px 0 0', color: 'var(--color-primary)', fontSize: '0.92rem', fontWeight: 700 }}>
                180ms
              </p>
            </div>
            <div>
              <div style={{ letterSpacing: '0.06em', fontSize: '10px' }}>INTENT</div>
              <p style={{ margin: '3px 0 0', color: 'var(--color-primary)', fontSize: '0.92rem', fontWeight: 700 }}>
                booking
              </p>
            </div>
            <div>
              <div style={{ letterSpacing: '0.06em', fontSize: '10px' }}>SENTIMENT</div>
              <p style={{ margin: '3px 0 0', color: 'var(--color-primary)', fontSize: '0.92rem', fontWeight: 700 }}>
                +0.92
              </p>
            </div>
          </div>
        </div>

        {/* Industry Switcher Pills */}
        {industries.length > 0 && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'center',
              gap: '0.45rem',
              marginTop: '1rem',
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
                    background: isActive ? 'var(--color-primary)' : 'var(--bg-card)',
                    color: isActive ? 'var(--text-inverse)' : 'var(--text-secondary)',
                    border: `1px solid ${isActive ? 'var(--color-primary)' : 'var(--border-medium)'}`,
                    padding: '0.25rem 0.65rem',
                    borderRadius: 'var(--radius-full)',
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    boxShadow: isActive ? '0 2px 8px color-mix(in oklab, var(--color-primary) 30%, transparent)' : 'none',
                  }}
                >
                  {ind.title.split(' ')[0]}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
