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
} from 'lucide-react';
import { api } from '../api';

const QUICK_PROMPTS = [
  'What are your operating hours?',
  'What services or menu items do you provide?',
  'Book an appointment for tomorrow at 4:00 PM for 2 people',
  'Can I speak with a human receptionist?',
];

export default function Playground({ business }) {
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [actionFeedback, setActionFeedback] = useState(null);
  const chatBottomRef = useRef(null);

  // Initialize or reset with greeting
  useEffect(() => {
    if (business) {
      setMessages([
        {
          role: 'assistant',
          content: business.greeting_message || 'Hello! Welcome to our reception. How can I assist you today?',
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
      setPendingAction(null);
      setActionFeedback(null);
    }
  }, [business?.id]);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pendingAction]);

  const handleSend = async (textToSend) => {
    const text = textToSend || inputText;
    if (!text.trim() || !business) return;

    const userMsg = {
      role: 'user',
      content: text.trim(),
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setLoading(true);
    setActionFeedback(null);

    try {
      const resp = await api.sendMessage(business.id, text.trim());
      const aiMsg = {
        role: 'assistant',
        content: resp.content,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, aiMsg]);

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
    try {
      const res = await api.confirmAction(business.id, pendingAction.id);
      setActionFeedback({ type: 'success', text: `Action confirmed! Reference: ${res.reference_id || 'CONFIRMED'}` });
      setPendingAction(null);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Action confirmed successfully: ${res.message || 'Operation executed.'}`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } catch (err) {
      setActionFeedback({ type: 'error', text: `Confirmation failed: ${err.message}` });
    }
  };

  const handleCancelAction = async () => {
    if (!pendingAction || !business) return;
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
    }
  };

  if (!business) {
    return (
      <div className="main-content">
        <div className="card" style={{ textAlign: 'center', padding: '3.5rem 1.5rem' }}>
          <h3>No Business Selected</h3>
          <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
            Please select or register a business in Receptionist Setup to test the virtual receptionist.
          </p>
        </div>
      </div>
    );
  }

  return (
    <section className="main-content" aria-label="AI Receptionist Playground Simulator">
      <div className="section-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.25rem 0.65rem',
                borderRadius: 'var(--radius-full)',
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-secondary)',
                fontSize: '0.74rem',
                fontWeight: 600,
                marginBottom: '0.45rem',
              }}
            >
              <Terminal size={12} /> Interactive Dialogue Runtime
            </div>
            <h1 className="section-title">AI Receptionist Voice & Dialogue Simulator</h1>
            <p className="section-subtitle">
              Simulate customer voice and text conversations with <strong>{business.name}</strong>'s LangGraph virtual receptionist.
            </p>
          </div>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setMessages([
                {
                  role: 'assistant',
                  content: business.greeting_message || 'Hello! Welcome to our reception. How can I assist you today?',
                  time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                },
              ]);
              setPendingAction(null);
              setActionFeedback(null);
            }}
          >
            <RotateCcw size={14} />
            <span>Reset Dialogue</span>
            <kbd>R</kbd>
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', height: '620px' }}>
        {/* Chat Messages Log */}
        <div style={{ flex: 1, padding: '1.5rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem', background: 'var(--bg-app)' }}>
          {messages.map((m, idx) => {
            const isUser = m.role === 'user';
            return (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  gap: '0.75rem',
                  alignItems: 'flex-start',
                  alignSelf: isUser ? 'flex-end' : 'flex-start',
                  maxWidth: '82%',
                }}
              >
                {!isUser && (
                  <div
                    style={{
                      width: '30px',
                      height: '30px',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--bg-surface-elevated)',
                      border: '1px solid var(--border-medium)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#ffffff',
                      flexShrink: 0,
                    }}
                    aria-hidden="true"
                  >
                    <Bot size={15} />
                  </div>
                )}

                <div>
                  <div
                    style={{
                      padding: '0.75rem 1.1rem',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.86rem',
                      lineHeight: 1.55,
                      background: isUser ? '#ffffff' : 'var(--bg-card)',
                      color: isUser ? '#07080a' : 'var(--text-primary)',
                      border: isUser ? 'none' : '1px solid var(--border-subtle)',
                      boxShadow: 'var(--shadow-sm)',
                      fontWeight: isUser ? 500 : 400,
                    }}
                  >
                    {m.content}
                  </div>
                  <div
                    style={{
                      fontSize: '0.7rem',
                      color: 'var(--text-tertiary)',
                      marginTop: '0.3rem',
                      textAlign: isUser ? 'right' : 'left',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {m.time}
                  </div>
                </div>

                {isUser && (
                  <div
                    style={{
                      width: '30px',
                      height: '30px',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--bg-surface-elevated)',
                      border: '1px solid var(--border-subtle)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'var(--text-secondary)',
                      flexShrink: 0,
                    }}
                    aria-hidden="true"
                  >
                    <User size={15} />
                  </div>
                )}
              </div>
            );
          })}

          {loading && (
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <div
                style={{
                  width: '30px',
                  height: '30px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-medium)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#ffffff',
                }}
              >
                <Bot size={15} />
              </div>
              <div
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '0.65rem 1rem',
                  fontSize: '0.8rem',
                  color: 'var(--text-secondary)',
                  fontStyle: 'italic',
                }}
              >
                {business.name} Virtual Receptionist is thinking...
              </div>
            </div>
          )}

          {/* Pending Action Approval Card */}
          {pendingAction && (
            <div
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-strong)',
                borderRadius: 'var(--radius-md)',
                padding: '1.25rem',
                margin: '0.5rem 0',
                boxShadow: 'var(--shadow-md), var(--specular-top)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#ffffff', fontWeight: 600, fontSize: '0.88rem' }}>
                <Sparkles size={15} /> Human Operator Approval Required
              </div>
              <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: '0.35rem' }}>
                The receptionist proposed executing autonomous action: <strong>{pendingAction.action_type}</strong>
              </div>

              <div
                style={{
                  background: 'var(--bg-app)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-subtle)',
                  padding: '0.75rem',
                  margin: '0.75rem 0',
                  fontSize: '0.78rem',
                }}
              >
                <pre style={{ margin: 0, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {JSON.stringify(pendingAction.parameters || {}, null, 2)}
                </pre>
              </div>

              <div style={{ display: 'flex', gap: '0.65rem' }}>
                <button
                  type="button"
                  className="btn-primary"
                  style={{ padding: '0.45rem 1rem', fontSize: '0.8rem' }}
                  onClick={handleConfirmAction}
                >
                  <CheckCircle2 size={14} /> Confirm & Execute
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ padding: '0.45rem 1rem', fontSize: '0.8rem' }}
                  onClick={handleCancelAction}
                >
                  <XCircle size={14} /> Cancel Action
                </button>
              </div>
            </div>
          )}

          <div ref={chatBottomRef} />
        </div>

        {/* Quick Suggestion Chips */}
        <div
          style={{
            padding: '0.6rem 1.25rem',
            background: 'var(--bg-card)',
            borderTop: '1px solid var(--border-subtle)',
            display: 'flex',
            gap: '0.45rem',
            overflowX: 'auto',
          }}
        >
          {QUICK_PROMPTS.map((prompt, i) => (
            <button
              key={i}
              type="button"
              style={{
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-full)',
                padding: '0.25rem 0.75rem',
                fontSize: '0.74rem',
                fontWeight: 500,
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all var(--transition-fast)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-strong)';
                e.currentTarget.style.color = '#ffffff';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-subtle)';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }}
              onClick={() => handleSend(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Message Input Box */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          style={{
            padding: '0.85rem 1.25rem',
            background: 'var(--bg-card)',
            borderTop: '1px solid var(--border-subtle)',
            display: 'flex',
            gap: '0.65rem',
          }}
        >
          <input
            type="text"
            className="form-input"
            placeholder="Type customer message or spoken inquiry..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={loading}
            style={{ flex: 1, padding: '0.6rem 0.85rem' }}
          />
          <button
            type="submit"
            className="btn-primary"
            disabled={loading || !inputText.trim()}
            style={{ padding: '0.6rem 1.25rem' }}
          >
            <Send size={14} />
            <span>Send</span>
          </button>
        </form>
      </div>
    </section>
  );
}
