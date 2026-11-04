import React, { useState, useEffect } from 'react';
import {
  Bed,
  Layers,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Plus,
  LogIn,
  LogOut,
  Wrench,
  Brush,
  User,
  Phone,
  Calendar,
  X,
  Sliders,
  ShieldCheck,
  Building2,
} from 'lucide-react';
import { api } from '../api';

export default function HotelFloorGridView({ business, onLayoutUpdated }) {
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [layout, setLayout] = useState(null);
  const [roomTypes, setRoomTypes] = useState([]);
  const [statusFilter, setStatusFilter] = useState('all'); // 'all', 'clean', 'dirty', 'occupied', 'maintenance'

  // Modal States
  const [checkInModalOpen, setCheckInModalOpen] = useState(false);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [guestName, setGuestName] = useState('');
  const [guestPhone, setGuestPhone] = useState('');
  const [stayNights, setStayNights] = useState(1);
  const [guestPartySize, setGuestPartySize] = useState(2);
  const [checkInNotes, setCheckInNotes] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  // Bulk Setup Modal State
  const [setupModalOpen, setSetupModalOpen] = useState(false);
  const [floorsCount, setFloorsCount] = useState(3);
  const [roomsPerFloor, setRoomsPerFloor] = useState(4);
  const [startingFloor, setStartingFloor] = useState(1);
  const [selectedRoomTypeId, setSelectedRoomTypeId] = useState('');
  const [replaceExisting, setReplaceExisting] = useState(false);

  useEffect(() => {
    if (business?.id) {
      loadData();
    }
  }, [business?.id]);

  const loadData = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const [floorData, roomsData] = await Promise.all([
        api.getHotelFloors(business.id),
        api.getRooms(business.id).catch(() => ({ items: [] })),
      ]);
      setLayout(floorData);
      setRoomTypes(roomsData?.items || []);
      if (roomsData?.items?.length > 0 && !selectedRoomTypeId) {
        setSelectedRoomTypeId(roomsData.items[0].id);
      }
    } catch (err) {
      console.error('Failed to load hotel floor grid:', err);
      setErrorMsg(err.message || 'Failed to load floor layout.');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateStatus = async (resourceId, newStatus) => {
    setActionLoading(true);
    try {
      const updated = await api.updateRoomStatus(business.id, resourceId, newStatus);
      setLayout(updated);
      setFeedback({ type: 'success', text: `Room status updated to "${newStatus}".` });
      setTimeout(() => setFeedback(null), 3500);
      if (onLayoutUpdated) onLayoutUpdated();
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to update status: ${err.message}` });
    } finally {
      setActionLoading(false);
    }
  };

  const openCheckInModal = (room) => {
    setSelectedRoom(room);
    setGuestName('');
    setGuestPhone('');
    setStayNights(1);
    setGuestPartySize(Math.min(2, room.capacity || 2));
    setCheckInNotes('');
    setCheckInModalOpen(true);
  };

  const handleCheckInSubmit = async (e) => {
    e.preventDefault();
    if (!selectedRoom || !guestName.trim() || !guestPhone.trim()) return;

    setActionLoading(true);
    try {
      const updated = await api.hotelCheckIn(business.id, selectedRoom.id, {
        customer_name: guestName.trim(),
        customer_phone: guestPhone.trim(),
        nights: Number(stayNights),
        party_size: Number(guestPartySize),
        notes: checkInNotes.trim() || undefined,
      });
      setLayout(updated);
      setCheckInModalOpen(false);
      setFeedback({
        type: 'success',
        text: `Checked in "${guestName.trim()}" to Room ${selectedRoom.room_number || selectedRoom.name}!`,
      });
      setTimeout(() => setFeedback(null), 4000);
      if (onLayoutUpdated) onLayoutUpdated();
    } catch (err) {
      setFeedback({ type: 'error', text: `Check-in failed: ${err.message}` });
    } finally {
      setActionLoading(false);
    }
  };

  const handleCheckOut = async (room) => {
    const occupant = room.active_guest?.customer_name || 'guest';
    if (!window.confirm(`Check out ${occupant} from Room ${room.room_number || room.name}? Room will be marked as "Needs Cleaning".`)) {
      return;
    }

    setActionLoading(true);
    try {
      const updated = await api.hotelCheckOut(business.id, room.id);
      setLayout(updated);
      setFeedback({
        type: 'success',
        text: `Room ${room.room_number || room.name} checked out and marked for housekeeping.`,
      });
      setTimeout(() => setFeedback(null), 4000);
      if (onLayoutUpdated) onLayoutUpdated();
    } catch (err) {
      setFeedback({ type: 'error', text: `Check-out failed: ${err.message}` });
    } finally {
      setActionLoading(false);
    }
  };

  const handleBulkSetupSubmit = async (e) => {
    e.preventDefault();
    setActionLoading(true);
    try {
      const updated = await api.bulkSetupHotelFloors(business.id, {
        floors_count: Number(floorsCount),
        rooms_per_floor: Number(roomsPerFloor),
        starting_floor: Number(startingFloor),
        room_type_id: selectedRoomTypeId || undefined,
        replace_existing: replaceExisting,
      });
      setLayout(updated);
      setSetupModalOpen(false);
      setFeedback({
        type: 'success',
        text: `Generated ${Number(floorsCount) * Number(roomsPerFloor)} rooms across ${floorsCount} floors!`,
      });
      setTimeout(() => setFeedback(null), 4000);
      if (onLayoutUpdated) onLayoutUpdated();
    } catch (err) {
      setFeedback({ type: 'error', text: `Property setup failed: ${err.message}` });
    } finally {
      setActionLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'occupied':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: 'var(--radius-full)',
              background: 'rgba(56, 189, 248, 0.15)',
              color: '#38bdf8',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              fontSize: '0.72rem',
              fontWeight: 600,
            }}
          >
            <User size={10} /> Occupied
          </span>
        );
      case 'dirty':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: 'var(--radius-full)',
              background: 'rgba(251, 191, 36, 0.15)',
              color: '#fbbf24',
              border: '1px solid rgba(251, 191, 36, 0.3)',
              fontSize: '0.72rem',
              fontWeight: 600,
            }}
          >
            <Brush size={10} /> Needs Cleaning
          </span>
        );
      case 'maintenance':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: 'var(--radius-full)',
              background: 'rgba(244, 63, 94, 0.15)',
              color: '#fb7185',
              border: '1px solid rgba(244, 63, 94, 0.3)',
              fontSize: '0.72rem',
              fontWeight: 600,
            }}
          >
            <Wrench size={10} /> Maintenance
          </span>
        );
      case 'clean':
      default:
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: 'var(--radius-full)',
              background: 'rgba(52, 211, 153, 0.15)',
              color: '#34d399',
              border: '1px solid rgba(52, 211, 153, 0.3)',
              fontSize: '0.72rem',
              fontWeight: 600,
            }}
          >
            <CheckCircle2 size={10} /> Clean & Ready
          </span>
        );
    }
  };

  const floors = layout?.floors || [];
  const filteredFloors = floors.map((f) => ({
    ...f,
    rooms: f.rooms.filter((r) => {
      if (statusFilter === 'all') return true;
      return r.status === statusFilter;
    }),
  })).filter((f) => f.rooms.length > 0 || statusFilter === 'all');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Feedback Banner */}
      {feedback && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-md, 8px)',
            background: feedback.type === 'success' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
            border: `1px solid ${feedback.type === 'success' ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.3)'}`,
            color: feedback.type === 'success' ? 'var(--mint-400, #34d399)' : '#fb7185',
            fontSize: '0.82rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          {feedback.type === 'success' ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
          {feedback.text}
        </div>
      )}

      {errorMsg && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-md, 8px)',
            background: 'rgba(244, 63, 94, 0.1)',
            border: '1px solid rgba(244, 63, 94, 0.3)',
            color: '#fb7185',
            fontSize: '0.82rem',
          }}
        >
          {errorMsg}
        </div>
      )}

      {/* KPI Stats Strip */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
          gap: '1rem',
        }}
      >
        <div
          className="card"
          style={{
            padding: '1rem',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-medium)',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          <div style={{ fontSize: '0.74rem', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase' }}>
            Total Rooms
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {layout?.total_rooms ?? 0}
          </div>
          <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
            Authoritative physical units
          </div>
        </div>

        <div
          className="card"
          style={{
            padding: '1rem',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-medium)',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          <div style={{ fontSize: '0.74rem', color: '#38bdf8', fontWeight: 600, textTransform: 'uppercase' }}>
            Occupied
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#38bdf8' }}>
            {layout?.occupied_count ?? 0}
          </div>
          <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
            {layout?.occupancy_rate_pct ?? 0}% Live Occupancy
          </div>
        </div>

        <div
          className="card"
          style={{
            padding: '1rem',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-medium)',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          <div style={{ fontSize: '0.74rem', color: '#34d399', fontWeight: 600, textTransform: 'uppercase' }}>
            Clean & Ready
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#34d399' }}>
            {layout?.clean_count ?? 0}
          </div>
          <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
            Available for instant check-in
          </div>
        </div>

        <div
          className="card"
          style={{
            padding: '1rem',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-medium)',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          <div style={{ fontSize: '0.74rem', color: '#fbbf24', fontWeight: 600, textTransform: 'uppercase' }}>
            Housekeeping Required
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#fbbf24' }}>
            {layout?.dirty_count ?? 0}
          </div>
          <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
            Needs cleaning after checkout
          </div>
        </div>
      </div>

      {/* Control Bar & Filter Strip */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.75rem',
          padding: '0.85rem 1rem',
          borderRadius: 'var(--radius-md, 8px)',
          background: 'var(--bg-surface-elevated)',
          border: '1px solid var(--border-medium)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', marginRight: '4px', fontWeight: 600 }}>
            Filter:
          </span>
          {[
            { id: 'all', label: `All (${layout?.total_rooms ?? 0})` },
            { id: 'clean', label: `🟢 Clean (${layout?.clean_count ?? 0})` },
            { id: 'dirty', label: `🟡 Dirty (${layout?.dirty_count ?? 0})` },
            { id: 'occupied', label: `🔵 Occupied (${layout?.occupied_count ?? 0})` },
            { id: 'maintenance', label: `🔴 Maintenance (${layout?.maintenance_count ?? 0})` },
          ].map((flt) => (
            <button
              key={flt.id}
              type="button"
              className={`btn-secondary ${statusFilter === flt.id ? 'active' : ''}`}
              style={{
                fontSize: '0.74rem',
                padding: '0.25rem 0.65rem',
                background: statusFilter === flt.id ? '#ffffff' : 'transparent',
                borderColor: statusFilter === flt.id ? '#ffffff' : 'var(--border-medium)',
                color: statusFilter === flt.id ? '#07080a' : 'var(--text-secondary)',
                fontWeight: 600,
              }}
              onClick={() => setStatusFilter(flt.id)}
            >
              {flt.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            type="button"
            className="btn-secondary"
            onClick={loadData}
            disabled={loading}
            style={{ fontSize: '0.76rem', padding: '0.35rem 0.75rem' }}
            title="Refresh floor grid"
          >
            <RefreshCw size={12} className={loading ? 'spin' : ''} /> Refresh
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => setSetupModalOpen(true)}
            style={{ fontSize: '0.76rem', padding: '0.35rem 0.85rem' }}
          >
            <Building2 size={13} /> Bulk Setup Property
          </button>
        </div>
      </div>

      {/* Floor-by-Floor Grid */}
      {filteredFloors.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '3rem 1.5rem',
            background: 'var(--bg-card)',
            borderRadius: 'var(--radius-md, 8px)',
            border: '1px solid var(--border-medium)',
            color: 'var(--text-tertiary)',
          }}
        >
          <Building2 size={32} style={{ margin: '0 auto 0.75rem', opacity: 0.5 }} />
          <div style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
            No rooms found matching "{statusFilter}" filter.
          </div>
          <div style={{ fontSize: '0.8rem', marginBottom: '1.25rem' }}>
            Use the Bulk Setup Property button to auto-generate your floors and rooms.
          </div>
          <button
            type="button"
            className="btn-primary"
            onClick={() => setSetupModalOpen(true)}
            style={{ margin: '0 auto', fontSize: '0.8rem' }}
          >
            <Plus size={14} /> Setup Floor Plan
          </button>
        </div>
      ) : (
        filteredFloors.map((flr) => (
          <div
            key={flr.floor_number}
            className="card"
            style={{
              padding: '1.25rem',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-medium)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '1rem',
                borderBottom: '1px solid var(--border-medium)',
                paddingBottom: '0.65rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Layers size={18} color="var(--sky-400, #38bdf8)" />
                <h3 style={{ fontSize: '1rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
                  {flr.floor_name}
                </h3>
                <span
                  style={{
                    fontSize: '0.72rem',
                    color: 'var(--text-tertiary)',
                    background: 'var(--bg-surface-elevated)',
                    padding: '2px 8px',
                    borderRadius: 'var(--radius-full)',
                    border: '1px solid var(--border-medium)',
                  }}
                >
                  {flr.rooms.length} Units
                </span>
              </div>
            </div>

            {/* Room Cards Row */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                gap: '1rem',
              }}
            >
              {flr.rooms.map((rm) => {
                const isOccupied = rm.status === 'occupied';
                const isDirty = rm.status === 'dirty';
                const isClean = rm.status === 'clean';
                const isMaint = rm.status === 'maintenance';

                return (
                  <div
                    key={rm.id}
                    style={{
                      borderRadius: 'var(--radius-md, 8px)',
                      padding: '1rem',
                      background: isOccupied
                        ? 'rgba(56, 189, 248, 0.04)'
                        : isDirty
                        ? 'rgba(251, 191, 36, 0.04)'
                        : isMaint
                        ? 'rgba(244, 63, 94, 0.04)'
                        : 'var(--bg-surface-elevated)',
                      border: `1px solid ${
                        isOccupied
                          ? 'rgba(56, 189, 248, 0.3)'
                          : isDirty
                          ? 'rgba(251, 191, 36, 0.3)'
                          : isMaint
                          ? 'rgba(244, 63, 94, 0.3)'
                          : 'var(--border-medium)'
                      }`,
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      gap: '0.75rem',
                      transition: 'border-color 0.15s ease',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                        <div>
                          <span
                            style={{
                              fontSize: '1.25rem',
                              fontWeight: 800,
                              color: 'var(--text-primary)',
                              letterSpacing: '-0.02em',
                            }}
                          >
                            {rm.room_number || rm.name}
                          </span>
                        </div>
                        {getStatusBadge(rm.status)}
                      </div>

                      <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '4px' }}>
                        {rm.room_type_name || 'Standard Room'}
                      </div>

                      <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        <span>🛏️ {rm.bed_type || 'Double Bed'}</span>
                        <span>👥 Max {rm.capacity || 2}</span>
                        {rm.base_price && <span>💰 ₹{rm.base_price.toLocaleString()}/nt</span>}
                      </div>

                      {/* Active Guest Card if Occupied */}
                      {isOccupied && rm.active_guest && (
                        <div
                          style={{
                            marginTop: '0.65rem',
                            padding: '0.55rem 0.65rem',
                            borderRadius: '6px',
                            background: 'rgba(56, 189, 248, 0.08)',
                            border: '1px solid rgba(56, 189, 248, 0.2)',
                            fontSize: '0.74rem',
                          }}
                        >
                          <div style={{ fontWeight: 700, color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '2px' }}>
                            <User size={11} /> {rm.active_guest.customer_name}
                          </div>
                          <div style={{ color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <Phone size={10} /> {rm.active_guest.customer_phone}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Operational Actions */}
                    <div
                      style={{
                        display: 'flex',
                        gap: '0.4rem',
                        alignItems: 'center',
                        borderTop: '1px solid var(--border-medium)',
                        paddingTop: '0.6rem',
                        flexWrap: 'wrap',
                      }}
                    >
                      {isClean && (
                        <button
                          type="button"
                          className="btn-primary"
                          onClick={() => openCheckInModal(rm)}
                          disabled={actionLoading}
                          style={{ fontSize: '0.72rem', padding: '0.25rem 0.65rem', flex: 1, justifyContent: 'center' }}
                        >
                          <LogIn size={11} /> Check-In
                        </button>
                      )}

                      {isOccupied && (
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => handleCheckOut(rm)}
                          disabled={actionLoading}
                          style={{
                            fontSize: '0.72rem',
                            padding: '0.25rem 0.65rem',
                            flex: 1,
                            justifyContent: 'center',
                            color: '#fb7185',
                            borderColor: 'rgba(244, 63, 94, 0.3)',
                          }}
                        >
                          <LogOut size={11} /> Check-Out
                        </button>
                      )}

                      {isDirty && (
                        <button
                          type="button"
                          className="btn-primary"
                          onClick={() => handleUpdateStatus(rm.id, 'clean')}
                          disabled={actionLoading}
                          style={{
                            fontSize: '0.72rem',
                            padding: '0.25rem 0.65rem',
                            flex: 1,
                            justifyContent: 'center',
                            background: '#059669',
                            borderColor: '#059669',
                          }}
                        >
                          <Brush size={11} /> Mark Cleaned
                        </button>
                      )}

                      {/* Dropdown status toggles */}
                      {!isOccupied && (
                        <select
                          className="form-input"
                          value={rm.status}
                          disabled={actionLoading}
                          onChange={(e) => handleUpdateStatus(rm.id, e.target.value)}
                          style={{
                            fontSize: '0.7rem',
                            padding: '0.2rem 0.4rem',
                            width: 'auto',
                            height: 'auto',
                          }}
                        >
                          <option value="clean">Clean</option>
                          <option value="dirty">Needs Cleaning</option>
                          <option value="maintenance">Maintenance</option>
                        </select>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}

      {/* =====================================================================
          MODAL: WALK-IN / FRONT DESK GUEST CHECK-IN
          ===================================================================== */}
      {checkInModalOpen && selectedRoom && (
        <div className="modal-backdrop">
          <div className="modal-content" style={{ maxWidth: '440px', padding: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <LogIn size={18} color="#38bdf8" />
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700 }}>
                  Front Desk Check-In — Room {selectedRoom.room_number || selectedRoom.name}
                </h3>
              </div>
              <button
                type="button"
                className="btn-icon"
                onClick={() => setCheckInModalOpen(false)}
                style={{ padding: '4px' }}
              >
                <X size={16} />
              </button>
            </div>

            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>
              Assign walk-in guest to <strong>{selectedRoom.room_type_name || 'Room'}</strong> on {selectedRoom.floor_name}.
            </p>

            <form onSubmit={handleCheckInSubmit}>
              <div className="form-group" style={{ marginBottom: '0.85rem' }}>
                <label className="form-label">Guest Full Name *</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Vikram Malhotra"
                  value={guestName}
                  onChange={(e) => setGuestName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group" style={{ marginBottom: '0.85rem' }}>
                <label className="form-label">Guest Mobile Number *</label>
                <input
                  type="tel"
                  className="form-input"
                  placeholder="+91 98765 43210"
                  value={guestPhone}
                  onChange={(e) => setGuestPhone(e.target.value)}
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.85rem' }}>
                <div className="form-group">
                  <label className="form-label">Stay Nights</label>
                  <input
                    type="number"
                    min="1"
                    max="60"
                    className="form-input"
                    value={stayNights}
                    onChange={(e) => setStayNights(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Guests Count</label>
                  <input
                    type="number"
                    min="1"
                    max={selectedRoom.capacity || 4}
                    className="form-input"
                    value={guestPartySize}
                    onChange={(e) => setGuestPartySize(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: '1.25rem' }}>
                <label className="form-label">Special Requests / Notes</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Extra towel, early checkout, airport drop"
                  value={checkInNotes}
                  onChange={(e) => setCheckInNotes(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setCheckInModalOpen(false)}
                  disabled={actionLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={actionLoading}
                >
                  <LogIn size={14} /> {actionLoading ? 'Checking In...' : 'Confirm Check-In'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =====================================================================
          MODAL: BULK PROPERTY SETUP (OYO ONBOARDING PARITY)
          ===================================================================== */}
      {setupModalOpen && (
        <div className="modal-backdrop">
          <div className="modal-content" style={{ maxWidth: '480px', padding: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Building2 size={18} color="var(--mint-400, #34d399)" />
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700 }}>
                  Property Layout Setup Wizard
                </h3>
              </div>
              <button
                type="button"
                className="btn-icon"
                onClick={() => setSetupModalOpen(false)}
                style={{ padding: '4px' }}
              >
                <X size={16} />
              </button>
            </div>

            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>
              Define your building layout like OYO: specify floors, rooms per floor, and room category. Rooms will be auto-numbered (e.g. 101–104, 201–204).
            </p>

            <form onSubmit={handleBulkSetupSubmit}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.85rem' }}>
                <div className="form-group">
                  <label className="form-label">Number of Floors</label>
                  <input
                    type="number"
                    min="1"
                    max="15"
                    className="form-input"
                    value={floorsCount}
                    onChange={(e) => setFloorsCount(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Rooms per Floor</label>
                  <input
                    type="number"
                    min="1"
                    max="30"
                    className="form-input"
                    value={roomsPerFloor}
                    onChange={(e) => setRoomsPerFloor(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.85rem' }}>
                <div className="form-group">
                  <label className="form-label">Starting Floor Number</label>
                  <select
                    className="form-input"
                    value={startingFloor}
                    onChange={(e) => setStartingFloor(Number(e.target.value))}
                  >
                    <option value={0}>Ground Floor (001...)</option>
                    <option value={1}>1st Floor (101...)</option>
                    <option value={2}>2nd Floor (201...)</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Default Room Tier</label>
                  <select
                    className="form-input"
                    value={selectedRoomTypeId}
                    onChange={(e) => setSelectedRoomTypeId(e.target.value)}
                  >
                    {roomTypes.map((rt) => (
                      <option key={rt.id} value={rt.id}>
                        {rt.name}
                      </option>
                    ))}
                    {roomTypes.length === 0 && <option value="">Standard Deluxe Room</option>}
                  </select>
                </div>
              </div>

              <div style={{ marginBottom: '1.25rem', padding: '0.65rem 0.85rem', background: 'var(--bg-surface-elevated)', borderRadius: '6px', border: '1px solid var(--border-medium)' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                  <input
                    type="checkbox"
                    checked={replaceExisting}
                    onChange={(e) => setReplaceExisting(e.target.checked)}
                  />
                  <span>Replace existing rooms with this new layout</span>
                </label>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setSetupModalOpen(false)}
                  disabled={actionLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={actionLoading}
                >
                  <Building2 size={14} /> {actionLoading ? 'Generating...' : `Generate ${Number(floorsCount) * Number(roomsPerFloor)} Rooms`}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
