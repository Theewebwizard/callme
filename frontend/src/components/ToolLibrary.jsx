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
  Utensils,
  Bed,
  Clock,
  Stethoscope,
} from 'lucide-react';
import { api } from '../api';
import BookingCalendarView from './BookingCalendarView';
import MenuManagerModal, { MenuManagerView } from './MenuManagerModal';
import RoomManagerModal, { RoomManagerView } from './RoomManagerModal';
import TreatmentManagerModal, { TreatmentManagerView } from './TreatmentManagerModal';
import { getDomainForBusiness } from '../domain/businessDomainRegistry';
import ResourceInventoryCard from './ResourceInventoryCard';

const TOOL_ICONS = {
  answer_faq: BookOpen,
  check_table_availability: Calendar,
  create_table_booking: Calendar,
  check_room_availability: Calendar,
  create_room_booking: Calendar,
  check_appointment_availability: Calendar,
  create_appointment: Calendar,
  take_message: MessageSquare,
  transfer_call: PhoneForwarded,
  query_menu_pricing: Utensils,
  query_room_pricing: Bed,
  query_treatment_pricing: Stethoscope,
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
  const domainConfig = getDomainForBusiness(business);
  const ResourceIcon = domainConfig.resourceConfig.icon || Database;
  const [activeTab, setActiveTab] = useState('capabilities'); // 'capabilities', 'resources', 'demands'
  const [discoveryFilter, setDiscoveryFilter] = useState('all'); // 'all', 'enabled', 'disabled', 'unconfigured', 'unavailable', 'not_implemented'
  const [tools, setTools] = useState([]);
  const [capabilities, setCapabilities] = useState({});
  const [savedEnabledMap, setSavedEnabledMap] = useState({});
  const [enabledMap, setEnabledMap] = useState({});
  const [savingTools, setSavingTools] = useState(false);
  const [demands, setDemands] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [feedback, setFeedback] = useState(null);

  // Resource Management State
  const [resources, setResources] = useState([]);
  const [reservations, setReservations] = useState([]);
  const [loadingResources, setLoadingResources] = useState(false);


  // Wizard Modal State
  const [wizardOpen, setWizardOpen] = useState(false);
  const [menuModalOpen, setMenuModalOpen] = useState(false);
  const [menuItemCount, setMenuItemCount] = useState(17);
  const [roomModalOpen, setRoomModalOpen] = useState(false);
  const [roomCount, setRoomCount] = useState(0);
  const [treatmentModalOpen, setTreatmentModalOpen] = useState(false);
  const [treatmentCount, setTreatmentCount] = useState(0);
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

  useEffect(() => {
    if (activeTab === 'menu' && !domainConfig.hasMenu) {
      setActiveTab('capabilities');
    }
    if (activeTab === 'rooms' && !domainConfig.hasRooms) {
      setActiveTab('capabilities');
    }
    if (activeTab === 'treatments' && !domainConfig.hasTreatments) {
      setActiveTab('capabilities');
    }
  }, [domainConfig.hasMenu, domainConfig.hasRooms, domainConfig.hasTreatments, activeTab]);

  const loadData = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      // 1. Fetch core tools, resources, and demands immediately for instantaneous response
      const [toolsData, demandsData, resList, bookingList] = await Promise.all([
        api.getTools(business.id),
        api.getToolDemands(business.id).catch(() => []),
        api.listResources(business.id).catch(() => []),
        api.listReservations(business.id).catch(() => []),
      ]);
      const initialMap = toolsData.enabled_tools || {};
      setTools(toolsData.tools || []);
      setSavedEnabledMap(initialMap);
      setEnabledMap(initialMap);
      setDemands(demandsData || []);
      setResources(resList || []);
      setReservations(bookingList || []);
      api.getMenu(business.id).then((r) => r?.items && setMenuItemCount(r.items.length)).catch(() => {});
      api.getRooms(business.id).then((r) => r?.items && setRoomCount(r.items.length)).catch(() => {});
      api.getTreatments(business.id).then((r) => r?.items && setTreatmentCount(r.items.length)).catch(() => {});

      // 2. Fetch full live readiness reports (can take ~10s to audit all integration check engines)
      api.getCapabilities(business.id)
        .then((capsData) => {
          const capMap = {};
          (capsData || []).forEach((c) => {
            capMap[c.tool_id] = c;
          });
          setCapabilities(capMap);
        })
        .catch((err) => console.warn('Could not load detailed capability audit reports:', err));
    } catch (err) {
      console.error('Failed to load capability data:', err);
      setErrorMsg(err.message || 'Failed to load capability data');
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
      api.getMenu(business.id).then((r) => r?.items && setMenuItemCount(r.items.length)).catch(() => {});
      api.getRooms(business.id).then((r) => r?.items && setRoomCount(r.items.length)).catch(() => {});
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

  const handleToggle = async (toolId) => {
    const isCurrentlyEnabled = Boolean(enabledMap[toolId]);
    const newEnabled = !isCurrentlyEnabled;

    const nextMap = {
      ...enabledMap,
      [toolId]: newEnabled,
    };

    setEnabledMap(nextMap);
    setSavedEnabledMap(nextMap);

    // Optimistically update capability readiness state
    setCapabilities((prev) => {
      const existing = prev[toolId] || {};
      return {
        ...prev,
        [toolId]: {
          ...existing,
          tool_id: toolId,
          status: newEnabled ? 'ready' : (existing.status || 'not_configured'),
          is_enabled: newEnabled,
        },
      };
    });

    const toolObj = tools.find((t) => t.id === toolId);
    const toolDisplayName = toolObj?.name || toolId;

    try {
      setSavingTools(true);
      await api.updateTools(business.id, nextMap);
      setFeedback({
        type: 'success',
        text: `Tool "${toolDisplayName}" ${newEnabled ? 'enabled' : 'disabled'} successfully!`,
      });
      setTimeout(() => setFeedback(null), 3500);

      // Refresh capability readiness in the background
      api.getCapabilities(business.id).then((capsData) => {
        const capMap = {};
        (capsData || []).forEach((c) => {
          capMap[c.tool_id] = c;
        });
        setCapabilities(capMap);
      }).catch(() => {});
    } catch (err) {
      // Revert if error
      setEnabledMap(enabledMap);
      setSavedEnabledMap(savedEnabledMap);
      setFeedback({ type: 'error', text: `Failed to update tool: ${err.message}` });
    } finally {
      setSavingTools(false);
    }
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

  const getConfigurationBadge = (status) => {
    switch (status) {
      case 'ready':
      case 'configured':
        return (
          <span className="cap-badge-configured">
            <CheckCircle2 size={11} /> Configured
          </span>
        );
      case 'needs_input':
      case 'not_configured':
      default:
        return (
          <span className="cap-badge-needs-setup">
            <AlertCircle size={11} /> Needs Setup
          </span>
        );
    }
  };

  const getVerificationBadge = (status) => {
    switch (status) {
      case 'ready':
        return (
          <span className="cap-badge-verified">
            <ShieldCheck size={11} /> Verified Live
          </span>
        );
      case 'validating':
        return (
          <span className="cap-badge-validating">
            <RefreshCw size={11} className="animate-spin" /> Validating
          </span>
        );
      default:
        return (
          <span className="cap-badge-unverified">
            <Clock size={11} /> Unverified
          </span>
        );
    }
  };

  const getDiscoveryStatus = (t) => {
    if (t.is_implemented === false) return 'not_implemented';
    const isEnabled = Boolean(enabledMap[t.id]);
    if (isEnabled) return 'enabled';
    const cap = capabilities[t.id];
    if (cap?.status === 'degraded' || cap?.status === 'disconnected') return 'unavailable';
    if (!cap || cap.status === 'not_configured' || cap.status === 'needs_input') {
      return 'unconfigured';
    }
    return 'disabled';
  };

  const currentOption = wizardSchema?.supported_options?.find((o) => o.option_id === selectedOptionId);

  if (!business) return null;

  const countAll = tools.length;
  const countEnabled = tools.filter((t) => getDiscoveryStatus(t) === 'enabled').length;
  const countDisabled = tools.filter((t) => getDiscoveryStatus(t) === 'disabled').length;
  const countUnconfigured = tools.filter((t) => getDiscoveryStatus(t) === 'unconfigured').length;
  const countUnavailable = tools.filter((t) => getDiscoveryStatus(t) === 'unavailable').length;
  const countNotImplemented = tools.filter((t) => getDiscoveryStatus(t) === 'not_implemented').length;

  const filteredTools = tools.filter((t) => {
    if (discoveryFilter === 'all') return true;
    return getDiscoveryStatus(t) === discoveryFilter;
  });

  return (
    <section className="main-content">
      <div className="section-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <div>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.25rem 0.65rem',
                borderRadius: 'var(--radius-full)',
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                color: 'var(--text-secondary)',
                fontSize: '0.74rem',
                fontWeight: 600,
                marginBottom: '0.45rem',
              }}
            >
              <Wrench size={12} /> Autonomous Tool Registry
            </div>
            <h1 className="section-title">Capabilities, Inventory & Extensions</h1>
            <p className="section-subtitle">
              Configure verified capabilities, manage built-in table and room inventory, or connect external providers for <strong>{business.name}</strong>.
            </p>
          </div>
        </div>
      </div>

      {errorMsg && (
        <div
          style={{
            padding: '0.85rem 1.15rem',
            borderRadius: 'var(--radius-sm)',
            marginBottom: '1.25rem',
            background: 'rgba(244, 63, 94, 0.1)',
            border: '1px solid rgba(244, 63, 94, 0.3)',
            color: '#fb7185',
            fontSize: '0.82rem',
            fontWeight: 500,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, marginBottom: '0.4rem' }}>
            <AlertCircle size={16} /> Error Loading Capabilities
          </div>
          <div>{errorMsg}</div>
          <div style={{ display: 'flex', gap: '0.65rem', marginTop: '0.65rem' }}>
            {errorMsg.toLowerCase().includes('token') || errorMsg.toLowerCase().includes('authentication') || errorMsg.toLowerCase().includes('credentials') ? (
              <button
                className="btn-secondary"
                style={{ padding: '0.3rem 0.75rem', fontSize: '0.78rem', cursor: 'pointer' }}
                onClick={() => {
                  localStorage.removeItem('callme_token');
                  localStorage.removeItem('callme_active_business_id');
                  localStorage.removeItem('callme_role');
                  window.location.reload();
                }}
              >
                Sign In Again
              </button>
            ) : null}
            <button
              className="btn-primary"
              style={{ padding: '0.3rem 0.75rem', fontSize: '0.78rem', cursor: 'pointer' }}
              onClick={loadData}
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {feedback && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-sm)',
            marginBottom: '1.25rem',
            background: feedback.type === 'success' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
            color: feedback.type === 'success' ? 'var(--mint-400)' : '#fb7185',
            fontSize: '0.82rem',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            border: `1px solid ${feedback.type === 'success' ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)'}`,
          }}
        >
          {feedback.type === 'success' ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
          {feedback.text}
        </div>
      )}

      {/* Primary Navigation Tabs */}
      <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <button
          className={`btn-secondary ${activeTab === 'capabilities' ? 'active' : ''}`}
          style={{
            background: activeTab === 'capabilities' ? '#ffffff' : 'var(--bg-card)',
            borderColor: activeTab === 'capabilities' ? '#ffffff' : 'var(--border-medium)',
            color: activeTab === 'capabilities' ? '#07080a' : 'var(--text-secondary)',
            fontWeight: 600,
            padding: '0.45rem 0.95rem',
            fontSize: '0.8rem',
          }}
          onClick={() => setActiveTab('capabilities')}
        >
          <Wrench size={14} /> Capabilities ({tools.length})
        </button>

        {domainConfig.hasMenu && (
          <button
            className={`btn-secondary ${activeTab === 'menu' ? 'active' : ''}`}
            style={{
              background: activeTab === 'menu' ? '#ffffff' : 'var(--bg-card)',
              borderColor: activeTab === 'menu' ? '#ffffff' : 'var(--border-medium)',
              color: activeTab === 'menu' ? '#07080a' : 'var(--text-secondary)',
              fontWeight: 600,
              padding: '0.45rem 0.95rem',
              fontSize: '0.8rem',
            }}
            onClick={() => setActiveTab('menu')}
          >
            <Utensils size={14} /> 🍽️ {domainConfig.menuConfig.shortTitle} ({menuItemCount})
          </button>
        )}

        {domainConfig.hasRooms && (
          <button
            className={`btn-secondary ${activeTab === 'rooms' ? 'active' : ''}`}
            style={{
              background: activeTab === 'rooms' ? '#ffffff' : 'var(--bg-card)',
              borderColor: activeTab === 'rooms' ? '#ffffff' : 'var(--border-medium)',
              color: activeTab === 'rooms' ? '#07080a' : 'var(--text-secondary)',
              fontWeight: 600,
              padding: '0.45rem 0.95rem',
              fontSize: '0.8rem',
            }}
            onClick={() => setActiveTab('rooms')}
          >
            <Bed size={14} /> 🏨 {domainConfig.roomConfig?.shortTitle || 'Rooms & Rates'} ({roomCount})
          </button>
        )}

        {domainConfig.hasTreatments && (
          <button
            className={`btn-secondary ${activeTab === 'treatments' ? 'active' : ''}`}
            style={{
              background: activeTab === 'treatments' ? '#ffffff' : 'var(--bg-card)',
              borderColor: activeTab === 'treatments' ? '#ffffff' : 'var(--border-medium)',
              color: activeTab === 'treatments' ? '#07080a' : 'var(--text-secondary)',
              fontWeight: 600,
              padding: '0.45rem 0.95rem',
              fontSize: '0.8rem',
            }}
            onClick={() => setActiveTab('treatments')}
          >
            <Stethoscope size={14} /> 🩺 {domainConfig.treatmentConfig?.shortTitle || 'Treatments & Fees'} ({treatmentCount})
          </button>
        )}

        <button
          className={`btn-secondary ${activeTab === 'resources' ? 'active' : ''}`}
          style={{
            background: activeTab === 'resources' ? '#ffffff' : 'var(--bg-card)',
            borderColor: activeTab === 'resources' ? '#ffffff' : 'var(--border-medium)',
            color: activeTab === 'resources' ? '#07080a' : 'var(--text-secondary)',
            fontWeight: 600,
            padding: '0.45rem 0.95rem',
            fontSize: '0.8rem',
          }}
          onClick={() => setActiveTab('resources')}
        >
          <ResourceIcon size={14} /> {domainConfig.resourceConfig.shortTitle} ({resources.length})
        </button>

        <button
          className={`btn-secondary ${activeTab === 'demands' ? 'active' : ''}`}
          style={{
            background: activeTab === 'demands' ? '#ffffff' : 'var(--bg-card)',
            borderColor: activeTab === 'demands' ? '#ffffff' : 'var(--border-medium)',
            color: activeTab === 'demands' ? '#07080a' : 'var(--text-secondary)',
            fontWeight: 600,
            padding: '0.45rem 0.95rem',
            fontSize: '0.8rem',
          }}
          onClick={() => setActiveTab('demands')}
        >
          <Sparkles size={14} /> Custom Feature Demands ({demands.length})
        </button>
      </div>

      {/* =========================================================================
         TAB 1: CAPABILITIES & SETUP WIZARD
         ========================================================================= */}
      {activeTab === 'capabilities' && (
        <div>
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-medium)',
              borderRadius: 'var(--radius-md)',
              padding: '0.85rem 1.25rem',
              marginBottom: '1.25rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '1rem',
              flexWrap: 'wrap',
              boxShadow: 'var(--specular-top)',
            }}
          >
            <div>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.86rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Layers size={15} style={{ color: 'var(--mint-400)' }} /> Industry Policy: <strong>{business.industry || 'General'}</strong>
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', marginTop: '2px' }}>
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

          {/* Feature Discovery Status Filter Bar */}
          <div style={{ display: 'flex', gap: '0.45rem', marginBottom: '1.25rem', flexWrap: 'wrap', alignItems: 'center', background: 'var(--bg-surface-elevated)', padding: '0.6rem 0.85rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-medium)' }}>
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-tertiary)', marginRight: '6px' }}>Status Filter:</span>
            {[
              { id: 'all', label: 'All Capabilities', count: countAll },
              { id: 'enabled', label: 'Enabled', count: countEnabled },
              { id: 'disabled', label: 'Disabled', count: countDisabled },
              { id: 'unconfigured', label: 'Unconfigured', count: countUnconfigured },
              { id: 'unavailable', label: 'Unavailable', count: countUnavailable },
              { id: 'not_implemented', label: 'Not Yet Implemented', count: countNotImplemented },
            ].map((f) => {
              const isSelected = discoveryFilter === f.id;
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setDiscoveryFilter(f.id)}
                  style={{
                    fontSize: '0.76rem',
                    padding: '3px 10px',
                    borderRadius: 'var(--radius-full)',
                    border: isSelected ? '1px solid var(--border-medium)' : '1px solid transparent',
                    background: isSelected ? 'rgba(255, 255, 255, 0.08)' : 'transparent',
                    fontWeight: isSelected ? 600 : 500,
                    color: isSelected ? 'var(--text-primary)' : 'var(--text-tertiary)',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <span>{f.label}</span>
                  <span style={{
                    fontSize: '0.68rem',
                    fontFamily: 'var(--font-mono)',
                    padding: '1px 5px',
                    borderRadius: '10px',
                    background: isSelected ? 'rgba(255, 255, 255, 0.12)' : 'rgba(255, 255, 255, 0.04)',
                    color: isSelected ? 'var(--text-primary)' : 'var(--text-tertiary)',
                  }}>
                    {f.count}
                  </span>
                </button>
              );
            })}
          </div>

          {loading ? (
            <div className="card" style={{ padding: '3.5rem 2rem', textAlign: 'center', color: 'var(--slate-500)' }}>
              <div style={{ display: 'inline-block', width: '28px', height: '28px', border: '3px solid var(--indigo-100)', borderTopColor: 'var(--indigo-600)', borderRadius: '50%', animation: 'spin 1s linear infinite', marginBottom: '0.75rem' }} />
              <div style={{ fontWeight: 600, color: 'var(--slate-700)', fontSize: '0.95rem' }}>Loading business capabilities & tools...</div>
            </div>
          ) : filteredTools.length === 0 ? (
            <div className="card" style={{ padding: '3rem 2rem', textAlign: 'center', color: 'var(--slate-500)' }}>
              <p style={{ fontWeight: 600, fontSize: '0.95rem', marginBottom: '0.5rem' }}>
                No capabilities match filter <strong>"{discoveryFilter}"</strong>
              </p>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setDiscoveryFilter('all')}
                style={{ fontSize: '0.8rem', padding: '0.35rem 0.85rem' }}
              >
                Reset to All Capabilities
              </button>
            </div>
          ) : (
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <div className="table-wrapper" style={{ border: 'none' }}>
                <table className="modern-table">
                  <thead>
                    <tr>
                      <th style={{ width: '42%' }}>Capability & Purpose</th>
                      <th style={{ width: '16%' }}>Telephony Voice Link</th>
                      <th style={{ width: '14%' }}>Configuration State</th>
                      <th style={{ width: '14%' }}>Verification Status</th>
                      <th style={{ width: '14%', textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTools.map((t) => {
                      const IconComponent = TOOL_ICONS[t.id] || Wrench;
                      const isEnabled = Boolean(enabledMap[t.id]);
                      const cap = capabilities[t.id];
                      const capStatus = isEnabled
                        ? (cap?.status === 'degraded' || cap?.status === 'disconnected' ? cap.status : 'ready')
                        : (cap?.status || 'not_configured');
                      const authSource = cap?.authoritative_source || 'Platform Default Engine';

                      return (
                        <tr key={t.id}>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                              <div
                                style={{
                                  width: '32px',
                                  height: '32px',
                                  borderRadius: 'var(--radius-sm)',
                                  background: isEnabled ? '#ffffff' : 'var(--bg-surface-elevated)',
                                  color: isEnabled ? '#07080a' : 'var(--text-secondary)',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  flexShrink: 0,
                                  border: '1px solid var(--border-medium)',
                                  marginTop: '2px',
                                }}
                              >
                                <IconComponent size={15} />
                              </div>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                  <span style={{ fontWeight: 600, fontSize: '0.86rem', color: 'var(--text-primary)' }}>
                                    {t.name}
                                  </span>
                                  <span style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', background: 'var(--bg-surface-elevated)', border: '1px solid var(--border-medium)', color: 'var(--text-tertiary)', padding: '1px 5px', borderRadius: '4px' }}>
                                    {authSource}
                                  </span>
                                </div>
                                <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', lineHeight: 1.4, maxWidth: '420px' }}>
                                  {t.description}
                                </div>
                              </div>
                            </div>
                          </td>

                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                              <label className="switch" title={t.is_implemented === false ? "Tool not yet implemented" : (isEnabled ? "Disable tool" : "Enable tool")}>
                                <input
                                  type="checkbox"
                                  checked={isEnabled}
                                  disabled={t.is_implemented === false}
                                  onChange={() => handleToggle(t.id)}
                                  aria-label={`Toggle ${t.name}`}
                                />
                                <span className="slider" />
                              </label>
                              <span
                                className={isEnabled ? "cap-link-active" : "cap-link-disabled"}
                                style={{ fontSize: '0.78rem', fontWeight: 600, letterSpacing: '-0.01em', userSelect: 'none' }}
                              >
                                {isEnabled ? 'Active' : 'Disabled'}
                              </span>
                            </div>
                          </td>

                          <td>
                            {getConfigurationBadge(capStatus)}
                          </td>

                          <td>
                            {getVerificationBadge(capStatus)}
                          </td>

                          <td style={{ textAlign: 'right' }}>
                            <div style={{ display: 'inline-flex', gap: '0.4rem', justifyContent: 'flex-end', alignItems: 'center' }}>
                              {t.id === 'query_menu_pricing' && domainConfig.hasMenu && (
                                <button
                                  type="button"
                                  className="cap-menu-btn"
                                  onClick={() => setMenuModalOpen(true)}
                                  title="Upload and manage restaurant menu"
                                >
                                  <Utensils size={12} />
                                  <span>Menu</span>
                                </button>
                              )}
                              {t.id === 'query_room_pricing' && domainConfig.hasRooms && (
                                <button
                                  type="button"
                                  className="cap-menu-btn"
                                  onClick={() => setRoomModalOpen(true)}
                                  title="Upload and manage hotel room types and rates"
                                >
                                  <Bed size={12} />
                                  <span>Rooms</span>
                                </button>
                              )}
                              {t.id === 'query_treatment_pricing' && domainConfig.hasTreatments && (
                                <button
                                  type="button"
                                  className="cap-menu-btn"
                                  onClick={() => setTreatmentModalOpen(true)}
                                  title="Upload and manage clinic treatments and fee card"
                                >
                                  <Stethoscope size={12} />
                                  <span>Treatments</span>
                                </button>
                              )}
                              <button
                                type="button"
                                className="btn-secondary"
                                onClick={() => openWizard(t)}
                                style={{ padding: '0.25rem 0.6rem', fontSize: '0.74rem' }}
                                title="Open guided configuration wizard"
                              >
                                <Sliders size={12} />
                                <span>Configure</span>
                              </button>
                              <button
                                type="button"
                                className="btn-secondary"
                                onClick={() => handleTestConnection(t.id)}
                                style={{ padding: '0.25rem 0.5rem', fontSize: '0.74rem' }}
                                title="Test live connectivity and verify permissions"
                              >
                                <ShieldCheck size={12} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
         TAB: RESTAURANT MENU & SEMANTIC PRICING STORE
         ========================================================================= */}
      {activeTab === 'menu' && domainConfig.hasMenu && (
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-card)', border: '1px solid var(--border-medium)' }}>
          <div style={{ marginBottom: '1.25rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Utensils size={20} color="var(--color-emerald)" /> Restaurant Menu & Semantic Pricing Store
            </h2>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0 }}>
              Upload and manage your dishes, categories, and prices for <strong style={{ color: 'var(--text-primary)' }}>{business.name}</strong>. Choose any of the 3 upload methods below.
            </p>
          </div>

          <MenuManagerView
            business={business}
            isEmbedded={true}
            defaultTab="upload"
            onMenuUpdated={() => {
              loadData();
              api.getMenu(business.id).then((r) => r?.items && setMenuItemCount(r.items.length)).catch(() => {});
      api.getRooms(business.id).then((r) => r?.items && setRoomCount(r.items.length)).catch(() => {});
            }}
          />
        </div>
      )}

      {/* =========================================================================
         TAB: HOTEL ROOM TYPES & RATE CARD STORE
         ========================================================================= */}
      {activeTab === 'rooms' && domainConfig.hasRooms && (
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-card)', border: '1px solid var(--border-medium)' }}>
          <div style={{ marginBottom: '1.25rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Bed size={20} color="var(--sky-400, #38bdf8)" /> Hotel Room Types, Rates & Amenities Store
            </h2>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0 }}>
              Upload and manage your room tiers, tariffs, bed configurations, and amenities for <strong style={{ color: 'var(--text-primary)' }}>{business.name}</strong>.
            </p>
          </div>

          <RoomManagerView
            business={business}
            isEmbedded={true}
            defaultTab="rooms"
            onRoomsUpdated={() => {
              loadData();
              api.getRooms(business.id).then((r) => r?.items && setRoomCount(r.items.length)).catch(() => {});
            }}
          />
        </div>
      )}

      {/* =========================================================================
         TAB: CLINIC MEDICAL TREATMENTS & FEE STORE
         ========================================================================= */}
      {activeTab === 'treatments' && domainConfig.hasTreatments && (
        <div className="card" style={{ padding: '1.5rem', background: 'var(--bg-card)', border: '1px solid var(--border-medium)' }}>
          <div style={{ marginBottom: '1.25rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Stethoscope size={20} color="var(--primary, #3b82f6)" />
              {domainConfig.treatmentConfig?.title || 'Clinic Treatments, Services & Fee Store'}
            </h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: 0 }}>
              {domainConfig.treatmentConfig?.description || 'Manage procedures, doctor specializations, and fee catalog for ' + business.name}
            </p>
          </div>
          <TreatmentManagerView
            business={business}
            isEmbedded={true}
            defaultTab="treatments"
            onTreatmentsUpdated={() => {
              loadData();
              api.getTreatments(business.id).then((r) => r?.items && setTreatmentCount(r.items.length)).catch(() => {});
            }}
          />
        </div>
      )}

      {/* =========================================================================
         TAB 2: RESOURCE INVENTORY & BOOKINGS (FIRST-PARTY ENGINE)
         ========================================================================= */}
      {activeTab === 'resources' && (
        <ResourceInventoryCard
          business={business}
          domainConfig={domainConfig}
          resources={resources}
          reservations={reservations}
          onRefresh={loadResources}
        />
      )}

      {/* =========================================================================
         TAB 3: FEATURE DEMANDS
         ========================================================================= */}
      {activeTab === 'demands' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: '1.5rem', alignItems: 'flex-start' }}>
          <form onSubmit={handleDemandSubmit} className="card">
            <div className="card-title">
              <Sparkles size={18} color="var(--indigo-600)" /> Demand a Custom Tool Feature
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
                    <div style={{ fontSize: '0.72rem', color: 'var(--indigo-600)', fontWeight: 600 }}>Target: {d.integration_target} • Status: {d.status}</div>
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
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
        >
          <div
            style={{
              background: 'var(--bg-card)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border-medium)',
              maxWidth: (wizardTool?.id === 'query_menu_pricing' && wizardStep === 2) ? '920px' : '680px',
              width: '100%',
              maxHeight: '90vh',
              overflowY: 'auto',
              boxShadow: 'var(--shadow-modal)',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {/* Modal Header */}
            <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--border-medium)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--color-emerald)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Capability Guided Setup
                </div>
                <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)', margin: '2px 0 0' }}>
                  {wizardSchema.name}
                </h2>
              </div>
              <button
                type="button"
                onClick={closeWizard}
                style={{ background: 'none', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer', padding: '4px' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Step Indicators */}
            <div style={{ padding: '0.85rem 1.5rem', background: 'var(--bg-surface-elevated)', borderBottom: '1px solid var(--border-medium)', display: 'flex', justifyContent: 'space-between' }}>
              {[
                { num: 1, label: 'Integration Choice' },
                { num: 2, label: 'Configuration' },
                { num: 3, label: 'Validation & Tests' },
                { num: 4, label: 'Operational' },
              ].map((s) => (
                <div key={s.num} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.76rem', fontWeight: wizardStep >= s.num ? 600 : 500, color: wizardStep >= s.num ? 'var(--color-emerald)' : 'var(--text-tertiary)' }}>
                  <span style={{ width: '20px', height: '20px', borderRadius: '50%', background: wizardStep >= s.num ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255, 255, 255, 0.04)', color: wizardStep >= s.num ? 'var(--color-emerald)' : 'var(--text-tertiary)', border: `1px solid ${wizardStep >= s.num ? 'rgba(16, 185, 129, 0.35)' : 'var(--border-medium)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', fontFamily: 'var(--font-mono)' }}>
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
                          border: `1px solid ${selectedOptionId === opt.option_id ? 'var(--color-emerald)' : 'var(--border-medium)'}`,
                          background: selectedOptionId === opt.option_id ? 'rgba(16, 185, 129, 0.08)' : 'var(--bg-surface-elevated)',
                          cursor: 'pointer',
                          transition: 'var(--transition)',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>
                            {opt.name}
                          </span>
                          <span style={{
                            fontSize: '0.72rem',
                            background: (opt.is_built_in ?? opt.is_builtin) ? 'rgba(16, 185, 129, 0.1)' : 'rgba(255, 255, 255, 0.05)',
                            color: (opt.is_built_in ?? opt.is_builtin) ? 'var(--color-emerald)' : 'var(--text-secondary)',
                            border: `1px solid ${(opt.is_built_in ?? opt.is_builtin) ? 'rgba(16, 185, 129, 0.25)' : 'var(--border-medium)'}`,
                            padding: '2px 8px',
                            borderRadius: 'var(--radius-full)',
                            fontWeight: 600,
                          }}>
                            {(opt.is_built_in ?? opt.is_builtin) ? 'First-Party Built-In' : 'External Provider'}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: '4px', lineHeight: 1.45 }}>
                          {opt.description}
                        </div>
                        <div style={{ fontSize: '0.74rem', color: 'var(--text-tertiary)', marginTop: '8px' }}>
                          Authoritative Store: <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{opt.authoritative_source}</strong>
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

                  {(wizardTool?.id === 'query_menu_pricing' || currentOption.option_id === 'builtin_restaurant_menu') && domainConfig.hasMenu && (
                    <div style={{ marginTop: '1.5rem', borderTop: '2px solid var(--slate-100)', paddingTop: '1.25rem' }}>
                      <div style={{ marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--slate-900)', margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Utensils size={18} color="var(--sky-600)" /> Restaurant Menu & Pricing (All 3 Upload Options)
                        </h3>
                        <p style={{ fontSize: '0.8rem', color: 'var(--slate-600)', margin: 0 }}>
                          Upload, paste, or manage your restaurant dishes using any of the 3 options below. The AI receptionist queries this dynamically for prices and ingredients.
                        </p>
                      </div>

                      <MenuManagerView
                        business={business}
                        isEmbedded={true}
                        onMenuUpdated={() => {
                          loadData();
                        }}
                      />
                    </div>
                  )}

                  {(wizardTool?.id === 'query_treatment_pricing' || currentOption.option_id === 'builtin_clinic_treatments') && domainConfig.hasTreatments && (
                    <div style={{ marginTop: '1.5rem', borderTop: '2px solid var(--slate-100)', paddingTop: '1.25rem' }}>
                      <div style={{ marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--slate-900)', margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Stethoscope size={18} color="var(--primary, #3b82f6)" /> Clinical Treatments & Fee Store
                        </h3>
                        <p style={{ fontSize: '0.8rem', color: 'var(--slate-600)', margin: 0 }}>
                          Upload, paste, or manage your procedures, consultation charges, and doctor specialties. The receptionist AI uses this dynamically for caller inquiries.
                        </p>
                      </div>
                      <TreatmentManagerView
                        business={business}
                        isEmbedded={true}
                        onTreatmentsUpdated={() => {
                          loadData();
                          api.getTreatments(business.id).then((r) => r?.items && setTreatmentCount(r.items.length)).catch(() => {});
                        }}
                      />
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

      {/* Standalone Menu Manager Modal */}
      <MenuManagerModal
        business={business}
        isOpen={menuModalOpen}
        onClose={() => setMenuModalOpen(false)}
        onMenuUpdated={loadData}
      />

      {/* Standalone Room Manager Modal */}
      <RoomManagerModal
        business={business}
        isOpen={roomModalOpen}
        onClose={() => setRoomModalOpen(false)}
        onRoomsUpdated={loadData}
      />

      {/* Standalone Treatment Manager Modal */}
      <TreatmentManagerModal
        business={business}
        isOpen={treatmentModalOpen}
        onClose={() => setTreatmentModalOpen(false)}
        onTreatmentsUpdated={loadData}
      />
    </section>
  );
}