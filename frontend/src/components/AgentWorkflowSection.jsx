import React, { useEffect, useRef, useState } from 'react';
import {
  PhoneIncoming,
  AudioLines,
  BrainCircuit,
  Database,
  CalendarCheck,
  Check,
  CircleCheck,
  RotateCcw,
  Workflow,
  Sparkles,
} from 'lucide-react';

export const WORKFLOW_STEPS = [
  {
    tag: 'Inbound telephony',
    stageLabel: 'Receive',
    title: 'A call arrives on the first ring',
    text: 'Never lose a high-value customer, whether during the dinner peak rush or at 3 AM when the front desk is closed. CallMe monitors your business DID line 24/7 with a sub-380ms pickup guarantee.',
    points: ['Picks up on the 1st ring', 'Zero dropped calls guarantee', 'Direct carrier DID binding'],
  },
  {
    tag: 'Bilingual voice engine',
    stageLabel: 'Respond',
    title: 'CallMe answers with natural human warmth',
    text: 'No frustrating "press 1 for reservations" IVR phone trees. CallMe immediately greets callers in fluent English or Hindi, detecting speech pauses and accents with ultra-low acoustic turn latency.',
    points: ['Natural English & Hindi code-switching', 'No robotic phone trees', '380ms conversational turn time'],
  },
  {
    tag: 'Semantic intent extraction',
    stageLabel: 'Understand',
    title: 'CallMe extracts the exact customer request',
    text: 'As callers speak naturally—"Hi, can we get a table for 4 tonight around 8 PM outside?"—CallMe accurately parses party size, time, date, dietary needs, or clinical symptoms grounded in your business policies.',
    points: ['Entity extraction (party, time, date)', 'FAQ knowledge grounding', 'Conversational context retention'],
  },
  {
    tag: 'Calendar & inventory truth',
    stageLabel: 'Verify',
    title: 'CallMe verifies live database availability',
    text: 'CallMe executes real-time database queries against your live room nights, restaurant tables, or doctor consultation chairs. It checks genuine availability, enforces party limits, and prevents double bookings.',
    points: ['Authoritative database lookup', 'Zero double-booking guarantee', 'Live capacity & party limits enforcement'],
  },
  {
    tag: 'Workflow resolution',
    stageLabel: 'Resolve',
    title: 'CallMe confirms and logs the entire transaction',
    text: 'The booking is committed to your authoritative database, a confirmation SMS with directions is dispatched to the caller’s mobile, and full turn-by-turn audio transcripts are synced to your cockpit.',
    points: ['Instant SMS confirmation dispatch', 'Structured Cockpit Audit Trail', '100% Autonomous Resolution'],
  },
];

const ICONS = [PhoneIncoming, AudioLines, BrainCircuit, Database, CalendarCheck];

