import React, { useState, useEffect, useRef } from 'react';
import {
  Phone,
  PhoneCall,
  CheckCircle2,
  Calendar,
  Sparkles,
  Play,
  Pause,
  RotateCcw,
  Zap,
  ShieldCheck,
  Clock,
  Radio,
  ArrowRight,
} from 'lucide-react';

export const DEMO_STAGES = [
  { id: 'incoming', label: '1. Incoming Ring' },
  { id: 'answered', label: '2. Auto Answer' },
  { id: 'caller_inquiry', label: '3. Caller Inquiry' },
  { id: 'ai_response', label: '4. AI Voice Response' },
  { id: 'tool_check', label: '5. Calendar Check' },
  { id: 'confirmed', label: '6. Confirmed Outcome' },
];

/**
 * Deterministic Simulated Waveform Bar
 * Clearly labeled as a simulated product demonstration waveform.
 */
function SimulatedWaveform({ stage, isPaused }) {
  // 24 bars with deterministic frequency heights depending on the active stage
  const barCount = 28;

  const getBarHeight = (i) => {
    if (stage === 'incoming') {
      // Periodic ring pulse
      return (i % 4 === 0 ? 65 : 20);
    }
    if (stage === 'caller_inquiry') {
      // Human vocal frequency pattern (higher mid frequencies)
      const distFromCenter = Math.abs(i - barCount / 2);
      const base = Math.max(15, 80 - distFromCenter * 4);
      return (i % 2 === 0 ? base : base * 0.6);
    }
    if (stage === 'ai_response') {
      // Smooth synthesized HD audio pattern
      const angle = (i / barCount) * Math.PI * 2;
      return Math.sin(angle) * 35 + 50;
    }
    if (stage === 'tool_check') {
      // Rapid radar scan pulses
      return (i % 3 === 0 ? 70 : 15);
    }
    if (stage === 'confirmed') {
      // Gentle harmonic hum
      return 25 + Math.sin(i * 0.5) * 15;
    }
    // Idle / answered
    return 18 + (i % 3) * 6;
  };

  const getWaveformTheme = () => {
    switch (stage) {
      case 'incoming':
        return { label: 'Simulated Inbound Ringing (0.2s Auto-Answer)', color: 'var(--amber-500)', glow: 'rgba(245, 158, 11, 0.3)' };
      case 'caller_inquiry':
        return { label: 'Simulated Inbound Caller Audio • 8kHz PCM', color: 'var(--sky-500)', glow: 'rgba(56, 189, 248, 0.3)' };
      case 'ai_response':
        return { label: 'Simulated CallMe Neural Voice Synthesis • 24kHz HD', color: 'var(--mint-400)', glow: 'rgba(16, 185, 129, 0.4)' };
      case 'tool_check':
        return { label: 'Simulated Real-Time Database Query Pulse', color: 'var(--indigo-400)', glow: 'rgba(99, 102, 241, 0.3)' };
      case 'confirmed':
        return { label: 'Call Workflow Completed • 100% Autonomous', color: 'var(--mint-400)', glow: 'rgba(16, 185, 129, 0.4)' };
      default:
        return { label: 'Simulated WebRTC Audio Channel Active', color: 'var(--mint-400)', glow: 'rgba(16, 185, 129, 0.3)' };
    }
  };

  const theme = getWaveformTheme();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', letterSpacing: '0.04em' }}>
          AUDIO SPECTRUM (SIMULATED DEMO)
        </span>
        <span style={{ fontSize: '0.7rem', fontFamily: 'var(--font-mono)', color: theme.color, display: 'flex', alignItems: 'center', gap: '5px' }}>
          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: theme.color, boxShadow: `0 0 6px ${theme.glow}` }} />
          {theme.label}
        </span>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '3px',
          height: '42px',
          padding: '4px 8px',
          background: 'rgba(255, 255, 255, 0.02)',
          border: '1px solid var(--border-medium)',
          borderRadius: 'var(--radius-sm)',
        }}
      >
        {Array.from({ length: barCount }).map((_, i) => {
          const height = getBarHeight(i);
          return (
            <div
              key={i}
              style={{
                flex: 1,
                height: `${height}%`,
                background: theme.color,
                borderRadius: '1px',
                opacity: isPaused ? 0.35 : 0.85,
                transition: 'height 0.25s cubic-bezier(0.16, 1, 0.3, 1), background 0.3s ease',
              }}
            />
          );
        })}
      </div>
    </div>
  );
}

