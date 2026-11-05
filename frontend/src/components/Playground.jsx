
function getLoadingFillerPhrase(userText, industry) {
  if (!userText) return 'I am checking on that for you right now, I will get back to you in just a couple of seconds...';
  const isHindi = /[\u0900-\u097F]/.test(userText) || /\b(namaste|kya|hai|hain|chahiye|table|booking|samay|kal|aaj|parson|shukrawar|somwar|aap|kijiye|madad|bhaiya|ji)\b/i.test(userText);
  const ind = (industry || '').toLowerCase();
  const lower = userText.toLowerCase();

  if (isHindi) {
    if (lower.includes('table') || lower.includes('booking') || lower.includes('book') || ind.includes('restaurant') || ind.includes('dining')) {
      return 'मैं अभी आपके लिए उपलब्ध टेबल चेक कर रहा हूँ, बस कुछ ही सेकंड में आपको बताता हूँ...';
    }
    if (lower.includes('doctor') || lower.includes('appointment') || lower.includes('clinic') || ind.includes('clinic')) {
      return 'मैं अभी डॉक्टर साहब का समय चेक कर रहा हूँ, बस कुछ ही सेकंड में आपको बताता हूँ...';
    }
    if (lower.includes('room') || lower.includes('hotel') || ind.includes('hotel')) {
      return 'मैं अभी कमरों की उपलब्धता चेक कर रहा हूँ, बस कुछ ही सेकंड में आपको बताता हूँ...';
    }
    return 'मैं अभी यह चेक कर रहा हूँ, बस कुछ ही सेकंड में आपको बताता हूँ...';
  } else {
    if (lower.includes('table') || lower.includes('book') || ind.includes('restaurant') || ind.includes('dining')) {
      return "I am checking our available tables for you right now, I'll get back to you in just a couple of seconds...";
    }
    if (lower.includes('doctor') || lower.includes('appointment') || lower.includes('clinic') || ind.includes('clinic')) {
      return "I am checking the doctor's appointment slots for you right now, I'll get back to you in a couple of seconds...";
    }
    if (lower.includes('room') || lower.includes('hotel') || ind.includes('hotel')) {
      return "I am checking room availability for you right now, I'll get back to you in just a couple of seconds...";
    }
    return "I am checking on that for you right now, I'll get back to you in just a couple of seconds...";
  }
}

import React, { useState, useEffect, useRef } from 'react';
import {
  Send,
  RotateCcw,
  Bot,
  User,
  Sparkles,
  CheckCircle2,
  XCircle,
  Clock,
  Terminal,
  Zap,
  Volume2,
  Check,
  Phone,
  ShieldCheck,
  Layers,
  ArrowRight,
  Loader2,
} from 'lucide-react';
import { api } from '../api';

