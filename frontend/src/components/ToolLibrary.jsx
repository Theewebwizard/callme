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
  Layers,
  Save,
  RotateCcw,
  Sliders,
  Check,
  X,
  Server,
  ShieldCheck,
  RefreshCw,
  Plus,
  Trash2,
  Database,
  Lock,
  ExternalLink,
} from 'lucide-react';
import { api } from '../api';

const TOOL_ICONS = {
  answer_faq: BookOpen,
  check_table_availability: Calendar,
  create_table_booking: Calendar,
  check_appointment_availability: Calendar,
  create_appointment: Calendar,
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
  const [activeTab, setActiveTab] = useState('capabilities'); // 'capabilities', 'resources', 'demands'
  const [tools, setTools] = useState([]);
  const [capabilities, setCapabilities] = useState({});
  const [savedEnabledMap, setSavedEnabledMap] = useState({});
  const [enabledMap, setEnabledMap] = useState({});
  const [savingTools, setSavingTools] = useState(false);
  const [demands, setDemands] = useState([]);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState(null);

  // Resource Management State
  const [resources, setResources] = useState([]);
  const [reservations, setReservations] = useState([]);
  const [loadingResources, setLoadingResources] = useState(false);
  const [newResourceName, setNewResourceName] = useState('');
  const [newResourceCapacity, setNewResourceCapacity] = useState(2);
  const [newResourceMinParty, setNewResourceMinParty] = useState(1);
  const [newResourceMaxParty, setNewResourceMaxParty] = useState(4);
  const [newResourceType, setNewResourceType] = useState('table');
  const [newResourceSection, setNewResourceSection] = useState('Main Dining');

  // Wizard Modal State
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardTool, setWizardTool] = useState(null);
  const [wizardSchema, setWizardSchema] = useState(null);
  const [wizardStep, setWizardStep] = useState(1); // 1: Option, 2: Fields, 3: Validate, 4: Ready
  const [selectedOptionId, setSelectedOptionId] = useState('');
  const [wizardFormData, setWizardFormData] = useState({});
  const [validationReport, setValidationReport] = useState(null);
  const [wizardLoading, setWizardLoading] = useState(false);
  const [testResult, setTestResult] = useState(null);

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
      const [toolsData, capsData, demandsData] = await Promise.all([
        api.getTools(business.id),
        api.getCapabilities(business.id).catch(() => []),
        api.getToolDemands(business.id).catch(() => []),
      ]);
      const initialMap = toolsData.enabled_tools || {};
      setTools(toolsData.tools || []);
      setSavedEnabledMap(initialMap);
      setEnabledMap(initialMap);

      const capMap = {};
      (capsData || []).forEach((c) => {
        capMap[c.tool_id] = c;
      });
      setCapabilities(capMap);
      setDemands(demandsData || []);

      if (activeTab === 'resources') {
        loadResources();
      }
    } catch (err) {
      console.error('Failed to load capability data:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadResources = async () => {
    setLoadingResources(true);
    try {
      const [resList, bookingList] = await Promise.all([
        api.listResources(business.id),
        api.listReservations(business.id).catch(() => []),
      ]);
      setResources(resList || []);
      setReservations(bookingList || []);
    } catch (err) {
      console.error('Failed to load resources:', err);
    } finally {
      setLoadingResources(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'resources') {
      loadResources();
    }
  }, [activeTab]);

  // Check if any tool toggle has changed compared to saved map
  const hasChanges = Object.keys({ ...savedEnabledMap, ...enabledMap }).some(
    (key) => Boolean(savedEnabledMap[key]) !== Boolean(enabledMap[key])
  );

  const handleToggle = (toolId) => {
    const cap = capabilities[toolId];
    const isCurrentlyEnabled = !!enabledMap[toolId];

    // If enabling, verify that the capability is ready or configured
    if (!isCurrentlyEnabled && cap && cap.status !== 'ready') {
      setFeedback({
        type: 'error',
        text: `Cannot enable "${cap.name || toolId}": It requires configuration. Click "Configure" to complete the guided setup.`,
      });
      openWizard(tools.find((t) => t.id === toolId));
      return;
    }

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
      setFeedback({ type: 'success', text: 'Tool enablement preferences updated successfully!' });
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to update tools: ${err.message}` });
    } finally {
      setSavingTools(false);
    }
  };

  // --- Setup Wizard Handlers ---

  const openWizard = async (tool) => {
    if (!tool) return;
    setWizardTool(tool);
    setWizardStep(1);
    setValidationReport(null);
    setTestResult(null);
    setWizardLoading(true);
    setWizardOpen(true);

    try {
      const schema = await api.getCapabilitySchema(business.id, tool.id);
      setWizardSchema(schema);

      const existingCap = capabilities[tool.id];
      const defaultOpt = existingCap?.selected_option_id || schema.supported_options?.[0]?.option_id || '';
      setSelectedOptionId(defaultOpt);

      // Prepopulate form data if existing config present
      setWizardFormData(existingCap?.configuration || {});
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to load setup schema: ${err.message}` });
      setWizardOpen(false);
    } finally {
      setWizardLoading(false);
    }
  };

  const closeWizard = () => {
    setWizardOpen(false);
    setWizardTool(null);
    setWizardSchema(null);
    setValidationReport(null);
    loadData();
  };

  const handleStartOption = async () => {
    if (!selectedOptionId) return;
    setWizardLoading(true);
    try {
      await api.startCapabilitySetup(business.id, wizardTool.id, selectedOptionId);
      setWizardStep(2);
    } catch (err) {
      setFeedback({ type: 'error', text: `Error starting setup: ${err.message}` });
    } finally {
      setWizardLoading(false);
    }
  };

  const handleSaveConfiguration = async () => {
    setWizardLoading(true);
    try {
      await api.saveCapabilityStep(business.id, wizardTool.id, 'configuration', wizardFormData, true);
      // Run validation automatically
      const report = await api.validateCapabilitySetup(business.id, wizardTool.id);
      setValidationReport(report);
      setWizardStep(3);
    } catch (err) {
      setFeedback({ type: 'error', text: `Error saving configuration: ${err.message}` });
    } finally {
      setWizardLoading(false);
    }
  };

  const handleRunValidation = async () => {
    setWizardLoading(true);
    try {
      const report = await api.validateCapabilitySetup(business.id, wizardTool.id);
      setValidationReport(report);
    } catch (err) {
      setFeedback({ type: 'error', text: `Validation check failed: ${err.message}` });
    } finally {
      setWizardLoading(false);
    }
  };

  const handleActivateCapability = async () => {
    setWizardLoading(true);
    try {
      await api.activateCapability(business.id, wizardTool.id);
      setWizardStep(4);
      setEnabledMap((prev) => ({ ...prev, [wizardTool.id]: true }));
      setSavedEnabledMap((prev) => ({ ...prev, [wizardTool.id]: true }));
      setFeedback({ type: 'success', text: `Capability "${wizardTool.name}" is now fully activated and operational!` });
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to activate: ${err.message}` });
    } finally {
      setWizardLoading(false);
    }
  };

  const handleDisconnectCapability = async () => {
    if (!window.confirm(`Are you sure you want to disconnect ${wizardTool.name}? This will purge stored credentials and disable the capability.`)) {
      return;
    }
    setWizardLoading(true);
    try {
      await api.disconnectCapability(business.id, wizardTool.id);
      setEnabledMap((prev) => ({ ...prev, [wizardTool.id]: false }));
      setSavedEnabledMap((prev) => ({ ...prev, [wizardTool.id]: false }));
      setFeedback({ type: 'success', text: `Integration for "${wizardTool.name}" disconnected and credentials purged.` });
      closeWizard();
    } catch (err) {
      setFeedback({ type: 'error', text: `Disconnection failed: ${err.message}` });
    } finally {
      setWizardLoading(false);
    }
  };

  const handleTestConnection = async (toolId) => {
    try {
      const res = await api.testCapabilityConnection(business.id, toolId);
      const isOk = res.connection?.connected;
      alert(`Integration Test for ${toolId}:\n` +
        `• Authoritative Source: ${res.authoritative_source}\n` +
        `• Connection: ${isOk ? 'ONLINE' : 'OFFLINE'} (${res.connection?.engine || 'Provider'})\n` +
        `• Permissions: ${res.permissions?.valid ? 'VALID' : 'INVALID'}`);
    } catch (err) {
      alert(`Connection test failed: ${err.message}`);
    }
  };

  // --- Resource Management Handlers ---

  const handleAddResource = async (e) => {
    e.preventDefault();
    if (!newResourceName.trim()) return;

    try {
      const created = await api.createResource(business.id, {
        name: newResourceName.trim(),
        capacity: Number(newResourceCapacity),
        min_party_size: Number(newResourceMinParty),
        max_party_size: Number(newResourceMaxParty),
        resource_type: newResourceType,
        section: newResourceSection.trim(),
      });
      setResources((prev) => [...prev, created]);
      setNewResourceName('');
      setFeedback({ type: 'success', text: `Resource "${created.name}" registered successfully!` });
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to add resource: ${err.message}` });
    }
  };

  const handleDeleteResource = async (resourceId) => {
    if (!window.confirm('Delete this resource from inventory? Existing reservations will be preserved.')) return;
    try {
      await api.deleteResource(business.id, resourceId);
      setResources((prev) => prev.filter((r) => r.id !== resourceId));
      setFeedback({ type: 'success', text: 'Resource deleted from inventory.' });
    } catch (err) {
      setFeedback({ type: 'error', text: `Delete failed: ${err.message}` });
    }
  };

  // --- Demand Submission ---

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

  const getCapabilityBadge = (status) => {
    switch (status) {
      case 'ready':
        return (
          <span style={{ background: 'var(--emerald-100)', color: 'var(--emerald-700)', padding: '3px 9px', borderRadius: '12px', fontSize: '0.72rem', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <CheckCircle2 size={13} /> Ready & Verified
          </span>
        );
      case 'pending_provider_approval':
        return (
          <span style={{ background: '#fef3c7', color: '#b45309', border: '1px solid #fde68a', padding: '3px 9px', borderRadius: '12px', fontSize: '0.72rem', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <AlertCircle size={13} /> Pending Partner Approval
          </span>
        );
      case 'awaiting_authorization':
        return (
          <span style={{ background: '#ede9fe', color: '#6d28d9', padding: '3px 9px', borderRadius: '12px', fontSize: '0.72rem', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <AlertCircle size={13} /> Awaiting Auth
          </span>
        );
      case 'needs_input':
        return (
          <span style={{ background: 'var(--amber-100)', color: 'var(--amber-800)', padding: '3px 9px', borderRadius: '12px', fontSize: '0.72rem', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <AlertCircle size={13} /> Needs Configuration
          </span>
        );
      case 'validating':
        return (
          <span style={{ background: 'var(--sky-100)', color: 'var(--sky-700)', padding: '3px 9px', borderRadius: '12px', fontSize: '0.72rem', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <RefreshCw size={13} /> Validating
          </span>
        );
      case 'degraded':
        return (
          <span style={{ background: '#ffedd5', color: '#c2410c', padding: '3px 9px', borderRadius: '12px', fontSize: '0.72rem', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <AlertCircle size={13} /> Degraded
          </span>
        );
      case 'disconnected':
        return (
          <span style={{ background: 'var(--rose-100)', color: 'var(--rose-700)', padding: '3px 9px', borderRadius: '12px', fontSize: '0.72rem', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <X size={13} /> Disconnected
          </span>
        );
      default:
        return (
          <span style={{ background: 'var(--slate-100)', color: 'var(--slate-600)', padding: '3px 9px', borderRadius: '12px', fontSize: '0.72rem', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            ⚙️ Not Configured
          </span>
        );
    }
  };

  const currentOption = wizardSchema?.supported_options?.find((o) => o.option_id === selectedOptionId);

  if (!business) return null;

  return (
    <section className="main-content">
      <div className="section-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <div>
            <h1 className="section-title">🧰 Capability Setup Wizard & Integrations</h1>
            <p className="section-subtitle">
              Configure verified capabilities, manage built-in table and room inventory, or connect external providers for <strong>{business.name}</strong>.
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

      {/* Primary Navigation Tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <button
          className={`btn-secondary ${activeTab === 'capabilities' ? 'active' : ''}`}
          style={{
            background: activeTab === 'capabilities' ? 'var(--sky-50)' : 'white',
            borderColor: activeTab === 'capabilities' ? 'var(--sky-400)' : 'var(--slate-300)',
            color: activeTab === 'capabilities' ? 'var(--sky-700)' : 'var(--slate-700)',
          }}
          onClick={() => setActiveTab('capabilities')}
        >
          <Wrench size={16} /> Capabilities & Tools ({tools.length})
        </button>

        <button
          className={`btn-secondary ${activeTab === 'resources' ? 'active' : ''}`}
          style={{
            background: activeTab === 'resources' ? 'var(--sky-50)' : 'white',
            borderColor: activeTab === 'resources' ? 'var(--sky-400)' : 'var(--slate-300)',
            color: activeTab === 'resources' ? 'var(--sky-700)' : 'var(--slate-700)',
          }}
          onClick={() => setActiveTab('resources')}
        >
          <Database size={16} /> 🪑 Resource Inventory ({resources.length})
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
          <Sparkles size={16} /> 💡 Custom Feature Demands ({demands.length})
        </button>
      </div>

      {/* =========================================================================
         TAB 1: CAPABILITIES & SETUP WIZARD
         ========================================================================= */}
      {activeTab === 'capabilities' && (
        <div>
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
                <Layers size={16} /> Industry Policy: <strong>{business.industry || 'General'}</strong>
              </div>
              <div style={{ color: 'var(--sky-700)', fontSize: '0.8rem', marginTop: '2px' }}>
                Live capability execution requires verified readiness. Tools must pass setup validation before they can handle caller requests.
              </div>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem' }}>
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
                }}
              >
                <Save size={15} />
                {savingTools ? 'Saving Changes...' : hasChanges ? 'Apply Tool Status Changes' : 'All Changes Saved'}
              </button>
            </div>
          </div>

          <div className="tool-grid">
            {tools.map((t) => {
              const IconComponent = TOOL_ICONS[t.id] || Wrench;
              const isEnabled = !!enabledMap[t.id];
              const cap = capabilities[t.id];
              const capStatus = cap?.status || (isEnabled ? 'ready' : 'not_configured');
              const authSource = cap?.authoritative_source || 'Platform Default';
              const selectedOptionName = cap?.selected_option_name || 'Built-in Architecture';

              return (
                <div key={t.id} className={`tool-card ${isEnabled ? 'enabled' : ''}`} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start', width: '100%' }}>
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
                      }}
                    >
                      <IconComponent size={20} />
                    </div>

                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px', flexWrap: 'wrap' }}>
                        <span style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--slate-900)' }}>
                          {t.name}
                        </span>
                        <label className="switch">
                          <input
                            type="checkbox"
                            checked={isEnabled}
                            onChange={() => handleToggle(t.id)}
                          />
                          <span className="slider" />
                        </label>
                      </div>

                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginTop: '4px', flexWrap: 'wrap' }}>
                        {getCapabilityBadge(capStatus)}
                        <span style={{ fontSize: '0.72rem', background: 'var(--slate-100)', color: 'var(--slate-600)', padding: '2px 8px', borderRadius: '10px', fontWeight: 600 }}>
                          {selectedOptionName}
                        </span>
                      </div>

                      <div style={{ fontSize: '0.82rem', color: 'var(--slate-600)', marginTop: '8px', lineHeight: 1.4 }}>
                        {t.description}
                      </div>

                      <div style={{ marginTop: '10px', fontSize: '0.75rem', color: 'var(--slate-500)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Server size={12} /> Source of Truth: <strong>{authSource}</strong>
                      </div>

                      {cap?.missing_requirements && cap.missing_requirements.length > 0 && (
                        <div style={{ marginTop: '8px', padding: '6px 10px', background: 'var(--amber-50)', border: '1px solid var(--amber-200)', borderRadius: '6px', fontSize: '0.75rem', color: 'var(--amber-800)' }}>
                          ⚠️ {cap.missing_requirements[0]}
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '0.5rem', borderTop: '1px solid var(--slate-100)', paddingTop: '0.75rem', marginTop: 'auto' }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => openWizard(t)}
                      style={{ flex: 1, padding: '0.4rem', fontSize: '0.8rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px' }}
                    >
                      <Sliders size={14} /> Configure Setup
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => handleTestConnection(t.id)}
                      title="Test live connectivity and verify permissions"
                      style={{ padding: '0.4rem 0.6rem', fontSize: '0.8rem' }}
                    >
                      <ShieldCheck size={14} /> Test
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* =========================================================================
         TAB 2: RESOURCE INVENTORY & BOOKINGS (FIRST-PARTY ENGINE)
         ========================================================================= */}
      {activeTab === 'resources' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', alignItems: 'flex-start' }}>
          {/* Add Resource Form */}
          <form onSubmit={handleAddResource} className="card">
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Plus size={18} color="var(--sky-600)" /> Add Reservable Resource
            </div>
            <div className="card-desc">
              Register dining tables or consultation suites for first-party booking conflict prevention.
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">Resource Label / Name *</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Table 5 (Terrace) or Dental Suite 3"
                value={newResourceName}
                onChange={(e) => setNewResourceName(e.target.value)}
                required
              />
            </div>

            <div className="form-grid" style={{ marginBottom: '1rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Resource Type</label>
                <select
                  className="form-input"
                  value={newResourceType}
                  onChange={(e) => setNewResourceType(e.target.value)}
                >
                  <option value="table">Dining Table (Restaurant)</option>
                  <option value="room">Hotel Room / Suite</option>
                  <option value="clinic_room">Clinical Suite / Consultation Room</option>
                  <option value="practitioner">Practitioner / Doctor</option>
                  <option value="service_staff">Service Staff / Stylist</option>
                  <option value="desk">Service Desk</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Section / Area</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Patio, 1st Floor"
                  value={newResourceSection}
                  onChange={(e) => setNewResourceSection(e.target.value)}
                />
              </div>
            </div>

            <div className="form-grid" style={{ marginBottom: '1.25rem', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
              <div className="form-group">
                <label className="form-label">Capacity</label>
                <input
                  type="number"
                  className="form-input"
                  min="1"
                  max="50"
                  value={newResourceCapacity}
                  onChange={(e) => setNewResourceCapacity(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Min Party</label>
                <input
                  type="number"
                  className="form-input"
                  min="1"
                  max="50"
                  value={newResourceMinParty}
                  onChange={(e) => setNewResourceMinParty(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Max Party</label>
                <input
                  type="number"
                  className="form-input"
                  min="1"
                  max="50"
                  value={newResourceMaxParty}
                  onChange={(e) => setNewResourceMaxParty(e.target.value)}
                  required
                />
              </div>
            </div>

            <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center' }}>
              <Plus size={16} /> Register Reservable Resource
            </button>
          </form>

          {/* Active Inventory List */}
          <div className="card">
            <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Database size={18} color="var(--sky-600)" /> Active Inventory ({resources.length})
              </span>
              <button
                type="button"
                className="btn-secondary"
                onClick={loadResources}
                disabled={loadingResources}
                style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }}
              >
                <RefreshCw size={12} /> Refresh
              </button>
            </div>
            <div className="card-desc">
              Resources authoritative in database. AI checks availability against this inventory.
            </div>

            {loadingResources ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--slate-500)' }}>Loading inventory...</div>
            ) : resources.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--slate-500)', background: 'var(--slate-50)', borderRadius: 'var(--radius-md)' }}>
                No reservable resources registered yet. Add a table or consultation suite to enable built-in booking.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {resources.map((res) => (
                  <div
                    key={res.id}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '0.75rem 1rem',
                      background: 'var(--slate-50)',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--slate-200)',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700, color: 'var(--slate-900)', fontSize: '0.9rem' }}>
                        {res.name}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--slate-500)', marginTop: '2px' }}>
                        Type: <strong>{res.resource_type}</strong> • Section: <strong>{res.section || 'General'}</strong> • Fits: <strong>{res.min_party_size}–{res.max_party_size} guests</strong>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleDeleteResource(res.id)}
                      title="Delete resource"
                      style={{ background: 'none', border: 'none', color: 'var(--rose-600)', cursor: 'pointer', padding: '6px' }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Recent Reservations Snapshot */}
            {reservations.length > 0 && (
              <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--slate-100)', paddingTop: '1rem' }}>
                <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--slate-800)', marginBottom: '0.5rem' }}>
                  Confirmed Bookings in Authoritative Database ({reservations.length})
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {reservations.slice(0, 5).map((b) => (
                    <div key={b.id} style={{ fontSize: '0.78rem', background: 'white', border: '1px solid var(--slate-200)', padding: '6px 10px', borderRadius: '6px', display: 'flex', justifyContent: 'space-between' }}>
                      <span><strong>{b.customer_name}</strong> ({b.party_size} guests)</span>
                      <span style={{ color: 'var(--slate-500)' }}>{b.start_time?.slice(0, 16).replace('T', ' ')}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
         TAB 3: FEATURE DEMANDS
         ========================================================================= */}
      {activeTab === 'demands' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: '1.5rem', alignItems: 'flex-start' }}>
          <form onSubmit={handleDemandSubmit} className="card">
            <div className="card-title">
              <Sparkles size={18} color="var(--sky-600)" /> Demand a Custom Tool Feature
            </div>
            <div className="card-desc">
              Request bespoke CRM, telephony, or calendar integrations for engineering review.
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">Tool / Feature Name *</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. SevenRooms Direct VIP Table Sync"
                value={toolName}
                onChange={(e) => setToolName(e.target.value)}
                required
              />
            </div>

            <div className="form-grid" style={{ marginBottom: '1rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Category</label>
                <select
                  className="form-input"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  {DEMAND_CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Priority</label>
                <select
                  className="form-input"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                >
                  {PRIORITIES.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">Target Integration / Software</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. SevenRooms, Salesforce, Practo, Google Calendar"
                value={integrationTarget}
                onChange={(e) => setIntegrationTarget(e.target.value)}
              />
            </div>

            <div className="form-group" style={{ marginBottom: '1.25rem' }}>
              <label className="form-label">Feature Description & Workflow *</label>
              <textarea
                className="form-input"
                rows={4}
                placeholder="Describe how the receptionist should invoke this capability during caller conversations..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
              />
            </div>

            <button type="submit" className="btn-primary" disabled={demandSubmitting} style={{ width: '100%', justifyContent: 'center' }}>
              <Sparkles size={16} /> {demandSubmitting ? 'Submitting...' : 'Submit Feature Demand'}
            </button>
          </form>

          <div className="card">
            <div className="card-title">Submitted Feature Demands ({demands.length})</div>
            <div className="card-desc">Tracks custom engineering requests submitted for {business.name}.</div>

            {demands.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--slate-500)', background: 'var(--slate-50)', borderRadius: 'var(--radius-md)' }}>
                No custom features demanded yet.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {demands.map((d) => (
                  <div key={d.id} style={{ padding: '0.85rem', background: 'var(--slate-50)', border: '1px solid var(--slate-200)', borderRadius: 'var(--radius-md)' }}>
                    <div style={{ fontWeight: 700, color: 'var(--slate-900)', fontSize: '0.9rem' }}>{d.tool_name}</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--slate-600)', margin: '4px 0' }}>{d.description}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--sky-600)', fontWeight: 600 }}>Target: {d.integration_target} • Status: {d.status}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
         CAPABILITY SETUP WIZARD MODAL
         ========================================================================= */}
      {wizardOpen && wizardSchema && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.6)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 'var(--radius-lg)',
              maxWidth: '680px',
              width: '100%',
              maxHeight: '90vh',
              overflowY: 'auto',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {/* Modal Header */}
            <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--slate-200)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--sky-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Capability Guided Setup
                </div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--slate-900)', margin: '2px 0 0' }}>
                  {wizardSchema.name}
                </h2>
              </div>
              <button
                type="button"
                onClick={closeWizard}
                style={{ background: 'none', border: 'none', color: 'var(--slate-400)', cursor: 'pointer', padding: '4px' }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Step Indicators */}
            <div style={{ padding: '0.85rem 1.5rem', background: 'var(--slate-50)', borderBottom: '1px solid var(--slate-200)', display: 'flex', justifyContent: 'space-between' }}>
              {[
                { num: 1, label: 'Integration Choice' },
                { num: 2, label: 'Configuration' },
                { num: 3, label: 'Validation & Tests' },
                { num: 4, label: 'Operational' },
              ].map((s) => (
                <div key={s.num} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem', fontWeight: wizardStep >= s.num ? 700 : 500, color: wizardStep >= s.num ? 'var(--sky-700)' : 'var(--slate-400)' }}>
                  <span style={{ width: '20px', height: '20px', borderRadius: '50%', background: wizardStep >= s.num ? 'var(--sky-500)' : 'var(--slate-200)', color: wizardStep >= s.num ? 'white' : 'var(--slate-600)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem' }}>
                    {s.num}
                  </span>
                  <span>{s.label}</span>
                </div>
              ))}
            </div>

            {/* Modal Content Body */}
            <div style={{ padding: '1.5rem', flex: 1 }}>
              {/* STEP 1: CHOOSE INTEGRATION OPTION */}
              {wizardStep === 1 && (
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--slate-800)', marginBottom: '0.25rem' }}>
                    Select an Integration Architecture
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--slate-600)', marginBottom: '1.25rem' }}>
                    Choose between our built-in first-party database manager or connecting an external authoritative provider.
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                    {wizardSchema.supported_options.map((opt) => (
                      <div
                        key={opt.option_id}
                        onClick={() => setSelectedOptionId(opt.option_id)}
                        style={{
                          padding: '1rem',
                          borderRadius: 'var(--radius-md)',
                          border: `2px solid ${selectedOptionId === opt.option_id ? 'var(--sky-500)' : 'var(--slate-200)'}`,
                          background: selectedOptionId === opt.option_id ? 'var(--sky-50)' : 'white',
                          cursor: 'pointer',
                          transition: 'var(--transition)',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontWeight: 800, fontSize: '0.95rem', color: 'var(--slate-900)' }}>
                            {opt.name}
                          </span>
                          <span style={{ fontSize: '0.72rem', background: opt.is_builtin ? 'var(--emerald-100)' : 'var(--slate-100)', color: opt.is_builtin ? 'var(--emerald-700)' : 'var(--slate-700)', padding: '2px 8px', borderRadius: '10px', fontWeight: 700 }}>
                            {opt.is_builtin ? 'First-Party Built-In' : 'External Provider'}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.82rem', color: 'var(--slate-600)', marginTop: '4px' }}>
                          {opt.description}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--slate-500)', marginTop: '8px' }}>
                          Authoritative Store: <strong>{opt.authoritative_source}</strong>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={handleStartOption}
                      disabled={!selectedOptionId || wizardLoading}
                    >
                      {wizardLoading ? 'Initializing...' : 'Continue to Configuration →'}
                    </button>
                  </div>
                </div>
              )}

              {/* STEP 2: CONFIGURE FIELDS */}
              {wizardStep === 2 && currentOption && (
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--slate-800)', marginBottom: '0.25rem' }}>
                    Configure {currentOption.name}
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--slate-600)', marginBottom: '1.25rem' }}>
                    Fill in the required setup fields. Secrets and tokens are securely vaulted using authenticated AES-256 encryption.
                  </div>

                  {currentOption.setup_fields.length === 0 ? (
                    <div style={{ padding: '1.5rem', background: 'var(--slate-50)', borderRadius: 'var(--radius-md)', textAlign: 'center', color: 'var(--slate-600)', fontSize: '0.85rem' }}>
                      No additional credentials required for this built-in option. It leverages your configured database and resource inventory.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      {currentOption.setup_fields.map((f) => (
                        <div key={f.key} className="form-group">
                          <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span>{f.label} {f.is_mandatory && '*'}</span>
                            {f.is_secret && (
                              <span style={{ fontSize: '0.7rem', color: 'var(--emerald-600)', display: 'flex', alignItems: 'center', gap: '3px' }}>
                                <Lock size={11} /> Encrypted Secret
                              </span>
                            )}
                          </label>
                          {f.field_type === 'textarea' ? (
                            <textarea
                              className="form-input"
                              rows={3}
                              placeholder={f.description}
                              value={wizardFormData[f.key] || ''}
                              onChange={(e) => setWizardFormData({ ...wizardFormData, [f.key]: e.target.value })}
                              required={f.is_mandatory}
                            />
                          ) : (
                            <input
                              type={f.is_secret ? 'password' : 'text'}
                              className="form-input"
                              placeholder={f.description}
                              value={wizardFormData[f.key] || ''}
                              onChange={(e) => setWizardFormData({ ...wizardFormData, [f.key]: e.target.value })}
                              required={f.is_mandatory}
                            />
                          )}
                          <div style={{ fontSize: '0.72rem', color: 'var(--slate-500)', marginTop: '2px' }}>
                            {f.description}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.5rem' }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => setWizardStep(1)}
                    >
                      ← Back
                    </button>
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={handleSaveConfiguration}
                      disabled={wizardLoading}
                    >
                      {wizardLoading ? 'Validating...' : 'Save & Verify Readiness →'}
                    </button>
                  </div>
                </div>
              )}

              {/* STEP 3: VALIDATION AND CHECKS */}
              {wizardStep === 3 && (
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--slate-800)', marginBottom: '0.25rem' }}>
                    Operational Readiness Checks
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--slate-600)', marginBottom: '1.25rem' }}>
                    The platform verifies connectivity, schemas, and resource inventory before activating live calls.
                  </div>

                  {validationReport ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      {validationReport.status === 'pending_provider_approval' && (
                        <div style={{ padding: '0.85rem 1rem', background: '#fef3c7', border: '1px solid #f59e0b', borderRadius: 'var(--radius-md)', color: '#92400e' }}>
                          <div style={{ fontWeight: 800, fontSize: '0.88rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <AlertCircle size={16} /> Partner Integration Agreement Approval Required
                          </div>
                          <div style={{ fontSize: '0.78rem', marginTop: '4px', lineHeight: 1.4 }}>
                            This integration is partner-gated. Live reservation operations remain disabled until your organization has an approved OpenTable Partner Agreement and verified credentials. Live inventory execution is blocked.
                          </div>
                        </div>
                      )}
                      {validationReport.checks?.map((c) => (
                        <div
                          key={c.check_id}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '0.75rem 1rem',
                            borderRadius: 'var(--radius-md)',
                            border: `1px solid ${c.passed ? 'var(--emerald-200)' : 'var(--rose-200)'}`,
                            background: c.passed ? 'var(--emerald-50)' : 'var(--rose-50)',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            {c.passed ? (
                              <CheckCircle2 size={18} color="var(--emerald-600)" />
                            ) : (
                              <AlertCircle size={18} color="var(--rose-600)" />
                            )}
                            <div>
                              <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--slate-900)' }}>
                                {c.name}
                              </div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--slate-600)', marginTop: '2px' }}>
                                {c.details}
                              </div>
                            </div>
                          </div>

                          <span style={{ fontSize: '0.72rem', fontWeight: 800, color: c.passed ? 'var(--emerald-700)' : 'var(--rose-700)' }}>
                            {c.passed ? 'PASSED' : 'ACTION REQUIRED'}
                          </span>
                        </div>
                      ))}

                      {validationReport.missing_requirements && validationReport.missing_requirements.length > 0 && (
                        <div style={{ padding: '0.85rem', background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 'var(--radius-md)', marginTop: '0.5rem' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.82rem', color: '#9a3412', marginBottom: '4px' }}>
                            Missing Requirements:
                          </div>
                          <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.78rem', color: '#c2410c' }}>
                            {validationReport.missing_requirements.map((m, idx) => (
                              <li key={idx}>{m}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--slate-500)' }}>
                      Running pre-flight checks...
                    </div>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.5rem' }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => setWizardStep(2)}
                    >
                      ← Reconfigure
                    </button>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={handleRunValidation}
                        disabled={wizardLoading}
                      >
                        <RefreshCw size={14} /> Re-check
                      </button>
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={handleActivateCapability}
                        disabled={!validationReport?.is_ready || wizardLoading}
                        style={{ opacity: validationReport?.is_ready ? 1 : 0.5 }}
                      >
                        {wizardLoading ? 'Activating...' : 'Activate Capability 🚀'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* STEP 4: OPERATIONAL SUCCESS */}
              {wizardStep === 4 && (
                <div style={{ textAlign: 'center', padding: '2rem 1rem' }}>
                  <div style={{ width: '56px', height: '56px', borderRadius: '50%', background: 'var(--emerald-100)', color: 'var(--emerald-600)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem' }}>
                    <CheckCircle2 size={32} />
                  </div>
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--slate-900)', margin: '0 0 0.5rem' }}>
                    Capability Is Live and Operational!
                  </h3>
                  <p style={{ fontSize: '0.85rem', color: 'var(--slate-600)', maxWidth: '440px', margin: '0 auto 1.5rem', lineHeight: 1.5 }}>
                    The AI Receptionist agent can now authoritatively execute this capability during live customer calls using verified tenant policies.
                  </p>

                  <div style={{ display: 'flex', justifyContent: 'center', gap: '0.75rem' }}>
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={closeWizard}
                    >
                      Return to Dashboard
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleDisconnectCapability}
                      style={{ color: 'var(--rose-700)', borderColor: 'var(--rose-300)' }}
                    >
                      Disconnect Integration
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
