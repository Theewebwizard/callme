import React, { useState, useEffect } from 'react';
import {
  Upload,
  FileText,
  ListPlus,
  Plus,
  Trash2,
  X,
  CheckCircle2,
  AlertCircle,
  Download,
  Search,
  Sparkles,
  Utensils,
  ArrowRight,
  RefreshCw,
} from 'lucide-react';
import { api } from '../api';

// Robust API client helpers with direct REST fallback
async function safeGetMenu(businessId, category = null) {
  if (api && typeof api.getMenu === 'function') {
    return api.getMenu(businessId, category);
  }
  const token = localStorage.getItem('callme_token');
  const q = category ? `?category=${encodeURIComponent(category)}` : '';
  const res = await fetch(`/api/businesses/${businessId}/menu${q}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Failed to load menu (HTTP ${res.status})`);
  return res.json();
}

async function safeUploadMenu(businessId, items, replace = false) {
  if (api && typeof api.uploadMenu === 'function') {
    return api.uploadMenu(businessId, items, replace);
  }
  const token = localStorage.getItem('callme_token');
  const res = await fetch(`/api/businesses/${businessId}/menu/upload`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ items, replace }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed (HTTP ${res.status})`);
  }
  return res.json();
}

async function safeDeleteMenuItem(businessId, itemId) {
  if (api && typeof api.deleteMenuItem === 'function') {
    return api.deleteMenuItem(businessId, itemId);
  }
  const token = localStorage.getItem('callme_token');
  const res = await fetch(`/api/businesses/${businessId}/menu/${itemId}`, {
    method: 'DELETE',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Failed to delete item (HTTP ${res.status})`);
  return res.json();
}

async function safeParseMenuText(businessId, text, defaultCategory = 'Mains') {
  if (api && typeof api.parseMenuText === 'function') {
    return api.parseMenuText(businessId, text, defaultCategory);
  }
  const token = localStorage.getItem('callme_token');
  const res = await fetch(`/api/businesses/${businessId}/menu/parse-text`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ text, default_category: defaultCategory }),
  });
  if (!res.ok) throw new Error(`Parsing failed (HTTP ${res.status})`);
  return res.json();
}

const DEFAULT_CATEGORIES = ['Starters', 'Mains', 'Breads', 'Desserts', 'Beverages'];