export default function AnimatedReceptionistDemo({ activePreview, activeIndustryId, onSelectIndustry, industries }) {
  const [stageIndex, setStageIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const containerRef = useRef(null);
  const [inView, setInView] = useState(true);

  const stage = DEMO_STAGES[stageIndex].id;

  // Track if hero is in view to pause timer when user scrolls past
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        setInView(entry.isIntersecting);
      },
      { threshold: 0.1 }
    );
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Stage timer intervals (in ms)
  const STAGE_DURATIONS = {
    incoming: 2800,
    answered: 2200,
    caller_inquiry: 3600,
    ai_response: 3600,
    tool_check: 2800,
    confirmed: 4500,
  };

  useEffect(() => {
    if (isPaused || !inView) return;

    const duration = (STAGE_DURATIONS[stage] || 3000) / playbackSpeed;
    const timer = setTimeout(() => {
      setStageIndex((prev) => (prev + 1) % DEMO_STAGES.length);
    }, duration);

    return () => clearTimeout(timer);
  }, [stageIndex, isPaused, inView, playbackSpeed, stage]);

  const handleRestart = () => {
    setStageIndex(0);
    setIsPaused(false);
  };

  return (
    <div
      ref={containerRef}
      className="call-simulation-container"
      id="industries"
      style={{
        position: 'relative',
        transition: 'transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s ease',
      }}
    >
      {/* 1. Header Bar with Telephony Telemetry */}
      <div className="call-simulation-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: stage === 'incoming' ? 'var(--amber-500)' : 'var(--mint-500)',
              boxShadow: stage === 'incoming' ? '0 0 10px rgba(245, 158, 11, 0.8)' : '0 0 10px rgba(16, 185, 129, 0.8)',
              animation: 'pulse 1.8s infinite',
            }}
          />
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
              {activePreview.businessName}
            </span>
            <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
              Inbound DID: {activePreview.phone}
            </span>
          </div>
        </div>

        {/* Telephony metrics */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span
            style={{
              fontSize: '0.72rem',
              fontFamily: 'var(--font-mono)',
              color: 'var(--mint-400)',
              background: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              padding: '2px 7px',
              borderRadius: '4px',
            }}
          >
            RTT: 280ms
          </span>
          <span
            style={{
              fontSize: '0.72rem',
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-mono)',
              background: 'var(--bg-surface-elevated)',
              border: '1px solid var(--border-medium)',
              padding: '2px 7px',
              borderRadius: '4px',
            }}
          >
            WEBRTC LIVE
          </span>
        </div>
      </div>

      {/* 2. Industry Selector Bar with Smooth Transition Triggers */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.65rem 1.25rem',
          borderBottom: '1px solid var(--border-medium)',
          background: 'var(--bg-surface-elevated)',
          flexWrap: 'wrap',
          gap: '0.6rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', overflowX: 'auto' }}>
          <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginRight: '4px' }}>
            Industry:
          </span>
          {industries.map((p) => {
            const isSelected = activeIndustryId === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  onSelectIndustry(p.id);
                  setStageIndex(0); // Restart demo on industry switch to show full flow
                }}
                style={{
                  padding: '0.28rem 0.65rem',
                  borderRadius: 'var(--radius-full)',
                  border: isSelected ? '1px solid var(--border-strong)' : '1px solid transparent',
                  background: isSelected ? 'rgba(255, 255, 255, 0.1)' : 'transparent',
                  color: isSelected ? 'var(--color-primary)' : 'var(--text-secondary)',
                  fontSize: '0.76rem',
                  fontWeight: isSelected ? 600 : 500,
                  cursor: 'pointer',
                  transition: 'all var(--transition-fast)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                {isSelected && <span style={{ width: '4px', height: '4px', borderRadius: '50%', background: 'var(--mint-400)' }} />}
                {p.title.split('&')[0].trim()}
              </button>
            );
          })}
        </div>

        {/* Playback Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <button
            type="button"
            onClick={() => setIsPaused(!isPaused)}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-medium)',
              color: 'var(--text-secondary)',
              padding: '2px 8px',
              borderRadius: 'var(--radius-xs)',
              fontSize: '0.72rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              cursor: 'pointer',
            }}
            title={isPaused ? 'Resume Demonstration' : 'Pause Demonstration'}
          >
            {isPaused ? <Play size={10} /> : <Pause size={10} />}
            <span>{isPaused ? 'Resume' : 'Pause'}</span>
          </button>

          <button
            type="button"
            onClick={handleRestart}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-medium)',
              color: 'var(--text-secondary)',
              padding: '2px 8px',
              borderRadius: 'var(--radius-xs)',
              fontSize: '0.72rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              cursor: 'pointer',
            }}
            title="Restart from Ringing"
          >
            <RotateCcw size={10} />
            <span>Replay</span>
          </button>
        </div>
      </div>

      {/* 3. Stage Progress Checkpoints (Interactive Scrubbing) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(6, 1fr)',
          borderBottom: '1px solid var(--border-medium)',
          background: 'rgba(7, 8, 10, 0.6)',
        }}
      >
        {DEMO_STAGES.map((s, idx) => {
          const isActive = stageIndex === idx;
          const isPassed = stageIndex > idx;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => setStageIndex(idx)}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid var(--mint-400)' : '2px solid transparent',
                padding: '6px 4px',
                fontSize: '0.66rem',
                fontFamily: 'var(--font-mono)',
                color: isActive ? 'var(--color-primary)' : isPassed ? 'var(--text-secondary)' : 'var(--text-tertiary)',
                fontWeight: isActive ? 600 : 400,
                cursor: 'pointer',
                textAlign: 'center',
                transition: 'all 0.15s ease',
              }}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      {/* 4. Main Demonstration Body */}
      <div className="call-simulation-body" style={{ padding: '1.25rem', minHeight: '340px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
        {/* State 1: Incoming Ring State */}
        {stage === 'incoming' && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '2.5rem 1rem',
              textAlign: 'center',
              animation: 'fadeInUp 0.3s ease both',
            }}
          >
            <div
              style={{
                width: '64px',
                height: '64px',
                borderRadius: '50%',
                background: 'rgba(245, 158, 11, 0.12)',
                border: '1px solid rgba(245, 158, 11, 0.35)',
                color: 'var(--amber-500)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: '1rem',
                boxShadow: '0 0 24px rgba(245, 158, 11, 0.25)',
              }}
            >
              <PhoneCall size={28} className="pulse-ring" />
            </div>

            <div style={{ fontSize: '0.74rem', color: 'var(--amber-500)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '4px' }}>
              ● Inbound Call Detected
            </div>
            <div style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
              Caller: Rohit Verma
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', marginBottom: '1.25rem' }}>
              Routing through carrier trunk • DID {activePreview.phone}
            </div>

            <div
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                padding: '6px 14px',
                borderRadius: 'var(--radius-full)',
                fontSize: '0.72rem',
                color: 'var(--text-secondary)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              Guaranteed Pickup on 1st Ring (Latency &lt; 380ms)
            </div>
          </div>
        )}

        {/* State 2 to 6: Active Call Dialogue Stream */}
        {stage !== 'incoming' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', flex: 1, animation: 'fadeIn 0.25s ease both' }}>
            {/* Call Connected Header Chip */}
            <div
              style={{
                alignSelf: 'center',
                background: 'rgba(16, 185, 129, 0.08)',
                border: '1px solid rgba(16, 185, 129, 0.22)',
                padding: '3px 10px',
                borderRadius: 'var(--radius-full)',
                fontSize: '0.7rem',
                color: 'var(--mint-400)',
                fontFamily: 'var(--font-mono)',
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
              }}
            >
              <Radio size={11} />
              <span>Call Connected • Bidirectional Streaming Active</span>
            </div>

            {/* Turn 1: Caller Inquiry */}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-start',
                maxWidth: '85%',
                alignSelf: 'flex-start',
                opacity: 1,
                transform: 'translateY(0)',
                transition: 'all 0.3s ease',
              }}
            >
              <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginBottom: '3px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span>Rohit Verma (Caller)</span>
                {stage === 'caller_inquiry' && <span style={{ color: 'var(--sky-500)', fontSize: '0.65rem' }}>● Speaking</span>}
              </div>
              <div
                style={{
                  background: 'var(--bg-surface-elevated)',
                  color: 'var(--text-primary)',
                  border: stage === 'caller_inquiry' ? '1px solid var(--sky-500)' : '1px solid var(--border-medium)',
                  padding: '0.65rem 0.95rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.84rem',
                  lineHeight: 1.5,
                  boxShadow: stage === 'caller_inquiry' ? '0 0 12px rgba(56, 189, 248, 0.15)' : 'none',
                }}
              >
                {activePreview.dialogue[0].text}
              </div>
            </div>

            {/* Turn 2: Receptionist Initial Answer */}
            {(stageIndex >= 3) && (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-end',
                  maxWidth: '85%',
                  alignSelf: 'flex-end',
                  animation: 'fadeInUp 0.3s ease both',
                }}
              >
                <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginBottom: '3px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  {stage === 'ai_response' && <span style={{ color: 'var(--mint-400)', fontSize: '0.65rem' }}>● Synthesizing Speech</span>}
                  <span>{activePreview.businessName} Receptionist</span>
                </div>
                <div
                  style={{
                    background: '#ffffff',
                    color: '#07080a',
                    padding: '0.65rem 0.95rem',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.84rem',
                    lineHeight: 1.5,
                    fontWeight: 500,
                    boxShadow: stage === 'ai_response' ? '0 0 16px rgba(255, 255, 255, 0.2)' : 'none',
                  }}
                >
                  {activePreview.dialogue[1].text}
                </div>
              </div>
            )}

            {/* Turn 3: Tool Execution Trace (Calendar Slot Radar) */}
            {(stageIndex >= 4) && (
              <div
                style={{
                  alignSelf: 'center',
                  background: 'var(--bg-surface-elevated)',
                  border: stage === 'tool_check' ? '1px solid var(--indigo-500)' : '1px solid var(--border-medium)',
                  padding: '0.45rem 0.95rem',
                  borderRadius: 'var(--radius-full)',
                  fontSize: '0.74rem',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--mint-400)',
                  boxShadow: 'var(--specular-top)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  animation: 'scaleIn 0.25s ease both',
                }}
              >
                <Zap size={13} style={{ color: 'var(--amber-500)' }} />
                <span>{activePreview.dialogue[2].text}</span>
              </div>
            )}

            {/* Turn 4: Final Confirmation */}
            {(stageIndex >= 5) && (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-end',
                  maxWidth: '85%',
                  alignSelf: 'flex-end',
                  animation: 'fadeInUp 0.3s ease both',
                }}
              >
                <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginBottom: '3px' }}>
                  {activePreview.businessName} Receptionist
                </div>
                <div
                  style={{
                    background: '#ffffff',
                    color: '#07080a',
                    padding: '0.65rem 0.95rem',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.84rem',
                    lineHeight: 1.5,
                    fontWeight: 500,
                  }}
                >
                  {activePreview.dialogue[3].text}
                </div>
              </div>
            )}

            {/* Confirmed Resolution Card */}
            {(stageIndex >= 5) && (
              <div
                style={{
                  marginTop: '0.5rem',
                  background: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                  padding: '0.75rem 1rem',
                  borderRadius: 'var(--radius-sm)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  animation: 'fadeInUp 0.3s ease both',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <CheckCircle2 size={16} style={{ color: 'var(--mint-400)' }} />
                  <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    Session Outcome: {activePreview.outcome}
                  </span>
                </div>
                <span style={{ fontSize: '0.72rem', color: 'var(--mint-400)', fontFamily: 'var(--font-mono)' }}>
                  SMS DISPATCHED • 0.4s
                </span>
              </div>
            )}
          </div>
        )}

        {/* 5. Real-Time Simulated Waveform Visualizer */}
        <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--border-medium)' }}>
          <SimulatedWaveform stage={stage} isPaused={isPaused} />
        </div>
      </div>
    </div>
  );
}