export default function AgentWorkflowSection() {
  const ref = useRef(null);
  const [active, setActive] = useState(0);
  const [running, setRunning] = useState(false);
  const [cycle, setCycle] = useState(0);

  // Auto-start on intersection
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setRunning(!window.matchMedia('(prefers-reduced-motion: reduce)').matches);
          observer.disconnect();
        }
      },
      { threshold: 0.25 }
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Automatic cycle timer
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => {
      setActive((current) => {
        if (current >= WORKFLOW_STEPS.length - 1) {
          setRunning(false);
          return current;
        }
        return current + 1;
      });
    }, 2800);
    return () => window.clearInterval(timer);
  }, [running, cycle]);

  const step = WORKFLOW_STEPS[active] || WORKFLOW_STEPS[0];
  const ActiveIcon = ICONS[active] || BrainCircuit;

  const handleReplay = () => {
    setActive(0);
    setCycle((n) => n + 1);
    setRunning(!window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  };

  return (
    <section id="workflow" className="reveal-on-scroll" style={{ maxWidth: '1080px', margin: '0 auto', padding: '5rem 1.5rem', width: '100%', boxSizing: 'border-box' }}>
      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
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
          <Sparkles size={13} />
          <span>Autonomous Call Lifecycle</span>
        </div>
        <h2 style={{ fontSize: 'clamp(1.75rem, 4vw, 2.75rem)', fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--text-primary)', maxWidth: '820px', margin: '0 auto 0.85rem' }}>
          How CallMe handles a call from <span className="text-gradient">first ring to confirmed booking</span>
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.94rem', maxWidth: '640px', margin: '0 auto' }}>
          One receptionist. An intelligent, deterministic workflow from incoming caller speech to committed database transaction.
        </p>
      </div>

      <div
        ref={ref}
        className="glass"
        style={{
          borderRadius: 'var(--radius-xl)',
          border: '1px solid var(--border-medium)',
          overflow: 'hidden',
          boxShadow: 'var(--shadow-glow), var(--card-shadow)',
        }}
      >
        {/* Workspace Header */}
        <header
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            padding: '1rem 1.5rem',
            borderBottom: '1px solid var(--border-medium)',
            background: 'var(--bg-surface-elevated)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <Workflow size={18} color="var(--color-primary)" />
            <span style={{ fontWeight: 700, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Agent Orchestration Engine</span>
            <span style={{ fontSize: '0.72rem', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>
              / CALL HANDLER PIPELINE
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
            <span
              style={{
                fontSize: '0.72rem',
                fontFamily: 'var(--font-mono)',
                color: running ? 'var(--color-primary)' : active === 4 ? 'var(--sky-500)' : 'var(--text-secondary)',
                fontWeight: 600,
              }}
            >
              DEMO {running ? '● RUNNING' : active === 4 ? '✓ COMPLETE' : 'READY'}
            </span>
            <button
              type="button"
              onClick={handleReplay}
              title="Replay workflow demonstration"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                height: '32px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-medium)',
                color: 'var(--text-primary)',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              <RotateCcw size={15} />
            </button>
          </div>
        </header>

        {/* 5-Node Workflow Track */}
        <div className="workflow-track" role="tablist" aria-label="Call handling stages">
          {WORKFLOW_STEPS.map((item, index) => {
            const NodeIcon = ICONS[index] || BrainCircuit;
            const isCompleted = index < active;
            const isActive = index === active;
            return (
              <div
                key={item.tag}
                className={`workflow-node ${isActive ? 'is-active' : ''} ${isCompleted ? 'is-complete' : ''}`}
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  className="workflow-node-button"
                  onClick={() => {
                    setActive(index);
                    setRunning(false);
                  }}
                >
                  <span className="workflow-node-icon">
                    {isCompleted ? <Check size={18} /> : <NodeIcon size={18} />}
                  </span>
                  <span style={{ fontSize: '0.75rem', fontWeight: isActive ? 700 : 500 }}>
                    {item.stageLabel}
                  </span>
                </button>
              </div>
            );
          })}
        </div>

        {/* Detail Panel & Execution Trace */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            borderTop: '1px solid var(--border-medium)',
          }}
        >
          {/* Left: Active Stage Details */}
          <div style={{ padding: '2rem 2.25rem', flex: '1.4' }}>
            <div key={`${active}-${cycle}`} className="workflow-detail">
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  fontSize: '0.75rem',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--color-primary)',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                }}
              >
                <ActiveIcon size={15} />
                <span>Stage 0{active + 1} • {step.tag}</span>
              </div>

              <h3 style={{ fontSize: '1.45rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0.85rem 0 0.65rem' }}>
                {step.title}
              </h3>

              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, maxWidth: '580px', margin: '0 0 1.5rem' }}>
                {step.text}
              </p>

              <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {step.points.map((point) => (
                  <li
                    key={point}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '0.65rem',
                      fontSize: '0.86rem',
                      color: 'var(--text-primary)',
                    }}
                  >
                    <CircleCheck size={16} color="var(--color-primary)" style={{ marginTop: '2px', flexShrink: 0 }} />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Right: Live Execution Trace */}
          <aside
            style={{
              padding: '2rem 2rem',
              background: 'var(--bg-surface-elevated)',
              borderLeft: '1px solid var(--border-medium)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
            }}
          >
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <span style={{ fontSize: '0.72rem', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', letterSpacing: '0.05em' }}>
                  EXECUTION TRACE
                </span>
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--color-primary)',
                    fontWeight: 700,
                    background: 'color-mix(in oklab, var(--color-primary) 12%, transparent)',
                    padding: '2px 8px',
                    borderRadius: 'var(--radius-full)',
                    border: '1px solid color-mix(in oklab, var(--color-primary) 30%, transparent)',
                  }}
                >
                  {active + 1} / {WORKFLOW_STEPS.length}
                </span>
              </div>

              <ol style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '1.15rem' }}>
                {WORKFLOW_STEPS.map((item, index) => {
                  const isCompleted = index < active;
                  const isCurrent = index === active;
                  return (
                    <li
                      key={item.tag}
                      className={`workflow-log ${index <= active ? 'is-reached' : ''}`}
                      style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}
                    >
                      <span
                        style={{
                          width: '20px',
                          height: '20px',
                          borderRadius: '50%',
                          border: `1px solid ${index <= active ? 'color-mix(in oklab, var(--color-primary) 45%, transparent)' : 'var(--border-medium)'}`,
                          display: 'grid',
                          placeItems: 'center',
                          marginTop: '2px',
                          flexShrink: 0,
                          color: 'var(--color-primary)',
                          background: index <= active ? 'color-mix(in oklab, var(--color-primary) 12%, transparent)' : 'transparent',
                        }}
                      >
                        {isCompleted ? (
                          <Check size={11} strokeWidth={3} />
                        ) : (
                          <span
                            style={{
                              width: '6px',
                              height: '6px',
                              borderRadius: '50%',
                              background: isCurrent ? 'var(--color-primary)' : 'var(--text-tertiary)',
                            }}
                          />
                        )}
                      </span>
                      <div>
                        <p style={{ fontSize: '0.8rem', fontWeight: 600, color: index <= active ? 'var(--text-primary)' : 'var(--text-secondary)', margin: 0 }}>
                          {item.tag}
                        </p>
                        <p style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', margin: '2px 0 0' }}>
                          {isCompleted ? '✓ Completed' : isCurrent ? '● Active stage' : 'Queued'}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>

            <div
              style={{
                marginTop: '2rem',
                paddingTop: '1rem',
                borderTop: '1px solid var(--border-medium)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.65rem',
                fontSize: '0.76rem',
                color: 'var(--text-secondary)',
              }}
            >
              <BrainCircuit size={16} color="var(--color-primary)" />
              <span>Aria · Autonomous Receptionist Agent</span>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
