import React, { useState, useEffect } from 'react';
import {
  Wrench,
  BookOpen,
  Calendar,
  MessageSquare,
  PhoneForwarded,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  PlusCircle,
  Clock,
  Layers,
  Send,
  Save,
  RotateCcw,
} from 'lucide-react';
import { api } from '../api';

const TOOL_ICONS = {
  lookup_faq: BookOpen,
  book_appointment: Calendar,
  take_message: MessageSquare,
  transfer_call: PhoneForwarded,
};

const DEMAND_CATEGORIES = [
  'Reservation & Booking',
  'CRM & Lead Management',
  'E-commerce & Order Tracking',
  'Payments & Billing',
  'WhatsApp & SMS Notifications',
  'Custom Database / Webhook',
  'Other',
];

const PRIORITIES = ['Nice to Have', 'Important', 'Business Critical'];

export default function ToolLibrary({ business }) {
  const [activeTab, setActiveTab] = useState('existing'); // 'existing' or 'demands'
  const [tools, setTools] = useState([]);
  const [savedEnabledMap, setSavedEnabledMap] = useState({});
  const [enabledMap, setEnabledMap] = useState({});
  const [savingTools, setSavingTools] = useState(false);
  const [demands, setDemands] = useState([]);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState(null);

  // Demand form state
  const [toolName, setToolName] = useState('');
  const [category, setCategory] = useState('Reservation & Booking');
  const [integrationTarget, setIntegrationTarget] = useState('');
  const [priority, setPriority] = useState('Important');
  const [description, setDescription] = useState('');
  const [demandSubmitting, setDemandSubmitting] = useState(false);

  useEffect(() => {
    if (business) {
      loadData();
    }
  }, [business?.id]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [toolsData, demandsData] = await Promise.all([
        api.getTools(business.id),
        api.getToolDemands(business.id).catch(() => []),
      ]);
      const initialMap = toolsData.enabled_tools || {};
      setTools(toolsData.tools || []);
      setSavedEnabledMap(initialMap);
      setEnabledMap(initialMap);
      setDemands(demandsData || []);
    } catch (err) {
      console.error('Failed to load tools:', err);
    } finally {
      setLoading(false);
    }
  };

  // Check if any tool toggle has changed compared to saved map
  const hasChanges = Object.keys({ ...savedEnabledMap, ...enabledMap }).some(
    (key) => Boolean(savedEnabledMap[key]) !== Boolean(enabledMap[key])
  );

  const handleToggle = (toolId) => {
    setEnabledMap((prev) => ({
      ...prev,
      [toolId]: !prev[toolId],
    }));
  };

  const handleResetChanges = () => {
    setEnabledMap(savedEnabledMap);
    setFeedback(null);
  };

  const handleSaveTools = async () => {
    setSavingTools(true);
    setFeedback(null);
    try {
      await api.updateTools(business.id, enabledMap);
      setSavedEnabledMap(enabledMap);
      setFeedback({ type: 'success', text: 'Tool settings updated and published successfully!' });
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to update tools: ${err.message}` });
    } finally {
      setSavingTools(false);
    }
  };

  const handleDemandSubmit = async (e) => {
    e.preventDefault();
    if (!toolName.trim() || !description.trim()) {
      setFeedback({ type: 'error', text: 'Please fill in both Tool Name and Description.' });
      return;
    }
    setDemandSubmitting(true);
    setFeedback(null);

    const payload = {
      tool_name: toolName.trim(),
      description: description.trim(),
      category,
      integration_target: integrationTarget.trim() || 'Custom API',
      priority,
    };

    try {
      const res = await api.createToolDemand(business.id, payload);
      setDemands((prev) => [res, ...prev]);
      setToolName('');
      setIntegrationTarget('');
      setDescription('');
      setFeedback({ type: 'success', text: `Tool demand "${res.tool_name}" submitted to engineering team!` });
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to submit demand: ${err.message}` });
    } finally {
      setDemandSubmitting(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'Under Review':
        return <span style={{ background: 'var(--amber-100)', color: 'var(--amber-800)', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 700 }}>🟡 Under Review</span>;
      case 'In Development':
        return <span style={{ background: 'var(--sky-100)', color: 'var(--sky-700)', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 700 }}>🔵 In Development</span>;
      case 'Ready':
      case 'Active':
        return <span style={{ background: 'var(--emerald-100)', color: 'var(--emerald-700)', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 700 }}>🟢 Ready & Active</span>;
      default:
        return <span style={{ background: 'var(--slate-100)', color: 'var(--slate-700)', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 700 }}>{status}</span>;
    }
  };

  if (!business) return null;

  return (
    <section className="main-content">
      <div className="section-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 className="section-title">🧰 Tools & Feature Demands</h1>
            <p className="section-subtitle">
              Manage operational tools for <strong>{business.name}</strong> or demand custom integrations built for your business.
            </p>
          </div>
        </div>
      </div>

      {feedback && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-md)',
            marginBottom: '1.25rem',
            background: feedback.type === 'success' ? 'var(--emerald-100)' : 'var(--rose-100)',
            color: feedback.type === 'success' ? 'var(--emerald-700)' : 'var(--rose-700)',
            fontSize: '0.85rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          {feedback.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          {feedback.text}
        </div>
      )}

      {/* Sub-Tabs: Pre-existing Tools vs Demand Features */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <button
          className={`btn-secondary ${activeTab === 'existing' ? 'active' : ''}`}
          style={{
            background: activeTab === 'existing' ? 'var(--sky-50)' : 'white',
            borderColor: activeTab === 'existing' ? 'var(--sky-400)' : 'var(--slate-300)',
            color: activeTab === 'existing' ? 'var(--sky-700)' : 'var(--slate-700)',
          }}
          onClick={() => setActiveTab('existing')}
        >
          <Wrench size={16} /> Pre-Existing Tools ({tools.length})
        </button>

        <button
          className={`btn-secondary ${activeTab === 'demands' ? 'active' : ''}`}
          style={{
            background: activeTab === 'demands' ? 'var(--sky-50)' : 'white',
            borderColor: activeTab === 'demands' ? 'var(--sky-400)' : 'var(--slate-300)',
            color: activeTab === 'demands' ? 'var(--sky-700)' : 'var(--slate-700)',
          }}
          onClick={() => setActiveTab('demands')}
        >
          <Sparkles size={16} /> 💡 Demand Custom Features ({demands.length})
        </button>
      </div>

      {/* =========================================================================
         TAB 1: PRE-EXISTING RECEPTIONIST TOOLS
         ========================================================================= */}
      {activeTab === 'existing' && (
        <div>
          {/* Industry Scoping Context Banner */}
          <div
            style={{
              background: 'var(--sky-50)',
              border: '1px solid var(--sky-200)',
              borderRadius: 'var(--radius-md)',
              padding: '0.85rem 1.15rem',
              marginBottom: '1.25rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '1rem',
              flexWrap: 'wrap',
            }}
          >
            <div>
              <div style={{ fontWeight: 800, color: 'var(--sky-900)', fontSize: '0.92rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Layers size={16} /> Industry-Tailored Tools: <strong>{business.industry || 'General'}</strong>
              </div>
              <div style={{ color: 'var(--sky-700)', fontSize: '0.8rem', marginTop: '2px' }}>
                Only tools authorized for <strong>{business.industry}</strong> businesses are displayed here. Other industry tools are filtered out.
              </div>
            </div>

            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 700,
                background: 'white',
                color: 'var(--sky-800)',
                border: '1px solid var(--sky-300)',
                padding: '4px 12px',
                borderRadius: '12px',
              }}
            >
              {tools.length} Available Tools
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div className="card-desc" style={{ margin: 0 }}>
              Turn pre-built conversational capabilities on or off for <strong>{business.name}</strong>. Toggle multiple tools and apply your changes when ready.
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {hasChanges && (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleResetChanges}
                  disabled={savingTools}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.82rem', padding: '0.45rem 0.85rem' }}
                >
                  <RotateCcw size={14} /> Discard
                </button>
              )}
              <button
                type="button"
                className="btn-primary"
                onClick={handleSaveTools}
                disabled={!hasChanges || savingTools}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  fontSize: '0.85rem',
                  padding: '0.45rem 1.15rem',
                  opacity: hasChanges ? 1 : 0.5,
                  cursor: hasChanges && !savingTools ? 'pointer' : 'not-allowed',
                  boxShadow: hasChanges ? '0 2px 8px rgba(14, 165, 233, 0.35)' : 'none',
                }}
              >
                <Save size={15} />
                {savingTools ? 'Saving Changes...' : hasChanges ? 'Update Tools (Unsaved Changes)' : 'Tool Status Updated'}
              </button>
            </div>
          </div>

          <div className="tool-grid">
            {tools.map((t) => {
              const IconComponent = TOOL_ICONS[t.id] || Wrench;
              const isEnabled = !!enabledMap[t.id];
              const isUniversal = !t.allowed_industries || t.allowed_industries.includes('*');

              return (
                <div key={t.id} className={`tool-card ${isEnabled ? 'enabled' : ''}`}>
                  <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start', flex: 1, paddingRight: '1rem' }}>
                    <div
                      style={{
                        width: '42px',
                        height: '42px',
                        borderRadius: 'var(--radius-md)',
                        background: isEnabled ? 'var(--sky-500)' : 'var(--slate-100)',
                        color: isEnabled ? 'white' : 'var(--slate-500)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                        boxShadow: isEnabled ? '0 4px 12px rgba(14, 165, 233, 0.3)' : 'none',
                        transition: 'var(--transition)',
                      }}
                    >
                      <IconComponent size={20} />
                    </div>

                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                        <span style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--slate-900)' }}>
                          {t.name}
                        </span>
                        {isUniversal ? (
                          <span style={{ background: 'var(--emerald-50)', color: 'var(--emerald-700)', border: '1px solid var(--emerald-200)', padding: '1px 7px', borderRadius: '10px', fontSize: '0.68rem', fontWeight: 700 }}>
                            🌐 Universal
                          </span>
                        ) : (
                          <span style={{ background: 'var(--sky-50)', color: 'var(--sky-700)', border: '1px solid var(--sky-200)', padding: '1px 7px', borderRadius: '10px', fontSize: '0.68rem', fontWeight: 700 }}>
                            🎯 {business.industry} Specific
                          </span>
                        )}
                      </div>

                      <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--sky-600)', margin: '2px 0 4px' }}>
                        Category: {t.category}
                      </div>
                      <div style={{ fontSize: '0.82rem', color: 'var(--slate-600)', lineHeight: 1.4 }}>
                        {t.description}
                      </div>
                    </div>
                  </div>

                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={isEnabled}
                      onChange={() => handleToggle(t.id)}
                    />
                    <span className="slider" />
                  </label>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* =========================================================================
         TAB 2: DEMAND OTHER TOOL FEATURES (CUSTOM CAPABILITIES)
         ========================================================================= */}
      {activeTab === 'demands' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: '1.5rem', alignItems: 'flex-start' }}>
          {/* Demand Submission Form */}
          <form onSubmit={handleDemandSubmit} className="card">
            <div className="card-title">
              <Sparkles size={18} color="var(--sky-600)" /> Demand a Custom Tool Feature
            </div>
            <div className="card-desc">
              Tell us what custom software, API, or action you want your receptionist to handle during calls.
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">Tool / Feature Name *</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Zomato Table Reservation Sync"
                value={toolName}
                onChange={(e) => setToolName(e.target.value)}
                required
              />
            </div>

            <div className="form-grid" style={{ marginBottom: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Category</label>
                <select
                  className="form-select"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  {DEMAND_CATEGORIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Target Software / API</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Google Calendar, Shopify, Zomato"
                  value={integrationTarget}
                  onChange={(e) => setIntegrationTarget(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">Priority</label>
              <select
                className="form-select"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>

            <div className="form-group" style={{ marginBottom: '1.25rem' }}>
              <label className="form-label">What should the AI receptionist do with this tool? *</label>
              <textarea
                className="form-textarea"
                placeholder="Explain the caller conversation flow: e.g. 'When a caller requests a table, check available seats in Zomato Bookings API and reserve with their name and phone number.'"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
                style={{ minHeight: '110px' }}
              />
            </div>

            <button type="submit" className="btn-primary" disabled={demandSubmitting} style={{ width: '100%' }}>
              <Send size={16} /> {demandSubmitting ? 'Submitting Demand...' : 'Submit Feature Demand'}
            </button>
          </form>

          {/* Demanded Features List */}
          <div className="card">
            <div className="card-title">
              <Layers size={18} color="var(--sky-600)" /> Your Demanded Features ({demands.length})
            </div>
            <div className="card-desc">
              Custom tool requests registered for <strong>{business.name}</strong>.
            </div>

            {demands.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--slate-400)', fontSize: '0.9rem' }}>
                No custom features demanded yet. Use the form on the left to request any custom tool or API integration!
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                {demands.map((d) => (
                  <div
                    key={d.id}
                    style={{
                      background: 'var(--slate-50)',
                      border: '1px solid var(--slate-200)',
                      borderRadius: 'var(--radius-md)',
                      padding: '1rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '0.35rem' }}>
                      <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--slate-900)' }}>
                        {d.tool_name}
                      </div>
                      {getStatusBadge(d.status)}
                    </div>

                    <div style={{ fontSize: '0.78rem', color: 'var(--sky-700)', fontWeight: 600, marginBottom: '0.35rem' }}>
                      {d.category} • Target: <code>{d.integration_target}</code> • Priority: <em>{d.priority}</em>
                    </div>

                    <div style={{ fontSize: '0.83rem', color: 'var(--slate-600)', lineHeight: 1.4 }}>
                      {d.description}
                    </div>

                    {d.created_at && (
                      <div style={{ fontSize: '0.72rem', color: 'var(--slate-400)', marginTop: '0.4rem' }}>
                        Requested: {new Date(d.created_at).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
