import React, { useState, useEffect } from 'react';
import {
  Stethoscope,
  UploadCloud,
  FileText,
  Sparkles,
  Plus,
  Trash2,
  Search,
  Check,
  AlertCircle,
  X,
  Layers,
  Clock,
  UserCheck,
  ClipboardList,
  Info,
  Sparkle,
} from 'lucide-react';
import { api } from '../api';

const DEFAULT_CATEGORIES = [
  'Consultation',
  'Preventive',
  'Restoration',
  'Orthodontics',
  'Prosthodontics',
  'Cosmetic',
  'Surgery',
  'Pediatric',
];

const COMMON_PRACTITIONERS = [
  'General Dentist',
  'Orthodontist',
  'Endodontist',
  'Prosthodontist',
  'Oral Surgeon',
  'Periodontist',
  'Pediatric Dentist',
  'Cosmetic Dentist',
  'General Physician',
];

export function TreatmentManagerView({
  business,
  isEmbedded = false,
  onTreatmentsUpdated,
  onClose,
  defaultTab = 'treatments',
}) {
  const [activeTab, setActiveTab] = useState(defaultTab); // 'treatments' | 'paste' | 'upload' | 'add'
  const [treatments, setTreatments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState(null); // { type: 'success' | 'error', text: '' }

  // Option 1: Paste Brochure / Rate Sheet
  const [pastedText, setPastedText] = useState('');
  const [pasteCategory, setPasteCategory] = useState('Consultation');
  const [parsedPasteItems, setParsedPasteItems] = useState([]);
  const [replaceOnPaste, setReplaceOnPaste] = useState(false);

  // Option 2: File Upload (JSON / CSV)
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileParsedPreview, setFileParsedPreview] = useState([]);
  const [replaceOnFile, setReplaceOnFile] = useState(false);

  // Option 3: Single Item Add
  const [newName, setNewName] = useState('');
  const [newCategory, setNewCategory] = useState('Consultation');
  const [newBaseFee, setNewBaseFee] = useState('');
  const [newFeeRangeMax, setNewFeeRangeMax] = useState('');
  const [newDuration, setNewDuration] = useState('30');
  const [newPractitioner, setNewPractitioner] = useState('General Dentist');
  const [newDesc, setNewDesc] = useState('');
  const [newPrep, setNewPrep] = useState('');

  // Filters
  const [searchFilter, setSearchFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('All');

  useEffect(() => {
    if (business?.id) {
      loadTreatments();
    }
  }, [business?.id]);

  const loadTreatments = async () => {
    if (!business?.id) return;
    setLoading(true);
    try {
      const res = await api.getTreatments(business.id);
      if (res && res.items) {
        setTreatments(res.items);
      }
    } catch (err) {
      console.error('Failed to load treatments:', err);
    } finally {
      setLoading(false);
    }
  };

  const notifySuccess = (msg) => {
    setFeedback({ type: 'success', text: msg });
    setTimeout(() => setFeedback(null), 4000);
  };

  const notifyError = (msg) => {
    setFeedback({ type: 'error', text: msg });
    setTimeout(() => setFeedback(null), 5000);
  };

  // 1. Delete single item
  const handleDeleteTreatment = async (treatmentId) => {
    if (!confirm('Are you sure you want to remove this procedure from your clinic fee store?')) return;
    try {
      await api.deleteTreatment(business.id, treatmentId);
      setTreatments((prev) => prev.filter((t) => t.id !== treatmentId));
      notifySuccess('Procedure deleted successfully.');
      if (onTreatmentsUpdated) onTreatmentsUpdated();
    } catch (err) {
      notifyError('Failed to delete procedure: ' + (err.message || 'Server error'));
    }
  };

  // 2. Parse Pasted Text
  const handleParsePastedText = async () => {
    if (!pastedText.trim()) {
      notifyError('Please paste some procedure brochure or rate card text first.');
      return;
    }
    setSaving(true);
    try {
      const res = await api.parseTreatmentText(business.id, pastedText, pasteCategory);
      if (res && res.items && res.items.length > 0) {
        setParsedPasteItems(res.items);
        notifySuccess(`Successfully detected ${res.items.length} procedures from text.`);
      } else {
        notifyError('Could not recognize any valid procedures with fees. Check format (e.g., "Root Canal - ₹4500").');
      }
    } catch (err) {
      notifyError('Parsing failed: ' + (err.message || 'Server error'));
    } finally {
      setSaving(false);
    }
  };

  const handleSaveParsedPaste = async () => {
    if (!parsedPasteItems.length) return;
    setSaving(true);
    try {
      const res = await api.uploadTreatments(business.id, parsedPasteItems, replaceOnPaste);
      notifySuccess(`Imported ${res.count || parsedPasteItems.length} procedures to clinic fee store!`);
      setPastedText('');
      setParsedPasteItems([]);
      setActiveTab('treatments');
      await loadTreatments();
      if (onTreatmentsUpdated) onTreatmentsUpdated();
    } catch (err) {
      notifyError('Import failed: ' + (err.message || 'Server error'));
    } finally {
      setSaving(false);
    }
  };

  // 3. File Upload Handler
  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const content = event.target?.result;
        if (typeof content !== 'string') return;

        if (file.name.endsWith('.json')) {
          const parsed = JSON.parse(content);
          const items = Array.isArray(parsed) ? parsed : parsed.items || parsed.treatments || [];
          setFileParsedPreview(items);
        } else if (file.name.endsWith('.csv')) {
          const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0);
          if (lines.length <= 1) {
            notifyError('CSV file has no data rows.');
            return;
          }
          const headers = lines[0].split(',').map((h) => h.trim().toLowerCase());
          const nameIdx = headers.findIndex((h) => h.includes('name') || h.includes('treatment') || h.includes('procedure'));
          const feeIdx = headers.findIndex((h) => h.includes('price') || h.includes('fee') || h.includes('cost') || h.includes('rate'));
          const catIdx = headers.findIndex((h) => h.includes('cat') || h.includes('department'));
          const durIdx = headers.findIndex((h) => h.includes('duration') || h.includes('mins'));
          const docIdx = headers.findIndex((h) => h.includes('doctor') || h.includes('practitioner') || h.includes('specialist'));

          const parsedList = [];
          for (let i = 1; i < lines.length; i++) {
            const cols = lines[i].split(',').map((c) => c.trim().replace(/^["']|["']$/g, ''));
            if (!cols[nameIdx] || !cols[feeIdx]) continue;
            parsedList.push({
              name: cols[nameIdx],
              category: catIdx !== -1 && cols[catIdx] ? cols[catIdx] : 'Consultation',
              base_fee: parseFloat(cols[feeIdx]) || 500,
              fee_range_max: parseFloat(cols[feeIdx]) || 500,
              duration_minutes: durIdx !== -1 && parseInt(cols[durIdx]) ? parseInt(cols[durIdx]) : 30,
              practitioner_type: docIdx !== -1 && cols[docIdx] ? cols[docIdx] : 'General Dentist',
              description: '',
              preparation_instructions: '',
              is_available: true,
            });
          }
          setFileParsedPreview(parsedList);
        }
      } catch (err) {
        notifyError('Failed to parse file: ' + err.message);
      }
    };
    reader.readAsText(file);
  };

  const handleSaveUploadedFile = async () => {
    if (!fileParsedPreview.length) return;
    setSaving(true);
    try {
      const res = await api.uploadTreatments(business.id, fileParsedPreview, replaceOnFile);
      notifySuccess(`Successfully uploaded ${res.count || fileParsedPreview.length} procedures!`);
      setSelectedFile(null);
      setFileParsedPreview([]);
      setActiveTab('treatments');
      await loadTreatments();
      if (onTreatmentsUpdated) onTreatmentsUpdated();
    } catch (err) {
      notifyError('Upload failed: ' + (err.message || 'Server error'));
    } finally {
      setSaving(false);
    }
  };

  // 4. Single Add Handler
  const handleAddSingleTreatment = async (e) => {
    e.preventDefault();
    if (!newName.trim() || !newBaseFee) {
      notifyError('Please enter procedure name and base fee.');
      return;
    }
    setSaving(true);
    try {
      const payload = [
        {
          name: newName.trim(),
          category: newCategory,
          base_fee: parseFloat(newBaseFee),
          fee_range_max: newFeeRangeMax ? parseFloat(newFeeRangeMax) : parseFloat(newBaseFee),
          currency: 'INR',
          duration_minutes: parseInt(newDuration) || 30,
          practitioner_type: newPractitioner,
          description: newDesc.trim() || null,
          preparation_instructions: newPrep.trim() || null,
          is_available: true,
        },
      ];
      await api.uploadTreatments(business.id, payload, false);
      notifySuccess(`Added "${newName}" to fee store!`);
      setNewName('');
      setNewBaseFee('');
      setNewFeeRangeMax('');
      setNewDesc('');
      setNewPrep('');
      setActiveTab('treatments');
      await loadTreatments();
      if (onTreatmentsUpdated) onTreatmentsUpdated();
    } catch (err) {
      notifyError('Failed to add treatment: ' + (err.message || 'Server error'));
    } finally {
      setSaving(false);
    }
  };

  // Filtered treatment list
  const filteredTreatments = treatments.filter((item) => {
    const matchesCat = categoryFilter === 'All' || item.category === categoryFilter;
    const matchesSearch =
      !searchFilter.trim() ||
      item.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
      (item.description && item.description.toLowerCase().includes(searchFilter.toLowerCase())) ||
      (item.practitioner_type && item.practitioner_type.toLowerCase().includes(searchFilter.toLowerCase()));
    return matchesCat && matchesSearch;
  });

  const uniqueCategories = ['All', ...new Set(treatments.map((t) => t.category).filter(Boolean))];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
            <Stethoscope size={20} color="var(--primary, #3b82f6)" />
            Clinic Treatments, Services & Fee Store
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', margin: '0.25rem 0 0 0' }}>
            Authoritative clinical procedures, consultation charges, doctor specializations, and patient preparation notes.
          </p>
        </div>

        {onClose && (
          <button
            onClick={onClose}
            className="btn btn-secondary"
            style={{ padding: '0.35rem 0.65rem', borderRadius: '6px' }}
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Feedback Banner */}
      {feedback && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            fontSize: '0.875rem',
            backgroundColor: feedback.type === 'success' ? 'rgba(34, 197, 94, 0.12)' : 'rgba(239, 68, 68, 0.12)',
            color: feedback.type === 'success' ? '#16a34a' : '#dc2626',
            border: `1px solid ${feedback.type === 'success' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
          }}
        >
          {feedback.type === 'success' ? <Check size={16} /> : <AlertCircle size={16} />}
          <span>{feedback.text}</span>
        </div>
      )}

      {/* Navigation Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', gap: '0.5rem', flexWrap: 'wrap' }}>
        <button
          onClick={() => setActiveTab('treatments')}
          style={{
            padding: '0.6rem 1rem',
            fontWeight: 500,
            fontSize: '0.875rem',
            borderBottom: activeTab === 'treatments' ? '2px solid var(--primary, #3b82f6)' : '2px solid transparent',
            color: activeTab === 'treatments' ? 'var(--primary, #3b82f6)' : 'var(--text-muted)',
            background: 'none',
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
          }}
        >
          <ClipboardList size={16} />
          Treatments & Fee Store ({treatments.length})
        </button>

        <button
          onClick={() => setActiveTab('paste')}
          style={{
            padding: '0.6rem 1rem',
            fontWeight: 500,
            fontSize: '0.875rem',
            borderBottom: activeTab === 'paste' ? '2px solid var(--primary, #3b82f6)' : '2px solid transparent',
            color: activeTab === 'paste' ? 'var(--primary, #3b82f6)' : 'var(--text-muted)',
            background: 'none',
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
          }}
        >
          <Sparkles size={16} />
          Paste Service Brochure / Fee Sheet
        </button>

        <button
          onClick={() => setActiveTab('add')}
          style={{
            padding: '0.6rem 1rem',
            fontWeight: 500,
            fontSize: '0.875rem',
            borderBottom: activeTab === 'add' ? '2px solid var(--primary, #3b82f6)' : '2px solid transparent',
            color: activeTab === 'add' ? 'var(--primary, #3b82f6)' : 'var(--text-muted)',
            background: 'none',
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
          }}
        >
          <Plus size={16} />
          Add Single Procedure
        </button>

        <button
          onClick={() => setActiveTab('upload')}
          style={{
            padding: '0.6rem 1rem',
            fontWeight: 500,
            fontSize: '0.875rem',
            borderBottom: activeTab === 'upload' ? '2px solid var(--primary, #3b82f6)' : '2px solid transparent',
            color: activeTab === 'upload' ? 'var(--primary, #3b82f6)' : 'var(--text-muted)',
            background: 'none',
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
          }}
        >
          <UploadCloud size={16} />
          Upload CSV / JSON
        </button>
      </div>

      {/* TAB 1: Treatments & Fee Store List */}
      {activeTab === 'treatments' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Controls & Search */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: '220px' }}>
              <div style={{ position: 'relative', width: '100%', maxWidth: '320px' }}>
                <Search size={15} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <input
                  type="text"
                  placeholder="Search procedures, symptoms, doctors..."
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  className="input"
                  style={{ paddingLeft: '2.2rem', width: '100%', fontSize: '0.85rem' }}
                />
              </div>

              {uniqueCategories.length > 2 && (
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="input"
                  style={{ fontSize: '0.85rem', width: 'auto' }}
                >
                  {uniqueCategories.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              )}
            </div>

            <button
              onClick={() => setActiveTab('add')}
              className="btn btn-primary"
              style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}
            >
              <Plus size={15} /> Add Procedure
            </button>
          </div>

          {/* Grid of Procedure Cards */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
              Loading clinic treatments...
            </div>
          ) : filteredTreatments.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '3rem 1.5rem',
                border: '1px dashed var(--border)',
                borderRadius: '12px',
                background: 'rgba(255, 255, 255, 0.02)',
              }}
            >
              <Stethoscope size={40} style={{ color: 'var(--text-muted)', marginBottom: '0.75rem', opacity: 0.6 }} />
              <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
                {searchFilter || categoryFilter !== 'All' ? 'No matching treatments found' : 'No treatments uploaded yet'}
              </h3>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', maxWidth: '420px', margin: '0 auto 1.25rem auto' }}>
                Upload your clinic service rate sheet, paste procedure charges, or add consultation fees so your AI receptionist can provide instant pricing answers.
              </p>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '0.75rem' }}>
                <button
                  onClick={() => setActiveTab('paste')}
                  className="btn btn-primary"
                  style={{ fontSize: '0.85rem' }}
                >
                  <Sparkles size={14} style={{ marginRight: '0.35rem' }} /> Paste Rate Sheet
                </button>
                <button
                  onClick={() => setActiveTab('add')}
                  className="btn btn-secondary"
                  style={{ fontSize: '0.85rem' }}
                >
                  Add Manually
                </button>
              </div>
            </div>
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: '1rem',
              }}
            >
              {filteredTreatments.map((item) => {
                const isRange = item.fee_range_max && item.fee_range_max > item.base_fee;
                const feeText = isRange
                  ? `₹${Math.round(item.base_fee).toLocaleString()} - ₹${Math.round(item.fee_range_max).toLocaleString()}`
                  : `₹${Math.round(item.base_fee).toLocaleString()}`;

                return (
                  <div
                    key={item.id}
                    className="card"
                    style={{
                      padding: '1rem',
                      borderRadius: '10px',
                      border: '1px solid var(--border)',
                      background: 'var(--bg-card)',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      gap: '0.75rem',
                      position: 'relative',
                    }}
                  >
                    <div>
                      {/* Category Badge & Duration */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                        <span
                          style={{
                            fontSize: '0.75rem',
                            padding: '0.2rem 0.5rem',
                            borderRadius: '999px',
                            background: 'rgba(59, 130, 246, 0.12)',
                            color: 'var(--primary, #3b82f6)',
                            fontWeight: 600,
                          }}
                        >
                          {item.category || 'Consultation'}
                        </span>

                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                          <Clock size={12} />
                          ~{item.duration_minutes || 30} mins
                        </span>
                      </div>

                      {/* Procedure Name */}
                      <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: '0 0 0.35rem 0', lineHeight: 1.3 }}>
                        {item.name}
                      </h4>

                      {/* Doctor / Specialist */}
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.5rem' }}>
                        <UserCheck size={13} color="#10b981" />
                        <span>{item.practitioner_type || 'General Dentist'}</span>
                      </div>

                      {/* Description */}
                      {item.description && (
                        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0 0 0.5rem 0', lineHeight: 1.4 }}>
                          {item.description}
                        </p>
                      )}

                      {/* Preparation Notes */}
                      {item.preparation_instructions && (
                        <div
                          style={{
                            fontSize: '0.75rem',
                            padding: '0.4rem 0.6rem',
                            background: 'rgba(234, 179, 8, 0.1)',
                            borderRadius: '6px',
                            color: '#ca8a04',
                            border: '1px solid rgba(234, 179, 8, 0.25)',
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '0.35rem',
                          }}
                        >
                          <Info size={12} style={{ flexShrink: 0, marginTop: '2px' }} />
                          <span>{item.preparation_instructions}</span>
                        </div>
                      )}
                    </div>

                    {/* Footer: Fee & Delete */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border)', paddingTop: '0.65rem' }}>
                      <div>
                        <div style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--primary, #3b82f6)' }}>
                          {feeText}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                          {isRange ? 'Estimated procedure range' : 'Fixed consultation fee'}
                        </div>
                      </div>

                      <button
                        onClick={() => handleDeleteTreatment(item.id)}
                        className="btn btn-secondary"
                        style={{
                          padding: '0.35rem 0.55rem',
                          borderRadius: '6px',
                          color: '#ef4444',
                        }}
                        title="Remove treatment"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: Paste Brochure / Fee Sheet */}
      {activeTab === 'paste' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ padding: '0.75rem 1rem', background: 'rgba(59, 130, 246, 0.08)', borderRadius: '8px', border: '1px solid rgba(59, 130, 246, 0.2)' }}>
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600, margin: '0 0 0.25rem 0', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Sparkles size={16} color="var(--primary, #3b82f6)" />
              Smart Brochure & Rate Sheet Extractor
            </h4>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
              Paste your clinic price sheet, fee brochure, or service list. Our heuristic extractor automatically detects procedure names, fees (fixed or ranges), doctor specialties, and duration.
            </p>
          </div>

          <div>
            <label style={{ fontSize: '0.85rem', fontWeight: 500, display: 'block', marginBottom: '0.35rem' }}>
              Paste Clinical Fee Sheet / Rate Brochure Text:
            </label>
            <textarea
              rows={8}
              value={pastedText}
              onChange={(e) => setPastedText(e.target.value)}
              placeholder={`Example:
--- Consultation & Diagnostics ---
Comprehensive Dental Examination & OPG X-Ray - ₹500 (30 mins)
Second Opinion Consultation - ₹800

--- Preventive & Hygiene ---
Ultrasonic Scaling & Polishing - ₹1200 - ₹1500 (45 mins)

--- Restorations ---
Single-Sitting Root Canal Therapy (RCT) - ₹4500 to ₹6500 (60 mins, Endodontist)
Zirconia Ceramic Crown - ₹6000 - ₹9000 (Prosthodontist)

--- Orthodontics & Cosmetic ---
Clear Invisible Aligners - ₹45000 to ₹75000 (Orthodontist)
Laser Teeth Whitening - ₹8000`}
              className="input"
              style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.85rem' }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Default Category:</span>
              <select
                value={pasteCategory}
                onChange={(e) => setPasteCategory(e.target.value)}
                className="input"
                style={{ fontSize: '0.85rem', width: 'auto' }}
              >
                {DEFAULT_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>

            <button
              onClick={handleParsePastedText}
              disabled={saving || !pastedText.trim()}
              className="btn btn-primary"
              style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}
            >
              <Sparkles size={15} />
              {saving ? 'Extracting...' : 'Extract & Preview Procedures'}
            </button>
          </div>

          {/* Parsed Preview Table */}
          {parsedPasteItems.length > 0 && (
            <div style={{ marginTop: '1rem', borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
              <h4 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                Extracted Procedures ({parsedPasteItems.length})
              </h4>

              <div style={{ maxHeight: '260px', overflowY: 'auto', border: '1px solid var(--border)', borderRadius: '8px' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead style={{ background: 'rgba(255, 255, 255, 0.04)', borderBottom: '1px solid var(--border)', textAlign: 'left' }}>
                    <tr>
                      <th style={{ padding: '0.5rem 0.75rem' }}>Procedure Name</th>
                      <th style={{ padding: '0.5rem 0.75rem' }}>Category</th>
                      <th style={{ padding: '0.5rem 0.75rem' }}>Fee</th>
                      <th style={{ padding: '0.5rem 0.75rem' }}>Duration</th>
                      <th style={{ padding: '0.5rem 0.75rem' }}>Specialist</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsedPasteItems.map((p, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td style={{ padding: '0.5rem 0.75rem', fontWeight: 500 }}>{p.name}</td>
                        <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)' }}>{p.category}</td>
                        <td style={{ padding: '0.5rem 0.75rem', color: 'var(--primary, #3b82f6)', fontWeight: 600 }}>
                          ₹{Math.round(p.base_fee).toLocaleString()}
                          {p.fee_range_max && p.fee_range_max > p.base_fee ? ` - ₹${Math.round(p.fee_range_max).toLocaleString()}` : ''}
                        </td>
                        <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)' }}>~{p.duration_minutes}m</td>
                        <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)' }}>{p.practitioner_type}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem' }}>
                <label style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={replaceOnPaste}
                    onChange={(e) => setReplaceOnPaste(e.target.checked)}
                  />
                  <span>Replace existing procedures (clear old fee store)</span>
                </label>

                <button
                  onClick={handleSaveParsedPaste}
                  disabled={saving}
                  className="btn btn-primary"
                  style={{ fontSize: '0.85rem' }}
                >
                  {saving ? 'Importing...' : `Import ${parsedPasteItems.length} Procedures to Fee Store`}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: Add Single Procedure */}
      {activeTab === 'add' && (
        <form onSubmit={handleAddSingleTreatment} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
            <div>
              <label style={{ fontSize: '0.85rem', fontWeight: 500, display: 'block', marginBottom: '0.35rem' }}>
                Procedure / Service Name *
              </label>
              <input
                type="text"
                required
                placeholder="e.g. Single-Sitting Root Canal Therapy"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="input"
                style={{ width: '100%', fontSize: '0.85rem' }}
              />
            </div>

            <div>
              <label style={{ fontSize: '0.85rem', fontWeight: 500, display: 'block', marginBottom: '0.35rem' }}>
                Category
              </label>
              <select
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                className="input"
                style={{ width: '100%', fontSize: '0.85rem' }}
              >
                {DEFAULT_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
            <div>
              <label style={{ fontSize: '0.85rem', fontWeight: 500, display: 'block', marginBottom: '0.35rem' }}>
                Base Fee (₹) *
              </label>
              <input
                type="number"
                required
                min="0"
                step="50"
                placeholder="e.g. 4500"
                value={newBaseFee}
                onChange={(e) => setNewBaseFee(e.target.value)}
                className="input"
                style={{ width: '100%', fontSize: '0.85rem' }}
              />
            </div>

            <div>
              <label style={{ fontSize: '0.85rem', fontWeight: 500, display: 'block', marginBottom: '0.35rem' }}>
                Fee Ceiling / Max Range (₹)
              </label>
              <input
                type="number"
                min="0"
                step="50"
                placeholder="e.g. 6500 (optional)"
                value={newFeeRangeMax}
                onChange={(e) => setNewFeeRangeMax(e.target.value)}
                className="input"
                style={{ width: '100%', fontSize: '0.85rem' }}
              />
            </div>

            <div>
              <label style={{ fontSize: '0.85rem', fontWeight: 500, display: 'block', marginBottom: '0.35rem' }}>
                Duration (minutes)
              </label>
              <input
                type="number"
                min="5"
                max="480"
                step="5"
                placeholder="30"
                value={newDuration}
                onChange={(e) => setNewDuration(e.target.value)}
                className="input"
                style={{ width: '100%', fontSize: '0.85rem' }}
              />
            </div>

            <div>
              <label style={{ fontSize: '0.85rem', fontWeight: 500, display: 'block', marginBottom: '0.35rem' }}>
                Practitioner / Specialist
              </label>
              <select
                value={newPractitioner}
                onChange={(e) => setNewPractitioner(e.target.value)}
                className="input"
                style={{ width: '100%', fontSize: '0.85rem' }}
              >
                {COMMON_PRACTITIONERS.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label style={{ fontSize: '0.85rem', fontWeight: 500, display: 'block', marginBottom: '0.35rem' }}>
              Procedure Description (Spoken to caller)
            </label>
            <input
              type="text"
              placeholder="e.g. Microscopic rotary root canal therapy with biocompatible obturation."
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              className="input"
              style={{ width: '100%', fontSize: '0.85rem' }}
            />
          </div>

          <div>
            <label style={{ fontSize: '0.85rem', fontWeight: 500, display: 'block', marginBottom: '0.35rem' }}>
              Patient Preparation Instructions
            </label>
            <input
              type="text"
              placeholder="e.g. Please take a light meal prior to appointment; avoid cold liquids after anesthesia."
              value={newPrep}
              onChange={(e) => setNewPrep(e.target.value)}
              className="input"
              style={{ width: '100%', fontSize: '0.85rem' }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setActiveTab('treatments')}
              className="btn btn-secondary"
              style={{ fontSize: '0.85rem' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="btn btn-primary"
              style={{ fontSize: '0.85rem' }}
            >
              {saving ? 'Saving...' : 'Add to Fee Store'}
            </button>
          </div>
        </form>
      )}

      {/* TAB 4: Upload CSV / JSON */}
      {activeTab === 'upload' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div
            style={{
              padding: '2rem 1rem',
              border: '2px dashed var(--border)',
              borderRadius: '12px',
              textAlign: 'center',
              background: 'rgba(255, 255, 255, 0.02)',
              cursor: 'pointer',
            }}
            onClick={() => document.getElementById('treatment-file-input')?.click()}
          >
            <UploadCloud size={36} color="var(--primary, #3b82f6)" style={{ marginBottom: '0.5rem' }} />
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: '0 0 0.25rem 0' }}>
              {selectedFile ? selectedFile.name : 'Select or drop CSV / JSON file'}
            </h4>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
              File should contain columns or keys: Name, Price/Fee, Category, Duration, Practitioner.
            </p>
            <input
              id="treatment-file-input"
              type="file"
              accept=".csv,.json"
              style={{ display: 'none' }}
              onChange={handleFileUpload}
            />
          </div>

          {fileParsedPreview.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                  Preview: {fileParsedPreview.length} procedures parsed
                </span>

                <label style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={replaceOnFile}
                    onChange={(e) => setReplaceOnFile(e.target.checked)}
                  />
                  <span>Replace existing fee store</span>
                </label>
              </div>

              <button
                onClick={handleSaveUploadedFile}
                disabled={saving}
                className="btn btn-primary"
                style={{ fontSize: '0.85rem', alignSelf: 'flex-end' }}
              >
                {saving ? 'Importing...' : `Import ${fileParsedPreview.length} Procedures to Fee Store`}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function TreatmentManagerModal({ business, isOpen, onClose, onTreatmentsUpdated }) {
  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(4px)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="card"
        style={{
          width: '100%',
          maxWidth: '920px',
          maxHeight: '90vh',
          overflowY: 'auto',
          background: 'var(--bg-card)',
          borderRadius: '12px',
          padding: '1.5rem',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.3)',
        }}
      >
        <TreatmentManagerView
          business={business}
          isEmbedded={false}
          onTreatmentsUpdated={onTreatmentsUpdated}
          onClose={onClose}
          defaultTab="treatments"
        />
      </div>
    </div>
  );
}

export default TreatmentManagerModal;
