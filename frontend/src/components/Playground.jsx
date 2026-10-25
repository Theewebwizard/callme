import React, { useState, useEffect, useRef } from 'react';
import {
  Send,
  RotateCcw,
  Bot,
  User,
  Sparkles,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ArrowRight,
} from 'lucide-react';
import { api } from '../api';

const QUICK_PROMPTS = [
  'What are your operating hours?',
  'What services or consultations do you provide?',
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
          content: `⚠️ Error processing response: ${err.message}`,
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
          content: `✅ Action confirmed successfully: ${res.message || 'Operation executed.'}`,
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
          content: '❌ Action cancelled as requested. How else may I assist you?',
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
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <h3>No Business Selected</h3>
          <p style={{ color: 'var(--slate-500)', marginTop: '0.5rem' }}>
            Please register or select a business in Business Setup to test the AI receptionist.
          </p>
        </div>
      </div>
    );
  }

  return (
    <section className="main-content">
      <div className="section-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 className="section-title">💬 AI Playground</h1>
            <p className="section-subtitle">
              Simulate customer conversations with <strong>{business.name}</strong>'s LangGraph virtual receptionist.
            </p>
          </div>
          <button
            className="btn-secondary"
            onClick={() => {
              setMessages([
                {
                  role: 'assistant',
                  content: business.greeting_message || 'Hello! How can I assist you today?',
                  time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                },
              ]);
              setPendingAction(null);
              setActionFeedback(null);
            }}
          >
            <RotateCcw size={15} /> Reset Chat
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', height: '620px' }}>
        {/* Chat Messages Log */}
        <div style={{ flex: 1, padding: '1.5rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem', background: 'var(--bg-app)' }}>
          {messages.map((m, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                gap: '0.75rem',
                alignItems: 'flex-start',
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '80%',
              }}
            >
              {m.role === 'assistant' && (
                <div
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, var(--sky-500) 0%, var(--sky-600) 100%)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'white',
                    flexShrink: 0,
                    boxShadow: 'var(--shadow-sm)',
                  }}
                >
                  <Bot size={17} />
                </div>
              )}

              <div>
                <div
                  style={{
                    padding: '0.85rem 1.15rem',
                    borderRadius: '16px',
                    fontSize: '0.92rem',
                    lineHeight: 1.5,
                    background: m.role === 'user' ? 'var(--sky-500)' : 'white',
                    color: m.role === 'user' ? 'white' : 'var(--slate-800)',
                    border: m.role === 'user' ? 'none' : '1px solid var(--slate-200)',
                    boxShadow: 'var(--shadow-sm)',
                  }}
                >
                  {m.content}
                </div>
                <div
                  style={{
                    fontSize: '0.72rem',
                    color: 'var(--slate-400)',
                    marginTop: '0.25rem',
                    textAlign: m.role === 'user' ? 'right' : 'left',
                  }}
                >
                  {m.time}
                </div>
              </div>

              {m.role === 'user' && (
                <div
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '50%',
                    background: 'var(--slate-200)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--slate-700)',
                    flexShrink: 0,
                  }}
                >
                  <User size={17} />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: 'var(--sky-500)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'white',
                }}
              >
                <Bot size={17} />
              </div>
              <div
                style={{
                  background: 'white',
                  border: '1px solid var(--slate-200)',
                  borderRadius: '16px',
                  padding: '0.65rem 1rem',
                  fontSize: '0.85rem',
                  color: 'var(--slate-500)',
                  fontStyle: 'italic',
                }}
              >
                {business.name} Receptionist is typing...
              </div>
            </div>
          )}

          {/* Phase B: Human Action Confirmation Card */}
          {pendingAction && (
            <div
              style={{
                background: 'var(--sky-50)',
                border: '2px solid var(--sky-400)',
                borderRadius: 'var(--radius-md)',
                padding: '1.25rem',
                margin: '1rem 0',
                boxShadow: 'var(--shadow-sky)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--sky-800)', fontWeight: 800, fontSize: '0.95rem' }}>
                <Sparkles size={18} /> Human Operator Approval Required
              </div>
              <div style={{ fontSize: '0.85rem', color: 'var(--slate-700)', marginTop: '0.35rem' }}>
                The receptionist proposed executing action: <strong>{pendingAction.action_type}</strong>
              </div>

              <div
                style={{
                  background: 'white',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--sky-200)',
                  padding: '0.75rem',
                  margin: '0.75rem 0',
                  fontSize: '0.82rem',
                }}
              >
                <pre style={{ margin: 0, fontFamily: 'var(--font-mono)' }}>
                  {JSON.stringify(pendingAction.parameters || {}, null, 2)}
                </pre>
              </div>

              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <button
                  className="btn-primary"
                  style={{ background: 'var(--emerald-500)', padding: '0.45rem 1rem', fontSize: '0.85rem' }}
                  onClick={handleConfirmAction}
                >
                  <CheckCircle size={15} /> Confirm & Execute
                </button>
                <button
                  className="btn-secondary"
                  style={{ borderColor: 'var(--rose-300)', color: 'var(--rose-600)', padding: '0.45rem 1rem', fontSize: '0.85rem' }}
                  onClick={handleCancelAction}
                >
                  <XCircle size={15} /> Cancel Action
                </button>
              </div>
            </div>
          )}

          <div ref={chatBottomRef} />
        </div>

        {/* Quick Suggestion Chips */}
        <div style={{ padding: '0.5rem 1rem', background: 'white', borderTop: '1px solid var(--slate-100)', display: 'flex', gap: '0.5rem', overflowX: 'auto' }}>
          {QUICK_PROMPTS.map((prompt, i) => (
            <button
              key={i}
              type="button"
              style={{
                background: 'var(--slate-50)',
                border: '1px solid var(--slate-200)',
                borderRadius: 'var(--radius-full)',
                padding: '0.35rem 0.75rem',
                fontSize: '0.78rem',
                color: 'var(--slate-700)',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'var(--transition)',
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
          style={{ padding: '1rem', background: 'white', borderTop: '1px solid var(--slate-200)', display: 'flex', gap: '0.75rem' }}
        >
          <input
            type="text"
            className="form-input"
            placeholder="Type customer message or inquiry..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={loading}
            style={{ flex: 1, padding: '0.75rem 1rem' }}
          />
          <button type="submit" className="btn-primary" disabled={loading || !inputText.trim()} style={{ padding: '0.75rem 1.25rem' }}>
            <Send size={16} /> Send
          </button>
        </form>
      </div>
    </section>
  );
}
