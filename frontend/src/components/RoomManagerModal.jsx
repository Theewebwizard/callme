import React, { useState, useEffect } from 'react';
import {
  Bed,
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
  DollarSign,
  Users,
  CheckCircle2,
  Calendar,
  ShieldCheck,
  Coffee,
  Waves,
} from 'lucide-react';
import { api } from '../api';

const DEFAULT_ROOM_CATEGORIES = ['Rooms', 'Suites', 'Villas', 'Penthouses', 'Cottages'];

const COMMON_AMENITIES = [
  'Ocean View',
  'Garden View',
  'Private Balcony',
  'Bathtub',
  'Private Pool',
  'High-Speed Wi-Fi',
  'Mini-bar',
  'Work Desk',
  'Walk-in Wardrobe',
  'Espresso Machine',
];

const COMMON_INCLUSIONS = [
  'Complimentary Buffet Breakfast',
  'Roundtrip Airport Transfer',
  'Pool & Fitness Center Access',
  'Executive Lounge Access',
  'Spa Sanctuary Credit',
  'Evening Sunset Cocktails',
];

export function RoomManagerView({
  business,
  isEmbedded = false,
  onRoomsUpdated,
  onClose,
  defaultTab = 'rooms',
}) {
  const [activeTab, setActiveTab] = useState(defaultTab); // 'rooms' | 'paste' | 'upload' | 'add'
  const [rooms, setRooms] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState(null); // { type: 'success' | 'error', text: '' }

  // Option 1: Paste Brochure / Rate Sheet
  const [pastedText, setPastedText] = useState('');
  const [pasteCategory, setPasteCategory] = useState('Rooms');
  const [parsedPasteRooms, setParsedPasteRooms] = useState([]);
  const [replaceOnPaste, setReplaceOnPaste] = useState(false);

  // Option 2: File Upload (JSON / CSV)
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileParsedPreview, setFileParsedPreview] = useState([]);
  const [replaceOnFile, setReplaceOnFile] = useState(false);

  // Option 3: Single Room Add
  const [newRoomName, setNewRoomName] = useState('');
  const [newRoomCategory, setNewRoomCategory] = useState('Rooms');
  const [newRoomPrice, setNewRoomPrice] = useState('');
  const [newRoomWeekendPrice, setNewRoomWeekendPrice] = useState('');
  const [newRoomBed, setNewRoomBed] = useState('1 King Bed');
  const [newRoomOccupancy, setNewRoomOccupancy] = useState('2');
  const [newRoomDesc, setNewRoomDesc] = useState('');
  const [selectedAmenities, setSelectedAmenities] = useState(['High-Speed Wi-Fi']);
  const [selectedInclusions, setSelectedInclusions] = useState(['Complimentary Buffet Breakfast']);

  // Filters
  const [searchFilter, setSearchFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('All');

  useEffect(() => {
    if (business?.id) {
      loadRooms();
    }
  }, [business?.id]);

  const loadRooms = async () => {
    if (!business?.id) return;
    setLoading(true);
    try {
      const res = await api.getRooms(business.id);
      if (res && res.items) {
        setRooms(res.items);
      }
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to load room catalog: ${err.message}` });
    } finally {
      setLoading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Action Handlers
  // ---------------------------------------------------------------------------
  const handleParseText = async () => {
    if (!pastedText.trim() || !business?.id) return;
    setSaving(true);
    setFeedback(null);
    try {
      const res = await api.parseRoomText(business.id, pastedText, pasteCategory);
      if (res && res.items && res.items.length > 0) {
        setParsedPasteRooms(res.items);
        setFeedback({
          type: 'success',
          text: `Auto-extracted ${res.items.length} room tiers with nightly rates and features.`,
        });
      } else {
        setFeedback({
          type: 'error',
          text: 'Could not extract room rates from the text. Make sure prices (e.g. ₹6,500/night or $180) are visible.',
        });
      }
    } catch (err) {
      setFeedback({ type: 'error', text: `Extraction failed: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  const handleSaveParsedRooms = async () => {
    if (!parsedPasteRooms.length || !business?.id) return;
    setSaving(true);
    setFeedback(null);
    try {
      const res = await api.uploadRooms(business.id, parsedPasteRooms, replaceOnPaste);
      setFeedback({
        type: 'success',
        text: `Successfully saved ${res.items.length} room types to your rate card!`,
      });
      setParsedPasteRooms([]);
      setPastedText('');
      await loadRooms();
      setActiveTab('rooms');
      if (onRoomsUpdated) onRoomsUpdated();
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to save rooms: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    const reader = new FileReader();
    reader.onload = async (evt) => {
      const content = evt.target?.result;
      if (!content || typeof content !== 'string') return;
      try {
        if (file.name.endsWith('.json')) {
          const parsed = JSON.parse(content);
          const items = Array.isArray(parsed) ? parsed : parsed.items || [];
          setFileParsedPreview(items);
          setFeedback({ type: 'success', text: `Parsed ${items.length} room tiers from JSON.` });
        } else {
          // Parse CSV
          const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0);
          if (lines.length < 2) {
            setFeedback({ type: 'error', text: 'CSV file is empty or missing data rows.' });
            return;
          }
          const header = lines[0].split(',').map((h) => h.trim().toLowerCase().replace(/[^a-z_]/g, ''));
          const nameIdx = header.findIndex((h) => h.includes('name') || h.includes('room'));
          const priceIdx = header.findIndex((h) => h.includes('price') || h.includes('rate') || h.includes('tariff'));
          const catIdx = header.findIndex((h) => h.includes('category') || h.includes('type'));
          const bedIdx = header.findIndex((h) => h.includes('bed'));
          const occIdx = header.findIndex((h) => h.includes('occupancy') || h.includes('capacity'));

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

            items.push({
              name,
              category: catIdx !== -1 && cols[catIdx] ? cols[catIdx] : 'Rooms',
              base_price: price,
              weekend_price: price * 1.15,
              currency: 'INR',
              bed_type: bedIdx !== -1 && cols[bedIdx] ? cols[bedIdx] : '1 King Bed',
              max_occupancy: occIdx !== -1 && !isNaN(parseInt(cols[occIdx])) ? parseInt(cols[occIdx]) : 2,
              max_adults: occIdx !== -1 && !isNaN(parseInt(cols[occIdx])) ? parseInt(cols[occIdx]) : 2,
              max_children: 1,
              amenities: ['High-Speed Wi-Fi', 'En-suite Bathroom'],
              inclusions: ['Complimentary Buffet Breakfast'],
              check_in_time: '14:00',
              check_out_time: '11:00',
              cancellation_policy: 'Free cancellation up to 48 hours prior to arrival',
              is_available: true,
            });
          }
          setFileParsedPreview(items);
          setFeedback({ type: 'success', text: `Parsed ${items.length} room tiers from CSV file.` });
        }
      } catch (err) {
        setFeedback({ type: 'error', text: `Failed parsing file: ${err.message}` });
      }
    };
    reader.readAsText(file);
  };

  const handleSaveFileRooms = async () => {
    if (!fileParsedPreview.length || !business?.id) return;
    setSaving(true);
    setFeedback(null);
    try {
      const res = await api.uploadRooms(business.id, fileParsedPreview, replaceOnFile);
      setFeedback({
        type: 'success',
        text: `Uploaded and saved ${res.items.length} room types successfully!`,
      });
      setFileParsedPreview([]);
      setSelectedFile(null);
      await loadRooms();
      setActiveTab('rooms');
      if (onRoomsUpdated) onRoomsUpdated();
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to save rooms: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  const handleAddSingleRoom = async (e) => {
    e.preventDefault();
    if (!newRoomName.trim() || !newRoomPrice || !business?.id) return;
    setSaving(true);
    setFeedback(null);
    try {
      const price = parseFloat(newRoomPrice);
      const weekend = newRoomWeekendPrice ? parseFloat(newRoomWeekendPrice) : price * 1.15;
      const occ = parseInt(newRoomOccupancy) || 2;

      const newRoom = {
        name: newRoomName.trim(),
        category: newRoomCategory,
        base_price: price,
        weekend_price: weekend,
        currency: 'INR',
        description: newRoomDesc.trim() || null,
        bed_type: newRoomBed,
        max_occupancy: occ,
        max_adults: occ,
        max_children: 1,
        amenities: selectedAmenities,
        inclusions: selectedInclusions,
        check_in_time: '14:00',
        check_out_time: '11:00',
        cancellation_policy: 'Free cancellation up to 48 hours prior to arrival',
        is_available: true,
      };

      await api.uploadRooms(business.id, [newRoom], false);
      setFeedback({ type: 'success', text: `Room '${newRoomName}' added to rate card!` });
      setNewRoomName('');
      setNewRoomPrice('');
      setNewRoomWeekendPrice('');
      setNewRoomDesc('');
      await loadRooms();
      setActiveTab('rooms');
      if (onRoomsUpdated) onRoomsUpdated();
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to add room: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteRoom = async (roomId, roomName) => {
    if (!window.confirm(`Are you sure you want to remove '${roomName}' from your rate card?`)) return;
    try {
      await api.deleteRoomType(business.id, roomId);
      setRooms((prev) => prev.filter((r) => r.id !== roomId));
      setFeedback({ type: 'success', text: `Room '${roomName}' removed.` });
      if (onRoomsUpdated) onRoomsUpdated();
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to delete room: ${err.message}` });
    }
  };

  const toggleAmenity = (amenity) => {
    setSelectedAmenities((prev) =>
      prev.includes(amenity) ? prev.filter((a) => a !== amenity) : [...prev, amenity]
    );
  };

  const toggleInclusion = (inc) => {
    setSelectedInclusions((prev) =>
      prev.includes(inc) ? prev.filter((i) => i !== inc) : [...prev, inc]
    );
  };

  // Filtered rooms
  const filteredRooms = rooms.filter((r) => {
    const matchesCat = categoryFilter === 'All' || r.category === categoryFilter;
    const matchesSearch =
      !searchFilter.trim() ||
      r.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
      (r.description && r.description.toLowerCase().includes(searchFilter.toLowerCase())) ||
      (r.amenities && r.amenities.some((a) => a.toLowerCase().includes(searchFilter.toLowerCase())));
    return matchesCat && matchesSearch;
  });

  return (
    <div style={{ width: '100%', fontFamily: 'inherit' }}>
      {/* Header bar if embedded */}
      {!isEmbedded && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '1.25rem',
            paddingBottom: '0.75rem',
            borderBottom: '1px solid var(--border-medium)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                background: 'rgba(14, 165, 233, 0.12)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#0284c7',
              }}
            >
              <Bed size={20} />
            </div>
            <div>
              <h2 style={{ fontSize: '1.15rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
                Hotel Room Types & Rate Card Store
              </h2>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: 0 }}>
                Manage room tiers, nightly tariffs, bed types, and amenities for <strong>{business?.name}</strong>.
              </p>
            </div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                padding: '6px',
              }}
            >
              <X size={20} />
            </button>
          )}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '1.25rem', borderBottom: '1px solid var(--border-medium)', paddingBottom: '0.5rem' }}>
        <button
          type="button"
          onClick={() => setActiveTab('rooms')}
          style={{
            padding: '0.45rem 0.9rem',
            borderRadius: '6px',
            fontSize: '0.82rem',
            fontWeight: 600,
            cursor: 'pointer',
            border: activeTab === 'rooms' ? '1px solid #0284c7' : '1px solid transparent',
            background: activeTab === 'rooms' ? 'rgba(14, 165, 233, 0.12)' : 'transparent',
            color: activeTab === 'rooms' ? '#0284c7' : 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Bed size={15} /> All Room Types
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('paste')}
          style={{
            padding: '0.45rem 0.9rem',
            borderRadius: '6px',
            fontSize: '0.82rem',
            fontWeight: 600,
            cursor: 'pointer',
            border: activeTab === 'paste' ? '1px solid #0284c7' : '1px solid transparent',
            background: activeTab === 'paste' ? 'rgba(14, 165, 233, 0.12)' : 'transparent',
            color: activeTab === 'paste' ? '#0284c7' : 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Sparkles size={15} /> Paste Brochure / Rate Sheet
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('add')}
          style={{
            padding: '0.45rem 0.9rem',
            borderRadius: '6px',
            fontSize: '0.82rem',
            fontWeight: 600,
            cursor: 'pointer',
            border: activeTab === 'add' ? '1px solid #0284c7' : '1px solid transparent',
            background: activeTab === 'add' ? 'rgba(14, 165, 233, 0.12)' : 'transparent',
            color: activeTab === 'add' ? '#0284c7' : 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Plus size={15} /> Add Single Room
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('upload')}
          style={{
            padding: '0.45rem 0.9rem',
            borderRadius: '6px',
            fontSize: '0.82rem',
            fontWeight: 600,
            cursor: 'pointer',
            border: activeTab === 'upload' ? '1px solid #0284c7' : '1px solid transparent',
            background: activeTab === 'upload' ? 'rgba(14, 165, 233, 0.12)' : 'transparent',
            color: activeTab === 'upload' ? '#0284c7' : 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <UploadCloud size={15} /> Import CSV / JSON
        </button>
      </div>

      {/* Feedback Banner */}
      {feedback && (
        <div
          style={{
            padding: '0.65rem 1rem',
            borderRadius: '6px',
            marginBottom: '1rem',
            fontSize: '0.82rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: feedback.type === 'error' ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)',
            color: feedback.type === 'error' ? '#ef4444' : '#10b981',
            border: `1px solid ${feedback.type === 'error' ? 'rgba(239, 68, 68, 0.25)' : 'rgba(16, 185, 129, 0.25)'}`,
          }}
        >
          {feedback.type === 'error' ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
          <span>{feedback.text}</span>
          <button
            onClick={() => setFeedback(null)}
            style={{ marginLeft: 'auto', background: 'transparent', border: 'none', cursor: 'pointer', color: 'inherit' }}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* =====================================================================
          TAB 1: ALL ROOM TYPES (GRID & SEARCH)
          ===================================================================== */}
      {activeTab === 'rooms' && (
        <div>
          {/* Search & Filter Toolbar */}
          <div style={{ display: 'flex', gap: '10px', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: 1, minWidth: '220px' }}>
              <Search size={15} style={{ position: 'absolute', left: '10px', top: '10px', color: 'var(--text-tertiary)' }} />
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="Search rooms, amenities (e.g. ocean view, king bed, jacuzzi)..."
                className="form-input"
                style={{ paddingLeft: '32px' }}
              />
            </div>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="form-select"
              style={{ width: '160px' }}
            >
              <option value="All">All Categories</option>
              {DEFAULT_ROOM_CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          {loading ? (
            <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-secondary)' }}>
              Loading room catalog...
            </div>
          ) : filteredRooms.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '3rem 1.5rem',
                background: 'var(--bg-app)',
                borderRadius: '8px',
                border: '1px dashed var(--border-medium)',
              }}
            >
              <Bed size={36} style={{ color: 'var(--text-tertiary)', marginBottom: '8px' }} />
              <h4 style={{ margin: '0 0 4px', color: 'var(--text-primary)' }}>No Room Types Found</h4>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: '0 0 1rem' }}>
                {rooms.length === 0
                  ? 'Your hotel rate card is currently empty. Add your room tiers or paste a brochure.'
                  : 'No room types matched your search filters.'}
              </p>
              {rooms.length === 0 && (
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => setActiveTab('paste')}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                >
                  <Sparkles size={15} /> Paste Brochure or Rate Sheet
                </button>
              )}
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
              {filteredRooms.map((room) => (
                <div
                  key={room.id}
                  className="card"
                  style={{
                    padding: '1.25rem',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-medium)',
                    borderRadius: '10px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          fontWeight: 600,
                          textTransform: 'uppercase',
                          letterSpacing: '0.04em',
                          color: '#0284c7',
                          background: 'rgba(14, 165, 233, 0.1)',
                          padding: '2px 8px',
                          borderRadius: '4px',
                        }}
                      >
                        {room.category}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleDeleteRoom(room.id, room.name)}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: 'var(--text-tertiary)',
                          cursor: 'pointer',
                          padding: '4px',
                        }}
                        title="Remove room type"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>

                    <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: '0 0 6px', color: 'var(--text-primary)' }}>
                      {room.name}
                    </h3>

                    {room.description && (
                      <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0 0 10px', lineHeight: 1.4 }}>
                        {room.description}
                      </p>
                    )}

                    {/* Features row */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '10px' }}>
                      <span
                        style={{
                          fontSize: '0.74rem',
                          background: 'var(--bg-app)',
                          border: '1px solid var(--border-medium)',
                          padding: '2px 7px',
                          borderRadius: '4px',
                          color: 'var(--text-secondary)',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <Bed size={12} /> {room.bed_type}
                      </span>
                      <span
                        style={{
                          fontSize: '0.74rem',
                          background: 'var(--bg-app)',
                          border: '1px solid var(--border-medium)',
                          padding: '2px 7px',
                          borderRadius: '4px',
                          color: 'var(--text-secondary)',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <Users size={12} /> Up to {room.max_occupancy} guests
                      </span>
                    </div>

                    {/* Amenities tags */}
                    {room.amenities && room.amenities.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '8px' }}>
                        {room.amenities.map((am) => (
                          <span
                            key={am}
                            style={{
                              fontSize: '0.7rem',
                              background: 'rgba(2, 132, 199, 0.08)',
                              color: '#0284c7',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              fontWeight: 500,
                            }}
                          >
                            ✓ {am}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Inclusions */}
                    {room.inclusions && room.inclusions.length > 0 && (
                      <div style={{ fontSize: '0.74rem', color: '#059669', marginBottom: '10px' }}>
                        ★ Inclusions: {room.inclusions.join(', ')}
                      </div>
                    )}
                  </div>

                  {/* Pricing footer */}
                  <div
                    style={{
                      borderTop: '1px solid var(--border-medium)',
                      paddingTop: '8px',
                      display: 'flex',
                      alignItems: 'baseline',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div>
                      <span style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                        ₹{room.base_price.toLocaleString()}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginLeft: '4px' }}>/ night</span>
                    </div>
                    {room.weekend_price && room.weekend_price !== room.base_price && (
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                        Weekend: ₹{room.weekend_price.toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* =====================================================================
          TAB 2: PASTE BROCHURE / RATE SHEET (AUTO PARSER)
          ===================================================================== */}
      {activeTab === 'paste' && (
        <div style={{ maxWidth: '780px' }}>
          <div style={{ marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: '0 0 4px', color: 'var(--text-primary)' }}>
              Paste Hotel Room Brochure or Rate Card
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: 0 }}>
              Paste raw room descriptions and tariffs from your hotel website, brochure, or booking sheet.
              The AI parser automatically extracts room tiers, nightly prices, bed types, and amenities.
            </p>
          </div>

          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label className="form-label">Default Category for Unclassified Rooms</label>
            <select
              value={pasteCategory}
              onChange={(e) => setPasteCategory(e.target.value)}
              className="form-select"
              style={{ maxWidth: '240px' }}
            >
              {DEFAULT_ROOM_CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label className="form-label">Brochure / Room Tariff Text</label>
            <textarea
              rows={8}
              value={pastedText}
              onChange={(e) => setPastedText(e.target.value)}
              placeholder={`Example:\nDeluxe Ocean King Room - ₹7,500/night (King bed, ocean view, private balcony, breakfast included)\nExecutive Suite - ₹14,000/night (Panoramic sea view, bathtub, jacuzzi, mini-bar)\nBeachfront Private Villa - ₹35,000/night (Private pool, direct beach access, 2 king beds)`}
              className="form-input"
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', lineHeight: 1.5 }}
            />
          </div>

          <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '1.25rem' }}>
            <button
              type="button"
              className="btn-primary"
              onClick={handleParseText}
              disabled={saving || !pastedText.trim()}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
            >
              <Sparkles size={16} /> {saving ? 'Extracting Rooms...' : 'Extract Room Tiers & Rates'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setPastedText('');
                setParsedPasteRooms([]);
              }}
              disabled={saving || !pastedText.trim()}
            >
              Clear
            </button>
          </div>

          {/* Parsed Preview Table */}
          {parsedPasteRooms.length > 0 && (
            <div
              style={{
                marginTop: '1.25rem',
                padding: '1.25rem',
                background: 'var(--bg-app)',
                borderRadius: '8px',
                border: '1px solid var(--border-medium)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                <h4 style={{ margin: 0, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
                  Extracted Rooms ({parsedPasteRooms.length})
                </h4>
                <label style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={replaceOnPaste}
                    onChange={(e) => setReplaceOnPaste(e.target.checked)}
                  />
                  <span>Replace existing room catalog completely</span>
                </label>
              </div>

              <div style={{ maxHeight: '280px', overflowY: 'auto', marginBottom: '1rem' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                  <thead>
                    <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border-medium)', color: 'var(--text-secondary)' }}>
                      <th style={{ padding: '6px 8px' }}>Room Tier</th>
                      <th style={{ padding: '6px 8px' }}>Category</th>
                      <th style={{ padding: '6px 8px' }}>Nightly Rate</th>
                      <th style={{ padding: '6px 8px' }}>Bed Type</th>
                      <th style={{ padding: '6px 8px' }}>Amenities</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsedPasteRooms.map((r, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '8px', fontWeight: 600, color: 'var(--text-primary)' }}>{r.name}</td>
                        <td style={{ padding: '8px' }}>{r.category}</td>
                        <td style={{ padding: '8px', color: '#0284c7', fontWeight: 700 }}>₹{r.base_price.toLocaleString()}</td>
                        <td style={{ padding: '8px' }}>{r.bed_type}</td>
                        <td style={{ padding: '8px', fontSize: '0.74rem' }}>{r.amenities?.join(', ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <button
                type="button"
                className="btn-primary"
                onClick={handleSaveParsedRooms}
                disabled={saving}
                style={{ width: '100%', padding: '0.65rem' }}
              >
                {saving ? 'Saving...' : `Save ${parsedPasteRooms.length} Room Types to Rate Card`}
              </button>
            </div>
          )}
        </div>
      )}

      {/* =====================================================================
          TAB 3: ADD SINGLE ROOM FORM
          ===================================================================== */}
      {activeTab === 'add' && (
        <form onSubmit={handleAddSingleRoom} style={{ maxWidth: '680px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px', marginBottom: '12px' }}>
            <div className="form-group">
              <label className="form-label">Room / Suite Name *</label>
              <input
                type="text"
                required
                value={newRoomName}
                onChange={(e) => setNewRoomName(e.target.value)}
                placeholder="e.g. Deluxe Oceanfront King Suite"
                className="form-input"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Category</label>
              <select
                value={newRoomCategory}
                onChange={(e) => setNewRoomCategory(e.target.value)}
                className="form-select"
              >
                {DEFAULT_ROOM_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '12px', marginBottom: '12px' }}>
            <div className="form-group">
              <label className="form-label">Base Rate (₹ / night) *</label>
              <input
                type="number"
                step="0.01"
                required
                value={newRoomPrice}
                onChange={(e) => setNewRoomPrice(e.target.value)}
                placeholder="6500"
                className="form-input"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Weekend Rate (₹)</label>
              <input
                type="number"
                step="0.01"
                value={newRoomWeekendPrice}
                onChange={(e) => setNewRoomWeekendPrice(e.target.value)}
                placeholder="7500"
                className="form-input"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Bed Type</label>
              <select
                value={newRoomBed}
                onChange={(e) => setNewRoomBed(e.target.value)}
                className="form-select"
              >
                <option value="1 King Bed">1 King Bed</option>
                <option value="2 Twin Beds">2 Twin Beds</option>
                <option value="1 Queen Bed">1 Queen Bed</option>
                <option value="2 King Beds">2 King Beds</option>
                <option value="1 Master King + 2 Singles">1 Master King + 2 Singles</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Max Occupancy</label>
              <input
                type="number"
                min="1"
                max="20"
                value={newRoomOccupancy}
                onChange={(e) => setNewRoomOccupancy(e.target.value)}
                className="form-input"
              />
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: '12px' }}>
            <label className="form-label">Description & View Details</label>
            <textarea
              rows={2}
              value={newRoomDesc}
              onChange={(e) => setNewRoomDesc(e.target.value)}
              placeholder="e.g. Spacious corner room overlooking the Arabian Sea with private balcony and marble bath."
              className="form-input"
            />
          </div>

          {/* Amenities Multi-Select */}
          <div className="form-group" style={{ marginBottom: '12px' }}>
            <label className="form-label">Included Room Amenities</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {COMMON_AMENITIES.map((am) => {
                const isSelected = selectedAmenities.includes(am);
                return (
                  <button
                    key={am}
                    type="button"
                    onClick={() => toggleAmenity(am)}
                    style={{
                      padding: '4px 10px',
                      borderRadius: '20px',
                      fontSize: '0.74rem',
                      cursor: 'pointer',
                      border: isSelected ? '1px solid #0284c7' : '1px solid var(--border-medium)',
                      background: isSelected ? 'rgba(14, 165, 233, 0.12)' : 'var(--bg-app)',
                      color: isSelected ? '#0284c7' : 'var(--text-secondary)',
                      fontWeight: isSelected ? 600 : 400,
                    }}
                  >
                    {isSelected ? '✓ ' : '+ '} {am}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Inclusions Multi-Select */}
          <div className="form-group" style={{ marginBottom: '1.25rem' }}>
            <label className="form-label">Complimentary Stay Inclusions</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {COMMON_INCLUSIONS.map((inc) => {
                const isSelected = selectedInclusions.includes(inc);
                return (
                  <button
                    key={inc}
                    type="button"
                    onClick={() => toggleInclusion(inc)}
                    style={{
                      padding: '4px 10px',
                      borderRadius: '20px',
                      fontSize: '0.74rem',
                      cursor: 'pointer',
                      border: isSelected ? '1px solid #059669' : '1px solid var(--border-medium)',
                      background: isSelected ? 'rgba(16, 185, 129, 0.12)' : 'var(--bg-app)',
                      color: isSelected ? '#059669' : 'var(--text-secondary)',
                      fontWeight: isSelected ? 600 : 400,
                    }}
                  >
                    {isSelected ? '★ ' : '+ '} {inc}
                  </button>
                );
              })}
            </div>
          </div>

          <button
            type="submit"
            className="btn-primary"
            disabled={saving}
            style={{ padding: '0.65rem 1.5rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <Plus size={16} /> {saving ? 'Adding...' : 'Add Room to Rate Card'}
          </button>
        </form>
      )}

      {/* =====================================================================
          TAB 4: IMPORT CSV / JSON FILE
          ===================================================================== */}
      {activeTab === 'upload' && (
        <div style={{ maxWidth: '680px' }}>
          <div style={{ marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: '0 0 4px', color: 'var(--text-primary)' }}>
              Bulk Upload Room Rate Sheet (CSV or JSON)
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: 0 }}>
              Upload your structured rate card spreadsheet containing room names, prices, and amenities.
            </p>
          </div>

          <div
            style={{
              padding: '2rem',
              border: '2px dashed var(--border-medium)',
              borderRadius: '8px',
              textAlign: 'center',
              background: 'var(--bg-app)',
              marginBottom: '1rem',
              cursor: 'pointer',
            }}
            onClick={() => document.getElementById('room-file-input').click()}
          >
            <UploadCloud size={36} style={{ color: '#0284c7', marginBottom: '8px' }} />
            <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
              {selectedFile ? selectedFile.name : 'Click to select CSV or JSON file'}
            </div>
            <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
              Expected columns: name, category, price, bed_type, amenities
            </div>
            <input
              id="room-file-input"
              type="file"
              accept=".csv,.json"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
          </div>

          {fileParsedPreview.length > 0 && (
            <div style={{ padding: '1rem', background: 'var(--bg-app)', borderRadius: '8px', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Validated {fileParsedPreview.length} rooms ready to import
                </span>
                <label style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={replaceOnFile}
                    onChange={(e) => setReplaceOnFile(e.target.checked)}
                  />
                  <span>Replace existing rooms</span>
                </label>
              </div>

              <button
                type="button"
                className="btn-primary"
                onClick={handleSaveFileRooms}
                disabled={saving}
                style={{ width: '100%', padding: '0.65rem' }}
              >
                {saving ? 'Saving...' : `Import ${fileParsedPreview.length} Rooms to Rate Card`}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function RoomManagerModal({ business, isOpen, onClose, onRoomsUpdated }) {
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
        <RoomManagerView
          business={business}
          isEmbedded={false}
          onRoomsUpdated={onRoomsUpdated}
          onClose={onClose}
          defaultTab="rooms"
        />
      </div>
    </div>
  );
}

export default RoomManagerModal;