export function MenuManagerView({ business, isEmbedded = false, onMenuUpdated, onClose, defaultTab = 'upload' }) {
  const [activeTab, setActiveTab] = useState(defaultTab); // 'upload' | 'paste' | 'table'
  const [menuItems, setMenuItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState(null); // { type: 'success' | 'error', text: '' }

  // Option 1: File Upload state
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileParsedPreview, setFileParsedPreview] = useState([]);
  const [replaceOnUpload, setReplaceOnUpload] = useState(false);

  // Option 2: Paste Text state
  const [pastedText, setPastedText] = useState('');
  const [pasteCategory, setPasteCategory] = useState('Mains');
  const [parsedPasteItems, setParsedPasteItems] = useState([]);
  const [replaceOnPaste, setReplaceOnPaste] = useState(false);

  // Option 3: Single Dish Add form state
  const [newDishName, setNewDishName] = useState('');
  const [newDishCategory, setNewDishCategory] = useState('Mains');
  const [newDishPrice, setNewDishPrice] = useState('');
  const [newDishDesc, setNewDishDesc] = useState('');
  const [newDishDietary, setNewDishDietary] = useState('vegetarian');
  const [newDishSpice, setNewDishSpice] = useState('medium');
  const [searchFilter, setSearchFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('All');

  useEffect(() => {
    if (business?.id) {
      loadMenu();
    }
  }, [business?.id]);

  const loadMenu = async () => {
    if (!business?.id) return;
    setLoading(true);
    try {
      const res = await safeGetMenu(business.id);
      if (res && res.items) {
        setMenuItems(res.items);
      }
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to load menu: ${err.message}` });
    } finally {
      setLoading(false);
    }
  };

  // -------------------------------------------------------------
  // Option 1: File Upload Logic (CSV / JSON)
  // -------------------------------------------------------------
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    parseFile(file);
  };

  const parseFile = (file) => {
    const reader = new FileReader();
    reader.onload = async (evt) => {
      const content = evt.target?.result;
      if (!content || typeof content !== 'string') return;

      try {
        if (file.name.endsWith('.json')) {
          const parsed = JSON.parse(content);
          const items = Array.isArray(parsed) ? parsed : (parsed.items || []);
          setFileParsedPreview(items);
          setFeedback({ type: 'success', text: `Parsed ${items.length} dishes from JSON file.` });
        } else {
          // Parse CSV
          const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0);
          if (lines.length < 2) {
            setFeedback({ type: 'error', text: 'CSV file is empty or missing data rows.' });
            return;
          }

          const header = lines[0].split(',').map((h) => h.trim().toLowerCase().replace(/[^a-z_]/g, ''));
          const nameIdx = header.findIndex((h) => h.includes('name') || h.includes('dish') || h.includes('item'));
          const priceIdx = header.findIndex((h) => h.includes('price') || h.includes('cost') || h.includes('rate'));
          const catIdx = header.findIndex((h) => h.includes('category') || h.includes('type') || h.includes('section'));
          const descIdx = header.findIndex((h) => h.includes('desc'));
          const tagsIdx = header.findIndex((h) => h.includes('diet') || h.includes('tag'));

          if (nameIdx === -1 || priceIdx === -1) {
            setFeedback({ type: 'error', text: 'CSV must contain at least "name" and "price" columns.' });
            return;
          }

          const items = [];
          for (let i = 1; i < lines.length; i++) {
            const cols = lines[i].split(',').map((c) => c.trim().replace(/^["']|["']$/g, ''));
            const name = cols[nameIdx];
            const price = parseFloat(cols[priceIdx] || '0');
            if (!name || isNaN(price)) continue;

            const category = catIdx !== -1 && cols[catIdx] ? cols[catIdx] : 'Mains';
            const desc = descIdx !== -1 ? cols[descIdx] : '';
            const rawTags = tagsIdx !== -1 && cols[tagsIdx] ? cols[tagsIdx].split(';').map((t) => t.trim()) : ['vegetarian'];

            items.push({
              name,
              category,
              price,
              currency: 'INR',
              description: desc || null,
              dietary_tags: rawTags,
              spice_level: 'medium',
              is_available: true,
            });
          }

          setFileParsedPreview(items);
          setFeedback({ type: 'success', text: `Parsed ${items.length} dishes from CSV file.` });
        }
      } catch (err) {
        setFeedback({ type: 'error', text: `Failed to read file: ${err.message}` });
      }
    };
    reader.readAsText(file);
  };

  const handleSaveFileItems = async () => {
    if (!fileParsedPreview.length) return;
    setSaving(true);
    try {
      const res = await safeUploadMenu(business.id, fileParsedPreview, replaceOnUpload);
      setFeedback({ type: 'success', text: `Successfully saved ${res.count} dishes to your menu!` });
      setSelectedFile(null);
      setFileParsedPreview([]);
      await loadMenu();
      if (onMenuUpdated) onMenuUpdated();
      setActiveTab('table');
    } catch (err) {
      setFeedback({ type: 'error', text: `Upload failed: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  const handleDownloadSampleCsv = () => {
    const csvContent =
      'name,category,price,description,dietary_tags,spice_level\n' +
      'Paneer Tikka Angaare,Starters,320,Charcoal grilled cottage cheese,vegetarian;gluten-free,spicy\n' +
      'Dal Makhani,Mains,280,Slow cooked black lentils with farm butter,vegetarian;gluten-free,mild\n' +
      'Butter Naan,Breads,60,Tandoor baked leavened bread,vegetarian,mild\n' +
      'Gulab Jamun (2 pcs),Desserts,90,Caramelized milk dumplings in cardamom syrup,vegetarian,mild\n' +
      'Mango Lassi,Beverages,120,Thick mango yogurt smoothie,vegetarian;gluten-free,mild\n';

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'callme_menu_template.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // -------------------------------------------------------------
  // Option 2: Paste Raw Text Logic
  // -------------------------------------------------------------
  const handleParsePastedText = async () => {
    if (!pastedText.trim()) {
      setFeedback({ type: 'error', text: 'Please paste menu text first.' });
      return;
    }
    setSaving(true);
    try {
      const res = await safeParseMenuText(business.id, pastedText, pasteCategory);
      if (res && res.items) {
        setParsedPasteItems(res.items);
        setFeedback({
          type: 'success',
          text: `AI detected ${res.count} dishes with prices and categories! Review below and click Save.`,
        });
      }
    } catch (err) {
      setFeedback({ type: 'error', text: `Parsing failed: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  const handleSavePastedItems = async () => {
    if (!parsedPasteItems.length) return;
    setSaving(true);
    try {
      const res = await safeUploadMenu(business.id, parsedPasteItems, replaceOnPaste);
      setFeedback({ type: 'success', text: `Successfully saved ${res.count} dishes to your menu!` });
      setPastedText('');
      setParsedPasteItems([]);
      await loadMenu();
      if (onMenuUpdated) onMenuUpdated();
      setActiveTab('table');
    } catch (err) {
      setFeedback({ type: 'error', text: `Save failed: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  // -------------------------------------------------------------
  // Option 3: Single Dish Add / Delete Logic
  // -------------------------------------------------------------
  const handleAddSingleDish = async (e) => {
    e.preventDefault();
    if (!newDishName.trim()) {
      setFeedback({ type: 'error', text: 'Dish name is required.' });
      return;
    }
    const priceNum = parseFloat(newDishPrice);
    if (isNaN(priceNum) || priceNum < 0) {
      setFeedback({ type: 'error', text: 'Valid numeric price is required.' });
      return;
    }

    const dishPayload = {
      name: newDishName.trim(),
      category: newDishCategory,
      price: priceNum,
      currency: 'INR',
      description: newDishDesc.trim() || null,
      dietary_tags: [newDishDietary],
      spice_level: newDishSpice,
      is_available: true,
    };

    setSaving(true);
    try {
      await safeUploadMenu(business.id, [dishPayload], false); // append
      setFeedback({ type: 'success', text: `Added "${newDishName}" to menu!` });
      setNewDishName('');
      setNewDishPrice('');
      setNewDishDesc('');
      await loadMenu();
      if (onMenuUpdated) onMenuUpdated();
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to add dish: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteDish = async (itemId, dishName) => {
    if (!window.confirm(`Delete "${dishName}" from your menu?`)) return;
    try {
      await safeDeleteMenuItem(business.id, itemId);
      setFeedback({ type: 'success', text: `Deleted "${dishName}".` });
      setMenuItems((prev) => prev.filter((i) => i.id !== itemId));
      if (onMenuUpdated) onMenuUpdated();
    } catch (err) {
      setFeedback({ type: 'error', text: `Delete failed: ${err.message}` });
    }
  };

  // Filtered menu for table view
  const filteredDishes = menuItems.filter((item) => {
    const matchesSearch =
      !searchFilter.trim() ||
      item.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
      (item.description || '').toLowerCase().includes(searchFilter.toLowerCase());
    const matchesCategory =
      categoryFilter === 'All' ||
      item.category.toLowerCase() === categoryFilter.toLowerCase();
    return matchesSearch && matchesCategory;
  });

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        background: 'white',
        borderRadius: isEmbedded ? '10px' : '0',
        border: isEmbedded ? '1px solid var(--slate-200, #e2e8f0)' : 'none',
        overflow: 'hidden',
      }}
    >
      {/* Sub-header Bar (Always visible) */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '0.75rem 1rem',
          background: 'var(--slate-50, #f8fafc)',
          borderBottom: '1px solid var(--slate-200, #e2e8f0)',
          flexWrap: 'wrap',
          gap: '8px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--slate-600, #475569)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Menu Upload & Management
          </span>
          <span
            style={{
              fontSize: '0.72rem',
              background: 'var(--sky-100, #e0f2fe)',
              color: 'var(--sky-700, #0369a1)',
              padding: '2px 8px',
              borderRadius: '10px',
              fontWeight: 700,
            }}
          >
            {menuItems.length} Dishes Active
          </span>
        </div>

        <button
          type="button"
          onClick={loadMenu}
          disabled={loading}
          style={{
            background: 'none',
            border: '1px solid var(--slate-300, #cbd5e1)',
            borderRadius: '6px',
            padding: '3px 8px',
            fontSize: '0.72rem',
            color: 'var(--slate-600, #475569)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          <RefreshCw size={11} className={loading ? 'spin' : ''} />
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* 3 Upload Options Selection Bar - Large Prominent Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: '8px',
          padding: '0.85rem 1rem',
          background: 'var(--slate-50, #f8fafc)',
          borderBottom: '1px solid var(--slate-200, #e2e8f0)',
        }}
      >
        {/* Option 1: File Upload */}
        <button
          type="button"
          onClick={() => setActiveTab('upload')}
          style={{
            padding: '10px 12px',
            borderRadius: '8px',
            border: activeTab === 'upload' ? '2px solid var(--sky-500, #0ea5e9)' : '1px solid var(--slate-200, #e2e8f0)',
            background: activeTab === 'upload' ? 'var(--sky-50, #f0f9ff)' : 'white',
            cursor: 'pointer',
            textAlign: 'left',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            boxShadow: activeTab === 'upload' ? '0 2px 6px rgba(14, 165, 233, 0.15)' : 'none',
            transition: 'all 0.15s ease',
          }}
        >
          <div
            style={{
              width: '34px',
              height: '34px',
              borderRadius: '6px',
              background: activeTab === 'upload' ? 'var(--sky-500, #0ea5e9)' : 'var(--slate-100, #f1f5f9)',
              color: activeTab === 'upload' ? 'white' : 'var(--slate-600, #475569)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Upload size={17} />
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: '0.84rem', color: activeTab === 'upload' ? 'var(--sky-900, #0c4a6e)' : 'var(--slate-800, #1e293b)' }}>
              1. File Upload (CSV/JSON)
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--slate-500, #64748b)', marginTop: '1px' }}>
              Upload spreadsheet file
            </div>
          </div>
        </button>

        {/* Option 2: Paste Raw Text */}
        <button
          type="button"
          onClick={() => setActiveTab('paste')}
          style={{
            padding: '10px 12px',
            borderRadius: '8px',
            border: activeTab === 'paste' ? '2px solid var(--sky-500, #0ea5e9)' : '1px solid var(--slate-200, #e2e8f0)',
            background: activeTab === 'paste' ? 'var(--sky-50, #f0f9ff)' : 'white',
            cursor: 'pointer',
            textAlign: 'left',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            boxShadow: activeTab === 'paste' ? '0 2px 6px rgba(14, 165, 233, 0.15)' : 'none',
            transition: 'all 0.15s ease',
          }}
        >
          <div
            style={{
              width: '34px',
              height: '34px',
              borderRadius: '6px',
              background: activeTab === 'paste' ? 'var(--sky-500, #0ea5e9)' : 'var(--slate-100, #f1f5f9)',
              color: activeTab === 'paste' ? 'white' : 'var(--slate-600, #475569)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <FileText size={17} />
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: '0.84rem', color: activeTab === 'paste' ? 'var(--sky-900, #0c4a6e)' : 'var(--slate-800, #1e293b)' }}>
              2. Paste Menu Text (AI)
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--slate-500, #64748b)', marginTop: '1px' }}>
              Auto-detect dishes & prices
            </div>
          </div>
        </button>

        {/* Option 3: Dish Inventory Table */}
        <button
          type="button"
          onClick={() => setActiveTab('table')}
          style={{
            padding: '10px 12px',
            borderRadius: '8px',
            border: activeTab === 'table' ? '2px solid var(--sky-500, #0ea5e9)' : '1px solid var(--slate-200, #e2e8f0)',
            background: activeTab === 'table' ? 'var(--sky-50, #f0f9ff)' : 'white',
            cursor: 'pointer',
            textAlign: 'left',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            boxShadow: activeTab === 'table' ? '0 2px 6px rgba(14, 165, 233, 0.15)' : 'none',
            transition: 'all 0.15s ease',
          }}
        >
          <div
            style={{
              width: '34px',
              height: '34px',
              borderRadius: '6px',
              background: activeTab === 'table' ? 'var(--sky-500, #0ea5e9)' : 'var(--slate-100, #f1f5f9)',
              color: activeTab === 'table' ? 'white' : 'var(--slate-600, #475569)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <ListPlus size={17} />
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: '0.84rem', color: activeTab === 'table' ? 'var(--sky-900, #0c4a6e)' : 'var(--slate-800, #1e293b)' }}>
              3. View & Add Dishes ({menuItems.length})
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--slate-500, #64748b)', marginTop: '1px' }}>
              Browse & edit {menuItems.length} items
            </div>
          </div>
        </button>
      </div>

      {/* Feedback Alert */}
      {feedback && (
        <div
          style={{
            margin: '0.75rem 1rem 0',
            padding: '0.65rem 1rem',
            borderRadius: '6px',
            fontSize: '0.82rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: feedback.type === 'error' ? '#fef2f2' : '#f0fdf4',
            color: feedback.type === 'error' ? '#b91c1c' : '#15803d',
            border: `1px solid ${feedback.type === 'error' ? '#fecaca' : '#bbf7d0'}`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {feedback.type === 'error' ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
            <span>{feedback.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}
          >
            ×
          </button>
        </div>
      )}

      {/* Tab Body */}
      <div style={{ padding: '1rem', overflowY: 'auto', flex: 1, maxHeight: isEmbedded ? '500px' : 'none' }}>
        {/* ========================================================= */}
        {/* OPTION 1: INTERACTIVE TABLE & ADD SINGLE DISH             */}
        {/* ========================================================= */}
        {activeTab === 'table' && (
          <div>
            {/* Quick Jump Callout */}
            <div style={{
              background: 'var(--sky-50, #f0f9ff)',
              border: '1px solid var(--sky-200, #bae6fd)',
              borderRadius: '8px',
              padding: '0.65rem 1rem',
              marginBottom: '1rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '8px',
            }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--sky-900, #0c4a6e)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Sparkles size={15} color="var(--sky-600, #0284c7)" />
                Want to bulk upload your menu at once?
              </div>
              <div style={{ display: 'flex', gap: '6px' }}>
                <button
                  type="button"
                  onClick={() => setActiveTab('upload')}
                  style={{
                    padding: '4px 10px',
                    fontSize: '0.74rem',
                    fontWeight: 700,
                    background: 'var(--sky-500, #0ea5e9)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '5px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  <Upload size={12} /> 📁 Upload CSV / JSON
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('paste')}
                  style={{
                    padding: '4px 10px',
                    fontSize: '0.74rem',
                    fontWeight: 700,
                    background: 'white',
                    color: 'var(--sky-700, #0369a1)',
                    border: '1px solid var(--sky-300, #7dd3fc)',
                    borderRadius: '5px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  <FileText size={12} /> 📝 Paste Raw Text
                </button>
              </div>
            </div>

            {/* Quick Add Dish Form */}
            <form
              onSubmit={handleAddSingleDish}
              style={{
                background: 'var(--slate-50, #f8fafc)',
                padding: '0.85rem',
                borderRadius: '8px',
                border: '1px solid var(--slate-200, #e2e8f0)',
                marginBottom: '1rem',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--slate-800, #1e293b)', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Plus size={14} color="var(--sky-600, #0284c7)" /> Add Single Dish to Menu
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px', marginBottom: '8px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, color: 'var(--slate-600, #475569)', marginBottom: '2px' }}>
                    Dish Name *
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Malai Kofta"
                    value={newDishName}
                    onChange={(e) => setNewDishName(e.target.value)}
                    required
                    style={{ width: '100%', padding: '6px 8px', fontSize: '0.8rem', borderRadius: '4px', border: '1px solid var(--slate-300, #cbd5e1)', boxSizing: 'border-box' }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, color: 'var(--slate-600, #475569)', marginBottom: '2px' }}>
                    Category
                  </label>
                  <select
                    value={newDishCategory}
                    onChange={(e) => setNewDishCategory(e.target.value)}
                    style={{ width: '100%', padding: '6px 8px', fontSize: '0.8rem', borderRadius: '4px', border: '1px solid var(--slate-300, #cbd5e1)', boxSizing: 'border-box', background: 'white' }}
                  >
                    {DEFAULT_CATEGORIES.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, color: 'var(--slate-600, #475569)', marginBottom: '2px' }}>
                    Price (₹) *
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="280"
                    value={newDishPrice}
                    onChange={(e) => setNewDishPrice(e.target.value)}
                    required
                    style={{ width: '100%', padding: '6px 8px', fontSize: '0.8rem', borderRadius: '4px', border: '1px solid var(--slate-300, #cbd5e1)', boxSizing: 'border-box' }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, color: 'var(--slate-600, #475569)', marginBottom: '2px' }}>
                    Dietary
                  </label>
                  <select
                    value={newDishDietary}
                    onChange={(e) => setNewDishDietary(e.target.value)}
                    style={{ width: '100%', padding: '6px 8px', fontSize: '0.8rem', borderRadius: '4px', border: '1px solid var(--slate-300, #cbd5e1)', boxSizing: 'border-box', background: 'white' }}
                  >
                    <option value="vegetarian">Vegetarian</option>
                    <option value="non-vegetarian">Non-Vegetarian</option>
                    <option value="vegan">Vegan</option>
                    <option value="jain-friendly">Jain-Friendly</option>
                    <option value="gluten-free">Gluten-Free</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, color: 'var(--slate-600, #475569)', marginBottom: '2px' }}>
                    Spice Level
                  </label>
                  <select
                    value={newDishSpice}
                    onChange={(e) => setNewDishSpice(e.target.value)}
                    style={{ width: '100%', padding: '6px 8px', fontSize: '0.8rem', borderRadius: '4px', border: '1px solid var(--slate-300, #cbd5e1)', boxSizing: 'border-box', background: 'white' }}
                  >
                    <option value="mild">Mild</option>
                    <option value="medium">Medium</option>
                    <option value="spicy">Spicy</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input
                  type="text"
                  placeholder="Optional ingredients or description (e.g. Cottage cheese dumplings in rich cashew gravy)"
                  value={newDishDesc}
                  onChange={(e) => setNewDishDesc(e.target.value)}
                  style={{ flex: 1, padding: '6px 8px', fontSize: '0.8rem', borderRadius: '4px', border: '1px solid var(--slate-300, #cbd5e1)', boxSizing: 'border-box' }}
                />
                <button
                  type="submit"
                  disabled={saving}
                  style={{
                    padding: '6px 14px',
                    background: 'var(--sky-500, #0ea5e9)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {saving ? 'Adding...' : '+ Add Dish'}
                </button>
              </div>
            </form>

            {/* Dish Filters and Search */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', gap: '8px', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                {['All', ...DEFAULT_CATEGORIES].map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setCategoryFilter(cat)}
                    style={{
                      padding: '3px 8px',
                      fontSize: '0.72rem',
                      borderRadius: '12px',
                      border: categoryFilter === cat ? '1px solid var(--sky-500, #0ea5e9)' : '1px solid var(--slate-200, #e2e8f0)',
                      background: categoryFilter === cat ? 'var(--sky-100, #e0f2fe)' : 'white',
                      color: categoryFilter === cat ? 'var(--sky-700, #0369a1)' : 'var(--slate-600, #475569)',
                      fontWeight: categoryFilter === cat ? 700 : 500,
                      cursor: 'pointer',
                    }}
                  >
                    {cat}
                  </button>
                ))}
              </div>

              <div style={{ position: 'relative', minWidth: '180px' }}>
                <Search size={13} style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)', color: 'var(--slate-400, #94a3b8)' }} />
                <input
                  type="text"
                  placeholder="Filter dishes..."
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '4px 8px 4px 26px',
                    fontSize: '0.75rem',
                    borderRadius: '4px',
                    border: '1px solid var(--slate-300, #cbd5e1)',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            </div>

            {/* Dish Table */}
            {filteredDishes.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem 1rem', background: 'var(--slate-50, #f8fafc)', borderRadius: '8px', color: 'var(--slate-500, #64748b)', fontSize: '0.82rem' }}>
                {menuItems.length === 0
                  ? 'No dishes configured yet. Use Option 1 above to add a dish, or switch to Option 2 (Upload File) / Option 3 (Paste Text).'
                  : 'No dishes match the selected category or search filter.'}
              </div>
            ) : (
              <div style={{ maxHeight: '280px', overflowY: 'auto', border: '1px solid var(--slate-200, #e2e8f0)', borderRadius: '8px' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                  <thead style={{ background: 'var(--slate-100, #f1f5f9)', position: 'sticky', top: 0, zIndex: 1 }}>
                    <tr style={{ textAlign: 'left', color: 'var(--slate-700, #334155)' }}>
                      <th style={{ padding: '8px 10px' }}>Dish Name</th>
                      <th style={{ padding: '8px 10px' }}>Category</th>
                      <th style={{ padding: '8px 10px', textAlign: 'right' }}>Price</th>
                      <th style={{ padding: '8px 10px' }}>Dietary & Spice</th>
                      <th style={{ padding: '8px 10px', textAlign: 'center', width: '40px' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredDishes.map((dish) => (
                      <tr key={dish.id} style={{ borderBottom: '1px solid var(--slate-100, #f1f5f9)' }}>
                        <td style={{ padding: '8px 10px' }}>
                          <div style={{ fontWeight: 700, color: 'var(--slate-800, #1e293b)' }}>{dish.name}</div>
                          {dish.description && (
                            <div style={{ fontSize: '0.72rem', color: 'var(--slate-500, #64748b)' }}>{dish.description}</div>
                          )}
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          <span style={{ fontSize: '0.72rem', background: 'var(--slate-100, #f1f5f9)', color: 'var(--slate-700, #334155)', padding: '2px 8px', borderRadius: '4px', fontWeight: 600 }}>
                            {dish.category}
                          </span>
                        </td>
                        <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 700, color: 'var(--emerald-700, #047857)' }}>
                          ₹{dish.price}
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                            {(dish.dietary_tags || []).map((t, idx) => (
                              <span key={idx} style={{ fontSize: '0.68rem', background: t.includes('non') ? '#fee2e2' : '#dcfce7', color: t.includes('non') ? '#b91c1c' : '#15803d', padding: '1px 6px', borderRadius: '4px', fontWeight: 600 }}>
                                {t}
                              </span>
                            ))}
                            {dish.spice_level && (
                              <span style={{ fontSize: '0.68rem', background: '#fef3c7', color: '#b45309', padding: '1px 6px', borderRadius: '4px' }}>
                                {dish.spice_level}
                              </span>
                            )}
                          </div>
                        </td>
                        <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                          <button
                            type="button"
                            onClick={() => handleDeleteDish(dish.id, dish.name)}
                            title="Delete dish"
                            style={{
                              background: 'none',
                              border: 'none',
                              color: '#ef4444',
                              cursor: 'pointer',
                              padding: '4px',
                            }}
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ========================================================= */}
        {/* OPTION 2: FILE UPLOAD (CSV / JSON)                        */}
        {/* ========================================================= */}
        {activeTab === 'upload' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '8px' }}>
              <div>
                <h4 style={{ fontSize: '0.92rem', fontWeight: 700, color: 'var(--slate-800, #1e293b)', margin: '0 0 2px' }}>
                  Upload Menu Spreadsheet (CSV or JSON)
                </h4>
                <p style={{ fontSize: '0.78rem', color: 'var(--slate-500, #64748b)', margin: 0 }}>
                  Upload a spreadsheet file containing dish names, categories, and prices.
                </p>
              </div>
              <button
                type="button"
                onClick={handleDownloadSampleCsv}
                style={{
                  padding: '5px 10px',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  border: '1px solid var(--slate-300, #cbd5e1)',
                  background: 'white',
                  borderRadius: '6px',
                  color: 'var(--slate-700, #334155)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <Download size={13} />
                Download Sample CSV
              </button>
            </div>

            {/* Drag and Drop Zone */}
            <div
              style={{
                border: '2px dashed var(--sky-300, #7dd3fc)',
                background: 'var(--sky-50, #f0f9ff)',
                borderRadius: '8px',
                padding: '1.5rem 1rem',
                textAlign: 'center',
                cursor: 'pointer',
                position: 'relative',
                marginBottom: '0.75rem',
              }}
            >
              <input
                type="file"
                accept=".csv,.json,.txt"
                onChange={handleFileChange}
                style={{
                  position: 'absolute',
                  inset: 0,
                  opacity: 0,
                  cursor: 'pointer',
                  width: '100%',
                  height: '100%',
                }}
              />
              <Upload size={28} color="var(--sky-600, #0284c7)" style={{ margin: '0 auto 6px' }} />
              <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--slate-800, #1e293b)' }}>
                {selectedFile ? selectedFile.name : 'Click to select or drag & drop menu CSV/JSON file'}
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--slate-500, #64748b)', marginTop: '2px' }}>
                Columns: name, category, price, description, dietary_tags, spice_level
              </div>
            </div>

            {/* Upload Mode Options */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '0.75rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem', color: 'var(--slate-700, #334155)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={replaceOnUpload}
                  onChange={(e) => setReplaceOnUpload(e.target.checked)}
                />
                <span><strong>Replace existing menu entirely</strong> (uncheck to append dishes)</span>
              </label>
            </div>

            {/* Parsed Preview Table */}
            {fileParsedPreview.length > 0 && (
              <div style={{ marginTop: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--slate-800, #1e293b)' }}>
                    Preview: {fileParsedPreview.length} dishes parsed
                  </div>
                  <button
                    type="button"
                    onClick={handleSaveFileItems}
                    disabled={saving}
                    style={{
                      padding: '5px 14px',
                      background: 'var(--sky-500, #0ea5e9)',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    {saving ? 'Saving...' : `Save All ${fileParsedPreview.length} Dishes →`}
                  </button>
                </div>

                <div style={{ maxHeight: '180px', overflowY: 'auto', border: '1px solid var(--slate-200, #e2e8f0)', borderRadius: '6px' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
                    <thead style={{ background: 'var(--slate-100, #f1f5f9)', position: 'sticky', top: 0 }}>
                      <tr>
                        <th style={{ padding: '6px 8px', textAlign: 'left' }}>Dish Name</th>
                        <th style={{ padding: '6px 8px', textAlign: 'left' }}>Category</th>
                        <th style={{ padding: '6px 8px', textAlign: 'right' }}>Price</th>
                        <th style={{ padding: '6px 8px', textAlign: 'left' }}>Tags</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fileParsedPreview.map((item, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid var(--slate-100, #f1f5f9)' }}>
                          <td style={{ padding: '6px 8px', fontWeight: 600 }}>{item.name}</td>
                          <td style={{ padding: '6px 8px', color: 'var(--slate-600, #475569)' }}>{item.category}</td>
                          <td style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 700 }}>₹{item.price}</td>
                          <td style={{ padding: '6px 8px', fontSize: '0.7rem', color: 'var(--slate-500, #64748b)' }}>
                            {(item.dietary_tags || []).join(', ')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ========================================================= */}
        {/* OPTION 3: PASTE RAW MENU TEXT                             */}
        {/* ========================================================= */}
        {activeTab === 'paste' && (
          <div>
            <div style={{ marginBottom: '0.75rem' }}>
              <h4 style={{ fontSize: '0.92rem', fontWeight: 700, color: 'var(--slate-800, #1e293b)', margin: '0 0 2px' }}>
                Paste Raw Menu Text or WhatsApp Message
              </h4>
              <p style={{ fontSize: '0.78rem', color: 'var(--slate-500, #64748b)', margin: 0 }}>
                Paste your menu directly. The parser automatically detects dish names, categories, and prices.
              </p>
            </div>

            <div style={{ marginBottom: '0.5rem' }}>
              <textarea
                rows={5}
                value={pastedText}
                onChange={(e) => setPastedText(e.target.value)}
                placeholder={`Example:\nStarters:\nPaneer Tikka - ₹320 (Charcoal grilled)\nCrispy Corn - 240\n\nMains:\nDal Makhani - 280\nButter Chicken - 420\nPaneer Butter Masala - 340\n\nBreads:\nButter Naan - 60\nTandoori Roti - 35\n\nDesserts:\nGulab Jamun - 90\nRasmalai - 130`}
                style={{
                  width: '100%',
                  padding: '0.65rem',
                  borderRadius: '6px',
                  border: '1px solid var(--slate-300, #cbd5e1)',
                  fontSize: '0.8rem',
                  fontFamily: 'monospace',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '8px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem', color: 'var(--slate-700, #334155)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={replaceOnPaste}
                  onChange={(e) => setReplaceOnPaste(e.target.checked)}
                />
                <span>Replace existing menu with these items</span>
              </label>

              <button
                type="button"
                onClick={handleParsePastedText}
                disabled={saving || !pastedText.trim()}
                style={{
                  padding: '6px 14px',
                  background: 'var(--sky-500, #0ea5e9)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <Sparkles size={13} />
                {saving ? 'Detecting Dishes...' : 'Auto-Detect Dishes & Prices'}
              </button>
            </div>

            {/* Parsed Paste Preview */}
            {parsedPasteItems.length > 0 && (
              <div style={{ border: '1px solid var(--slate-200, #e2e8f0)', borderRadius: '8px', padding: '0.75rem', background: 'var(--slate-50, #f8fafc)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <div style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--slate-800, #1e293b)' }}>
                    Detected {parsedPasteItems.length} Dishes
                  </div>
                  <button
                    type="button"
                    onClick={handleSavePastedItems}
                    disabled={saving}
                    style={{
                      padding: '5px 14px',
                      background: 'var(--emerald-600, #059669)',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    {saving ? 'Saving...' : `Save ${parsedPasteItems.length} Dishes to Menu`}
                  </button>
                </div>

                <div style={{ maxHeight: '180px', overflowY: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--slate-200, #e2e8f0)', textAlign: 'left', color: 'var(--slate-600, #475569)' }}>
                        <th style={{ padding: '6px' }}>Dish Name</th>
                        <th style={{ padding: '6px' }}>Category</th>
                        <th style={{ padding: '6px', textAlign: 'right' }}>Price</th>
                        <th style={{ padding: '6px' }}>Tags</th>
                      </tr>
                    </thead>
                    <tbody>
                      {parsedPasteItems.map((item, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid var(--slate-200, #e2e8f0)' }}>
                          <td style={{ padding: '6px', fontWeight: 600 }}>{item.name}</td>
                          <td style={{ padding: '6px' }}>
                            <span style={{ background: 'var(--slate-200, #e2e8f0)', padding: '2px 6px', borderRadius: '4px', fontSize: '0.7rem' }}>
                              {item.category}
                            </span>
                          </td>
                          <td style={{ padding: '6px', textAlign: 'right', fontWeight: 700 }}>₹{item.price}</td>
                          <td style={{ padding: '6px', fontSize: '0.7rem', color: 'var(--slate-500, #64748b)' }}>
                            {(item.dietary_tags || []).join(', ')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function MenuManagerModal({ business, isOpen, onClose, onMenuUpdated }) {
  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.65)',
        backdropFilter: 'blur(5px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1100,
        padding: '1rem',
      }}
    >
      <div
        style={{
          background: 'white',
          borderRadius: 'var(--radius-lg, 12px)',
          maxWidth: '880px',
          width: '100%',
          maxHeight: '92vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.3)',
          overflow: 'hidden',
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '1.25rem 1.5rem',
            borderBottom: '1px solid var(--slate-200, #e2e8f0)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'var(--slate-50, #f8fafc)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                background: 'var(--sky-500, #0ea5e9)',
                color: 'white',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Utensils size={20} />
            </div>
            <div>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--sky-600, #0284c7)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Restaurant Menu & Semantic Pricing
              </div>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--slate-900, #0f172a)', margin: 0 }}>
                {business?.name || 'Restaurant'} Menu
              </h2>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--slate-400, #94a3b8)',
              cursor: 'pointer',
              padding: '4px',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <MenuManagerView
            business={business}
            isEmbedded={false}
            onMenuUpdated={onMenuUpdated}
            onClose={onClose}
          />
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '1rem 1.5rem',
            borderTop: '1px solid var(--slate-200, #e2e8f0)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'var(--slate-50, #f8fafc)',
          }}
        >
          <div style={{ fontSize: '0.78rem', color: 'var(--slate-500, #64748b)' }}>
            Changes are saved live to your restaurant database. Your AI receptionist uses these immediately.
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '6px 16px',
              background: 'var(--slate-800, #1e293b)',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontSize: '0.8rem',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

export default MenuManagerModal;