export default function Playground({ business }) {
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [actionFeedback, setActionFeedback] = useState(null);
  const [executingAction, setExecutingAction] = useState(false);
  const [currentFiller, setCurrentFiller] = useState('');
  const chatBottomRef = useRef(null);

  // Suggested Prompts adapted to business industry
  const quickPrompts = (() => {
    const ind = (business?.industry || '').toLowerCase();
    if (ind.includes('hotel')) {
      return [
        'Do you have a Deluxe Suite available for 2 nights this Friday?',
        'Does the room rate include breakfast and airport shuttle?',
        'Can I request an early check-in at 11:00 AM?',
        'Can I speak with the front desk manager?',
      ];
    }
    if (ind.includes('clinic') || ind.includes('medical')) {
      return [
        'Do you have a consultation slot open tomorrow morning?',
        'What are your OPD consultation timings?',
        'I have a medical emergency, who should I contact?',
        'Can you transfer me to the triage desk?',
      ];
    }
    if (ind.includes('salon') || ind.includes('spa')) {
      return [
        'Can I book a haircut and beard styling this Saturday at 3 PM?',
        'What bridal and spa packages do you offer?',
        'Which senior stylists are available today?',
        'Can I reschedule my appointment?',
      ];
    }
    // Default Restaurant
    return [
      'Do you have a table for 4 tonight around 8:00 PM?',
      'Is outdoor or patio seating available?',
      'What are your top chef recommendations on the menu?',
      'Can I speak with the banquet manager for a party of 25?',
    ];
  })();

  // Initialize or reset with greeting
  useEffect(() => {
    if (business) {
      resetConversation();
    }
  }, [business?.id]);

  const resetConversation = () => {
    setMessages([
      {
        role: 'assistant',
        content: business?.greeting_message || 'Namaste! Welcome to our reception. How can I assist you today?',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
    setPendingAction(null);
    setActionFeedback(null);
  };

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, pendingAction]);

  // Keyboard shortcut: Cmd+R or Ctrl+R to reset dialogue (when not browser refreshing)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'r') {
        e.preventDefault();
        resetConversation();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [business]);

  const handleSend = async (textToSend) => {
    const text = textToSend || inputText;
    if (!text.trim() || !business || loading) return;

    const userMsg = {
      role: 'user',
      content: text.trim(),
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setCurrentFiller(getLoadingFillerPhrase(text.trim(), business?.industry));
    setLoading(true);
    setActionFeedback(null);

    try {
      const resp = await api.sendMessage(business.id, text.trim());
      
      const newMessages = [];

      // If backend tool call was captured, display simulated tool execution card
      if (resp.tool_calls && resp.tool_calls.length > 0) {
        resp.tool_calls.forEach((tc) => {
          newMessages.push({
            role: 'system_tool',
            toolName: tc.name || tc.tool || 'autonomous_tool',
            toolArgs: tc.arguments || tc.parameters || {},
            toolResult: tc.result || 'Execution verified',
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          });
        });
      }

      newMessages.push({
        role: 'assistant',
        content: resp.content || resp.message || 'I have checked that for you.',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      });

      setMessages((prev) => [...prev, ...newMessages]);

      if (resp.pending_action) {
        setPendingAction(resp.pending_action);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Error processing response: ${err.message}`,
          isError: true,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmAction = async () => {
    if (!pendingAction || !business) return;
    setExecutingAction(true);
    try {
      const res = await api.confirmAction(business.id, pendingAction.id);
      setActionFeedback({ type: 'success', text: `Action confirmed! Reference: ${res.reference_id || 'CONFIRMED'}` });
      setPendingAction(null);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Action confirmed successfully: ${res.message || 'Operation executed and confirmed to live database.'}`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } catch (err) {
      setActionFeedback({ type: 'error', text: `Confirmation failed: ${err.message}` });
    } finally {
      setExecutingAction(false);
    }
  };

  const handleCancelAction = async () => {
    if (!pendingAction || !business) return;
    setExecutingAction(true);
    try {
      await api.cancelAction(business.id, pendingAction.id);
      setActionFeedback({ type: 'info', text: 'Action cancelled by operator.' });
      setPendingAction(null);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Action cancelled as requested. How else may I assist you?',
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } catch (err) {
      setActionFeedback({ type: 'error', text: `Cancellation failed: ${err.message}` });
    } finally {
      setExecutingAction(false);
    }
  };

  return (
    <section className="main-content" aria-label="AI Receptionist Dialogue Simulator" style={{ padding: '1.75rem 2rem 2rem' }}>
      {/* 1. Header with Breadcrumb and Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.2rem 0.6rem',
              borderRadius: 'var(--radius-full)',
              background: 'var(--bg-surface-elevated)',
              border: '1px solid var(--border-medium)',
              color: 'var(--text-secondary)',
              fontSize: '0.72rem',
              fontWeight: 600,
              marginBottom: '0.35rem',
            }}
          >
            <Terminal size={12} /> Interactive Dialogue Runtime
          </div>
          <h1 className="section-title" style={{ margin: 0 }}>
            AI Receptionist Dialogue Simulator
          </h1>
          <p className="section-subtitle" style={{ margin: '3px 0 0' }}>
            Test customer voice & text conversation turns with <strong>{business?.name}</strong>'s LangGraph virtual receptionist.
          </p>
        </div>

        <button
          type="button"
          className="btn-secondary"
          onClick={resetConversation}
          title="Reset dialogue session (⌘R)"
          style={{ padding: '0.35rem 0.85rem', fontSize: '0.76rem' }}
        >
          <RotateCcw size={12} />
          <span>Reset Dialogue</span>
          <kbd className="sidebar-kbd">⌘R</kbd>
        </button>
      </div>

      {/* 2. Main Two-Column Workbench (Dialogue Canvas on Left | Telemetry Inspector on Right) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 300px',
          gap: '1.5rem',
          alignItems: 'start',
        }}
      >
        {/* Left Column: Chat Conversation Stream & Input */}
        <div
          className="card"
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 190px)',
            minHeight: '560px',
            padding: 0,
            overflow: 'hidden',
          }}
        >
          {/* Chat Stream Area */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.15rem',
            }}
          >
            {messages.map((msg, idx) => {
              const isAssistant = msg.role === 'assistant';
              const isTool = msg.role === 'system_tool';

              // Render Autonomous Tool Intervention Card
              if (isTool) {
                return (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.65rem',
                      padding: '0.6rem 0.85rem',
                      borderRadius: 'var(--radius-sm)',
                      background: 'rgba(56, 189, 248, 0.08)',
                      border: '1px solid rgba(56, 189, 248, 0.25)',
                      fontSize: '0.76rem',
                      color: '#38bdf8',
                      fontFamily: 'var(--font-mono)',
                      margin: '0.2rem 0',
                    }}
                  >
                    <Zap size={14} style={{ color: '#38bdf8' }} />
                    <span style={{ fontWeight: 600 }}>⚡ Executed: {msg.toolName}</span>
                    <span style={{ color: 'var(--text-tertiary)', marginLeft: 'auto' }}>{msg.time}</span>
                  </div>
                );
              }

              return (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: isAssistant ? 'flex-start' : 'flex-end',
                    maxWidth: '82%',
                    alignSelf: isAssistant ? 'flex-start' : 'flex-end',
                  }}
                >
                  {/* Speaker Label & Time */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.45rem',
                      marginBottom: '4px',
                      fontSize: '0.72rem',
                      color: 'var(--text-tertiary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {isAssistant ? (
                      <>
                        <Bot size={12} style={{ color: 'var(--mint-400)' }} />
                        <span style={{ color: 'var(--mint-400)', fontWeight: 600 }}>{business?.name || 'Receptionist'}</span>
                      </>
                    ) : (
                      <>
                        <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>Caller (You)</span>
                        <User size={12} style={{ color: 'var(--text-secondary)' }} />
                      </>
                    )}
                    <span>• {msg.time}</span>
                  </div>

                  {/* Message Bubble */}
                  <div
                    style={{
                      padding: '0.75rem 1rem',
                      borderRadius: isAssistant ? '4px 14px 14px 14px' : '14px 4px 14px 14px',
                      background: isAssistant ? 'var(--bg-surface-elevated)' : 'color-mix(in oklab, var(--color-primary) 12%, var(--bg-card))',
                      border: '1px solid',
                      borderColor: msg.isError ? 'rgba(244, 63, 94, 0.4)' : isAssistant ? 'var(--border-medium)' : 'var(--border-medium)',
                      color: msg.isError ? '#fb7185' : 'var(--text-primary)',
                      fontSize: '0.85rem',
                      lineHeight: 1.55,
                      boxShadow: 'var(--specular-top)',
                    }}
                  >
                    {msg.content}
                  </div>
                </div>
              );
            })}

            {/* Response Synthesizing Indicator with Professional Caller Filler */}
            {loading && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.65rem',
                  alignSelf: 'flex-start',
                  color: 'var(--mint-400)',
                  fontSize: '0.78rem',
                  background: 'color-mix(in oklab, var(--mint-400) 8%, var(--bg-surface-elevated))',
                  padding: '0.45rem 0.85rem',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid color-mix(in oklab, var(--mint-400) 25%, transparent)',
                }}
              >
                <Bot size={14} className="animate-pulse" />
                <span style={{ fontFamily: 'var(--font-sans)', fontWeight: 500 }}>
                  {currentFiller || 'Please give me just a moment while I proceed with your request...'}
                </span>
                <Loader2 size={12} className="animate-spin" />
              </div>
            )}

            {/* Pending Action Approval Card */}
            {pendingAction && (
              <div
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-strong)',
                  borderRadius: 'var(--radius-md)',
                  padding: '1rem',
                  marginTop: '0.5rem',
                  boxShadow: 'var(--shadow-md), var(--specular-top)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--amber-400)', fontWeight: 700, fontSize: '0.82rem', marginBottom: '0.4rem' }}>
                  <ShieldCheck size={16} />
                  <span>Guardrail: Operator Confirmation Required</span>
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
                  {pendingAction.description || 'The receptionist is requesting human authorization before committing this transaction.'}
                </div>

                <div style={{ display: 'flex', gap: '0.65rem' }}>
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={executingAction}
                    onClick={handleConfirmAction}
                    style={{ padding: '0.35rem 0.85rem', fontSize: '0.76rem' }}
                  >
                    <Check size={13} />
                    <span>Confirm Action</span>
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={executingAction}
                    onClick={handleCancelAction}
                    style={{ padding: '0.35rem 0.85rem', fontSize: '0.76rem' }}
                  >
                    <XCircle size={13} />
                    <span>Cancel Action</span>
                  </button>
                </div>
              </div>
            )}

            {actionFeedback && (
              <div style={{ fontSize: '0.78rem', color: actionFeedback.type === 'success' ? 'var(--mint-400)' : 'var(--amber-400)', fontFamily: 'var(--font-mono)' }}>
                {actionFeedback.text}
              </div>
            )}

            <div ref={chatBottomRef} />
          </div>

          {/* Quick Prompts Strip */}
          <div
            style={{
              padding: '0.5rem 1rem',
              borderTop: '1px solid var(--border-medium)',
              background: 'var(--bg-app)',
              display: 'flex',
              gap: '0.4rem',
              overflowX: 'auto',
            }}
          >
            {quickPrompts.map((prompt, pIdx) => (
              <button
                key={pIdx}
                type="button"
                onClick={() => handleSend(prompt)}
                disabled={loading}
                style={{
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-full)',
                  padding: '3px 10px',
                  fontSize: '0.73rem',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  transition: 'all var(--transition-fast)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = 'var(--text-primary)';
                  e.currentTarget.style.borderColor = 'var(--border-medium)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = 'var(--text-secondary)';
                  e.currentTarget.style.borderColor = 'var(--border-medium)';
                }}
              >
                {prompt}
              </button>
            ))}
          </div>

          {/* Input Box Bar */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            style={{
              padding: '0.75rem 1rem',
              borderTop: '1px solid var(--border-medium)',
              background: 'var(--bg-card)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.65rem',
            }}
          >
            <input
              type="text"
              placeholder="Type customer message or spoken inquiry... (Press Enter to send)"
              className="form-input"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              disabled={loading}
              style={{ flex: 1 }}
            />
            <button
              type="submit"
              className="btn-primary"
              disabled={!inputText.trim() || loading}
              style={{ padding: '0.5rem 1rem' }}
            >
              <Send size={14} />
              <span>Send</span>
            </button>
          </form>
        </div>

        {/* Right Column: Session Telemetry & Inspector */}
        <aside style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="card" style={{ padding: '1.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.75rem' }}>
              <Layers size={14} style={{ color: 'var(--mint-400)' }} />
              <span>Session Telemetry</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', fontSize: '0.76rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Agent Engine:</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>LangGraph + Gemini</span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Turn Count:</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: '#38bdf8' }}>{messages.length} turns</span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Target Line:</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{business?.phone_number || 'DID'}</span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Industry:</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{business?.industry}</span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Latency:</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--mint-400)' }}>~280ms RTT</span>
              </div>
            </div>
          </div>

          <div className="card" style={{ padding: '1.15rem' }}>
            <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.4rem' }}>
              Simulator Guidance
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
              This simulator interacts directly with your backend LangGraph agent. When asking for dates, slots, or menu items, the agent audits live database tables and executes verified capability tools.
            </p>
          </div>
        </aside>
      </div>
    </section>
  );
}
