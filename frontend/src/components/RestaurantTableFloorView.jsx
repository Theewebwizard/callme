import React, { useState, useMemo } from 'react';
import {
  Utensils,
  Users,
  Clock,
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  Plus,
  Trash2,
  CheckCircle2,
  AlertCircle,
  X,
  Search,
  Filter,
  Grid,
  List as ListIcon,
  RefreshCw,
  Phone,
  User,
  Sparkles,
  Bot,
  MapPin,
  Coffee,
  Wine,
  Layers,
  Check,
} from 'lucide-react';
import { api } from '../api';

const DINING_SECTIONS = [
  'All Sections',
  'Main Dining',
  'Outdoor Patio',
  'Private Dining Room',
  'Bar Counter',
];

const TABLE_TYPES = [
  { value: 'table', label: 'Dining Table', icon: Utensils },
  { value: 'booth', label: 'Private Booth', icon: Coffee },
  { value: 'terrace', label: 'Patio / Terrace', icon: Sparkles },
  { value: 'private_room', label: 'VIP Private Dining', icon: Wine },
  { value: 'bar', label: 'Bar Counter', icon: Wine },
];

const MEAL_TIMES = [
  // Lunch Shift
  { time: '12:00', label: '12:00 PM (Lunch)' },
  { time: '12:30', label: '12:30 PM (Lunch)' },
  { time: '13:00', label: '01:00 PM (Lunch)' },
  { time: '13:30', label: '01:30 PM (Lunch)' },
  { time: '14:00', label: '02:00 PM (Lunch)' },
  { time: '14:30', label: '02:30 PM (Lunch)' },
  // Dinner Shift
  { time: '19:00', label: '07:00 PM (Dinner)' },
  { time: '19:30', label: '07:30 PM (Dinner)' },
  { time: '20:00', label: '08:00 PM (Dinner)' },
  { time: '20:30', label: '08:30 PM (Dinner)' },
  { time: '21:00', label: '09:00 PM (Dinner)' },
  { time: '21:30', label: '09:30 PM (Dinner)' },
  { time: '22:00', label: '10:00 PM (Dinner)' },
];

function addMinutesToTime(timeStr, minutes) {
  if (!timeStr || !timeStr.includes(':')) return '20:30';
  const [h, m] = timeStr.split(':').map((v) => parseInt(v, 10));
  const total = h * 60 + (m || 0) + minutes;
  const endH = Math.floor(total / 60) % 24;
  const endM = total % 60;
  return `${endH.toString().padStart(2, '0')}:${endM.toString().padStart(2, '0')}`;
}

const getTodayIso = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const addDaysToIsoString = (isoDateStr, days) => {
  const base = isoDateStr || getTodayIso();
  const parts = base.split('-');
  const year = parseInt(parts[0], 10);
  const month = parseInt(parts[1], 10);
  const day = parseInt(parts[2], 10);
  const d = new Date(Date.UTC(year, month - 1, day));
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};

export default function RestaurantTableFloorView({
  business,
  resources = [],
  reservations = [],
  onRefresh,
}) {
  const [activeTab, setActiveTab] = useState('floor'); // 'floor' | 'timeline' | 'reservations' | 'tables'
  const [selectedSection, setSelectedSection] = useState('All Sections');
  const [selectedDate, setSelectedDate] = useState(() => getTodayIso());
  const [searchQuery, setSearchQuery] = useState('');
  const [feedback, setFeedback] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isNewBookingModalOpen, setIsNewBookingModalOpen] = useState(false);
  const [isAddTableModalOpen, setIsAddTableModalOpen] = useState(false);
  const [cancellingId, setCancellingId] = useState(null);

  // New Reservation Form State
  const [newBooking, setNewBooking] = useState({
    customer_name: '',
    customer_phone: '',
    party_size: 2,
    resource_id: '',
    reservation_date: getTodayIso(),
    start_time: '19:30',
    duration_minutes: 90,
    special_requests: '',
  });

  // New Table Form State
  const [newTable, setNewTable] = useState({
    name: '',
    section: 'Main Dining',
    capacity: 4,
    min_party_size: 2,
    max_party_size: 4,
    resource_type: 'table',
  });

  // Filter only restaurant table resources
  const tables = useMemo(() => {
    return resources.filter(
      (r) =>
        r.resource_type === 'table' ||
        r.resource_type === 'booth' ||
        r.resource_type === 'terrace' ||
        r.resource_type === 'private_room' ||
        r.resource_type === 'bar' ||
        (!['practitioner', 'room', 'clinic_room'].includes(r.resource_type))
    );
  }, [resources]);

  // Filter tables by selected section
  const filteredTables = useMemo(() => {
    if (selectedSection === 'All Sections') return tables;
    return tables.filter((t) => (t.section || '').toLowerCase() === selectedSection.toLowerCase());
  }, [tables, selectedSection]);

  // Compute total restaurant guest capacity
  const totalCovers = useMemo(() => {
    return tables.reduce((acc, t) => acc + (t.capacity || 2), 0);
  }, [tables]);

  // Active reservations count for today
  const activeReservations = useMemo(() => {
    return reservations.filter((r) => r.status !== 'cancelled');
  }, [reservations]);

  const todayReservations = useMemo(() => {
    return activeReservations.filter((r) => (r.start_time || '').slice(0, 10) === selectedDate);
  }, [activeReservations, selectedDate]);

  // Check if a table is reserved during a particular date
  const getTableReservationsForDate = (tableId, dateStr) => {
    return activeReservations.filter((r) => {
      if (r.resource_id !== tableId) return false;
      const bDate = (r.start_time || '').slice(0, 10);
      return bDate === dateStr;
    });
  };

  // Check if a table is currently occupied / reserved today
  const isTableReservedToday = (tableId) => {
    return getTableReservationsForDate(tableId, selectedDate).length > 0;
  };

  // Open New Booking Modal for a specific table
  const handleOpenBookingForTable = (table = null) => {
    const targetTable = table || (tables.length > 0 ? tables[0] : null);
    setNewBooking({
      customer_name: '',
      customer_phone: '',
      party_size: targetTable ? targetTable.capacity : 2,
      resource_id: targetTable ? targetTable.id : '',
      reservation_date: selectedDate,
      start_time: '19:30',
      duration_minutes: 90,
      special_requests: '',
    });
    setIsNewBookingModalOpen(true);
  };

  // Create Table Reservation
  const handleCreateReservation = async (e) => {
    e.preventDefault();
    if (!newBooking.customer_name.trim() || !newBooking.customer_phone.trim()) {
      setFeedback({ type: 'error', text: 'Please enter guest name and phone number.' });
      return;
    }

    setIsSubmitting(true);
    setFeedback(null);

    try {
      const selectedTbl = tables.find((t) => t.id === newBooking.resource_id);
      const startIso = `${newBooking.reservation_date}T${newBooking.start_time}:00`;
      const endTime = addMinutesToTime(newBooking.start_time, Number(newBooking.duration_minutes));
      const endIso = `${newBooking.reservation_date}T${endTime}:00`;

      await api.createReservation(business.id, {
        customer_name: newBooking.customer_name.trim(),
        customer_phone: newBooking.customer_phone.trim(),
        party_size: Number(newBooking.party_size),
        start_time: startIso,
        end_time: endIso,
        resource_id: newBooking.resource_id || undefined,
        resource_type: selectedTbl?.resource_type || 'table',
        section: selectedTbl?.section || 'Main Dining',
        special_requests: newBooking.special_requests || undefined,
        status: 'confirmed',
      });

      setFeedback({
        type: 'success',
        text: `Table reserved for ${newBooking.customer_name} (Party of ${newBooking.party_size}) at ${newBooking.start_time} on ${newBooking.reservation_date}!`,
      });
      setIsNewBookingModalOpen(false);
      if (onRefresh) await onRefresh();
      setTimeout(() => setFeedback(null), 5000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to create reservation: ${err.message}` });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Cancel Table Reservation
  const handleCancelReservation = async (bookingId, phone) => {
    if (!window.confirm('Cancel this dining table reservation?')) return;
    setCancellingId(bookingId);
    try {
      await api.cancelReservation(business.id, bookingId, phone);
      setFeedback({ type: 'success', text: 'Dining reservation cancelled successfully.' });
      if (onRefresh) await onRefresh();
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to cancel: ${err.message}` });
    } finally {
      setCancellingId(null);
    }
  };

  // Add New Table
  const handleAddTable = async (e) => {
    e.preventDefault();
    if (!newTable.name.trim()) return;

    setIsSubmitting(true);
    setFeedback(null);
    try {
      await api.createResource(business.id, {
        name: newTable.name.trim(),
        section: newTable.section.trim() || 'Main Dining',
        capacity: Number(newTable.capacity),
        min_party_size: Number(newTable.min_party_size),
        max_party_size: Number(newTable.max_party_size),
        resource_type: newTable.resource_type,
      });

      setFeedback({ type: 'success', text: `Table "${newTable.name.trim()}" registered to ${newTable.section}!` });
      setNewTable({
        name: '',
        section: 'Main Dining',
        capacity: 4,
        min_party_size: 2,
        max_party_size: 4,
        resource_type: 'table',
      });
      setIsAddTableModalOpen(false);
      if (onRefresh) await onRefresh();
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to add table: ${err.message}` });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Delete Table
  const handleDeleteTable = async (tableId, tableName) => {
    if (!window.confirm(`Delete "${tableName}"? Existing guest reservations will remain in history.`)) return;
    setIsSubmitting(true);
    try {
      await api.deleteResource(business.id, tableId);
      setFeedback({ type: 'success', text: `Table "${tableName}" removed from floor inventory.` });
      if (onRefresh) await onRefresh();
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to delete table: ${err.message}` });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Date Navigation
  const handlePrevDay = () => {
    setSelectedDate((prev) => addDaysToIsoString(prev, -1));
  };

  const handleNextDay = () => {
    setSelectedDate((prev) => addDaysToIsoString(prev, 1));
  };

  const handleToday = () => {
    setSelectedDate(getTodayIso());
  };

  const handleManualRefresh = async () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    try {
      if (onRefresh) {
        await onRefresh();
      }
      setFeedback({ type: 'success', text: 'Floor layout and dining reservations refreshed!' });
      setTimeout(() => setFeedback(null), 3000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to refresh: ${err.message}` });
    } finally {
      setIsRefreshing(false);
    }
  };

  // Filtered reservations for list view
  const searchFilteredReservations = useMemo(() => {
    if (!searchQuery.trim()) return activeReservations;
    const q = searchQuery.toLowerCase();
    return activeReservations.filter(
      (r) =>
        (r.customer_name && r.customer_name.toLowerCase().includes(q)) ||
        (r.customer_phone && r.customer_phone.includes(q)) ||
        (r.special_requests && r.special_requests.toLowerCase().includes(q)) ||
        (r.id && r.id.toLowerCase().includes(q))
    );
  }, [activeReservations, searchQuery]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', width: '100%' }}>
      {/* Feedback Banner */}
      {feedback && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-md)',
            background: feedback.type === 'success' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(244, 63, 94, 0.12)',
            border: `1px solid ${feedback.type === 'success' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
            color: feedback.type === 'success' ? 'var(--color-emerald)' : 'var(--color-rose)',
            fontSize: '0.85rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>{feedback.text}</span>
          <button onClick={() => setFeedback(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}>
            <X size={15} />
          </button>
        </div>
      )}

      {/* Control Header & Metrics Bar */}
      <div className="card" style={{ padding: '1.25rem 1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'rgba(16, 185, 129, 0.1)',
                  color: 'var(--color-emerald)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Utensils size={16} />
              </div>
              <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0, letterSpacing: '-0.02em' }}>
                Restaurant Dining Tables & Seating Floor
              </h2>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', marginTop: '3px', margin: 0 }}>
              Manage dining sections, table seating capacities, turnover shifts, and live customer dining reservations.
            </p>
          </div>

          {/* Quick Metrics */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                padding: '4px 10px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.76rem',
                color: 'var(--text-secondary)',
                fontWeight: 600,
              }}
            >
              <span>Dining Tables:</span>
              <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{tables.length}</strong>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-medium)',
                padding: '4px 10px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.76rem',
                color: 'var(--text-secondary)',
                fontWeight: 600,
              }}
            >
              <span>Total Covers / Capacity:</span>
              <strong style={{ color: 'var(--color-emerald)', fontFamily: 'var(--font-mono)' }}>{totalCovers} Guests</strong>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'rgba(16, 185, 129, 0.08)',
                border: '1px solid rgba(16, 185, 129, 0.25)',
                padding: '4px 10px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.76rem',
                color: 'var(--color-emerald)',
                fontWeight: 600,
              }}
            >
              <span>Today's Bookings:</span>
              <strong style={{ fontFamily: 'var(--font-mono)' }}>{todayReservations.length}</strong>
            </div>

            <button
              type="button"
              className="btn-primary"
              onClick={() => handleOpenBookingForTable()}
              style={{ display: 'flex', alignItems: 'center', gap: '5px', padding: '0.4rem 0.85rem', fontSize: '0.8rem', fontWeight: 600 }}
            >
              <Plus size={15} /> Book Dining Table
            </button>
          </div>
        </div>

        {/* Toolbar: Navigation Tabs & Section Selector */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '0.75rem',
            paddingTop: '0.85rem',
            borderTop: '1px solid var(--border-medium)',
          }}
        >
          {/* Main View Mode Selector */}
          <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
            <button
              type="button"
              className={`btn-secondary ${activeTab === 'floor' ? 'active' : ''}`}
              onClick={() => setActiveTab('floor')}
              style={{
                fontSize: '0.78rem',
                padding: '0.35rem 0.75rem',
                fontWeight: 600,
                background: activeTab === 'floor' ? '#ffffff' : 'var(--bg-surface-elevated)',
                color: activeTab === 'floor' ? '#07080a' : 'var(--text-secondary)',
              }}
            >
              <Grid size={13} /> 🏢 Table Floor & Grid
            </button>

            <button
              type="button"
              className={`btn-secondary ${activeTab === 'timeline' ? 'active' : ''}`}
              onClick={() => setActiveTab('timeline')}
              style={{
                fontSize: '0.78rem',
                padding: '0.35rem 0.75rem',
                fontWeight: 600,
                background: activeTab === 'timeline' ? '#ffffff' : 'var(--bg-surface-elevated)',
                color: activeTab === 'timeline' ? '#07080a' : 'var(--text-secondary)',
              }}
            >
              <Clock size={13} /> 🕒 Lunch & Dinner Shifts
            </button>

            <button
              type="button"
              className={`btn-secondary ${activeTab === 'reservations' ? 'active' : ''}`}
              onClick={() => setActiveTab('reservations')}
              style={{
                fontSize: '0.78rem',
                padding: '0.35rem 0.75rem',
                fontWeight: 600,
                background: activeTab === 'reservations' ? '#ffffff' : 'var(--bg-surface-elevated)',
                color: activeTab === 'reservations' ? '#07080a' : 'var(--text-secondary)',
              }}
            >
              <ListIcon size={13} /> Guest Reservations
            </button>

            <button
              type="button"
              className={`btn-secondary ${activeTab === 'tables' ? 'active' : ''}`}
              onClick={() => setActiveTab('tables')}
              style={{
                fontSize: '0.78rem',
                padding: '0.35rem 0.75rem',
                fontWeight: 600,
                background: activeTab === 'tables' ? '#ffffff' : 'var(--bg-surface-elevated)',
                color: activeTab === 'tables' ? '#07080a' : 'var(--text-secondary)',
              }}
            >
              <Layers size={13} /> Manage Tables
            </button>
          </div>

          {/* Section Filter & Date Navigator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            {activeTab === 'floor' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Filter size={13} color="var(--text-tertiary)" />
                <select
                  className="form-input"
                  value={selectedSection}
                  onChange={(e) => setSelectedSection(e.target.value)}
                  style={{ padding: '0.3rem 0.6rem', fontSize: '0.78rem', width: 'auto' }}
                >
                  {DINING_SECTIONS.map((sec) => (
                    <option key={sec} value={sec}>{sec}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Date Navigator */}
            {(activeTab === 'floor' || activeTab === 'timeline') && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <button type="button" className="btn-secondary" onClick={handlePrevDay} style={{ padding: '0.3rem 0.5rem' }}>
                  <ChevronLeft size={13} />
                </button>
                <button type="button" className="btn-secondary" onClick={handleToday} style={{ padding: '0.3rem 0.65rem', fontSize: '0.76rem', fontWeight: 600 }}>
                  Today
                </button>
                <button type="button" className="btn-secondary" onClick={handleNextDay} style={{ padding: '0.3rem 0.5rem' }}>
                  <ChevronRight size={13} />
                </button>
                <input
                  type="date"
                  className="form-input"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  style={{ padding: '0.25rem 0.5rem', fontSize: '0.78rem', width: 'auto' }}
                />
              </div>
            )}

            {onRefresh && (
              <button
                type="button"
                className="btn-secondary"
                onClick={handleManualRefresh}
                disabled={isRefreshing}
                title="Refresh floor layout and bookings"
                style={{
                  padding: '0.3rem 0.65rem',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  fontSize: '0.76rem',
                  fontWeight: 600,
                  cursor: isRefreshing ? 'wait' : 'pointer',
                  opacity: isRefreshing ? 0.7 : 1,
                }}
              >
                <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
                <span>{isRefreshing ? 'Refreshing...' : 'Refresh'}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* =========================================================================
         VIEW 1: VISUAL TABLE FLOOR & CAPACITY GRID
         ========================================================================= */}
      {activeTab === 'floor' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {filteredTables.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '3.5rem', color: 'var(--text-tertiary)' }}>
              No dining tables registered for section "{selectedSection}". Click "Add New Table" to configure your floor layout.
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
              {filteredTables.map((tbl) => {
                const dayBookings = getTableReservationsForDate(tbl.id, selectedDate);
                const isBooked = dayBookings.length > 0;

                return (
                  <div
                    key={tbl.id}
                    className="card"
                    style={{
                      padding: '1.15rem',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      gap: '0.85rem',
                      position: 'relative',
                      borderLeft: `4px solid ${isBooked ? '#f59e0b' : 'var(--color-emerald)'}`,
                    }}
                  >
                    <div>
                      {/* Top Row: Table Name & Status Badge */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '6px' }}>
                        <div>
                          <h4 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                            {tbl.name}
                          </h4>
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <MapPin size={11} /> {tbl.section || 'Main Dining'}
                          </div>
                        </div>

                        <span
                          style={{
                            fontSize: '0.68rem',
                            fontWeight: 700,
                            padding: '2px 8px',
                            borderRadius: 'var(--radius-full)',
                            background: isBooked ? 'rgba(245, 158, 11, 0.12)' : 'rgba(16, 185, 129, 0.12)',
                            color: isBooked ? '#f59e0b' : 'var(--color-emerald)',
                            border: `1px solid ${isBooked ? 'rgba(245, 158, 11, 0.3)' : 'rgba(16, 185, 129, 0.3)'}`,
                            letterSpacing: '0.04em',
                          }}
                        >
                          {isBooked ? `${dayBookings.length} RESERVATION${dayBookings.length > 1 ? 'S' : ''}` : 'AVAILABLE'}
                        </span>
                      </div>

                      {/* Capacity & Attributes */}
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '0.65rem' }}>
                        <span
                          style={{
                            fontSize: '0.72rem',
                            background: 'var(--bg-surface-elevated)',
                            border: '1px solid var(--border-medium)',
                            padding: '2px 7px',
                            borderRadius: '4px',
                            color: 'var(--text-secondary)',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                        >
                          <Users size={12} color="var(--color-emerald)" />
                          Seats {tbl.capacity} (Party: {tbl.min_party_size}–{tbl.max_party_size})
                        </span>

                        <span
                          style={{
                            fontSize: '0.72rem',
                            background: 'var(--bg-surface-elevated)',
                            border: '1px solid var(--border-medium)',
                            padding: '2px 7px',
                            borderRadius: '4px',
                            color: 'var(--text-tertiary)',
                          }}
                        >
                          {tbl.resource_type === 'booth'
                            ? 'Private Booth'
                            : tbl.resource_type === 'terrace'
                            ? 'Garden Patio'
                            : tbl.resource_type === 'private_room'
                            ? 'Private VIP'
                            : tbl.resource_type === 'bar'
                            ? 'Bar Counter'
                            : 'Standard Table'}
                        </span>
                      </div>

                      {/* Reservations on Selected Date */}
                      {dayBookings.length > 0 && (
                        <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', fontWeight: 700 }}>
                            Booked Slots ({selectedDate}):
                          </span>
                          {dayBookings.map((b) => (
                            <div
                              key={b.id}
                              style={{
                                fontSize: '0.74rem',
                                padding: '4px 8px',
                                background: 'rgba(245, 158, 11, 0.08)',
                                border: '1px solid rgba(245, 158, 11, 0.2)',
                                borderRadius: '4px',
                                color: 'var(--text-primary)',
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                              }}
                            >
                              <span>
                                <strong>{(b.start_time || '').slice(11, 16)}</strong> • {b.customer_name} ({b.party_size}p)
                              </span>
                              <button
                                type="button"
                                onClick={() => handleCancelReservation(b.id, b.customer_phone)}
                                style={{ background: 'none', border: 'none', color: '#f43f5e', cursor: 'pointer', padding: '1px 3px' }}
                                title="Cancel reservation"
                              >
                                <X size={12} />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Bottom Action */}
                    <div style={{ display: 'flex', gap: '6px', marginTop: '0.5rem' }}>
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => handleOpenBookingForTable(tbl)}
                        style={{ flex: 1, fontSize: '0.76rem', padding: '0.35rem 0.65rem', justifyContent: 'center' }}
                      >
                        <Plus size={13} /> Reserve Table
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
         VIEW 2: LUNCH & DINNER SHIFTS TIMELINE
         ========================================================================= */}
      {activeTab === 'timeline' && (
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          <div style={{ padding: '0.85rem 1.25rem', background: 'var(--bg-surface-elevated)', borderBottom: '1px solid var(--border-medium)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              🕒 Meal Service Timeline: {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' })}
            </span>
            <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
              Lunch Service: 12:00 PM – 03:00 PM • Dinner Service: 07:00 PM – 10:30 PM (90m turns)
            </span>
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '850px', textAlign: 'left' }}>
            <thead>
              <tr style={{ background: 'var(--bg-card)', borderBottom: '1px solid var(--border-medium)' }}>
                <th style={{ width: '220px', padding: '0.75rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', borderRight: '1px solid var(--border-medium)' }}>
                  DINING TABLE
                </th>
                {MEAL_TIMES.map((mt) => (
                  <th key={mt.time} style={{ padding: '0.6rem 0.4rem', fontSize: '0.72rem', textAlign: 'center', color: 'var(--text-secondary)', borderRight: '1px solid var(--border-medium)', minWidth: '65px' }}>
                    {mt.time}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tables.map((tbl, idx) => (
                <tr key={tbl.id} style={{ borderBottom: '1px solid var(--border-medium)', background: idx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.015)' }}>
                  <td style={{ padding: '0.75rem 1rem', borderRight: '1px solid var(--border-medium)' }}>
                    <div style={{ fontWeight: 600, fontSize: '0.84rem', color: 'var(--text-primary)' }}>{tbl.name}</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                      {tbl.section} • Seats {tbl.capacity}
                    </div>
                  </td>

                  {MEAL_TIMES.map((mt) => {
                    const dayBookings = getTableReservationsForDate(tbl.id, selectedDate);
                    // Match booking within this time window
                    const matched = dayBookings.find((b) => {
                      const startTime = (b.start_time || '').slice(11, 16);
                      const endTime = (b.end_time || '').slice(11, 16) || addMinutesToTime(startTime, 90);
                      return startTime <= mt.time && mt.time < endTime;
                    });

                    return (
                      <td
                        key={mt.time}
                        style={{
                          padding: '4px',
                          borderRight: '1px solid var(--border-medium)',
                          background: matched ? 'rgba(245, 158, 11, 0.15)' : 'transparent',
                          textAlign: 'center',
                          verticalAlign: 'middle',
                        }}
                      >
                        {matched ? (
                          <div
                            title={`Reserved for ${matched.customer_name} (${matched.party_size} guests)\n${matched.special_requests || 'No special requests'}`}
                            style={{
                              fontSize: '0.66rem',
                              fontWeight: 700,
                              color: '#f59e0b',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              padding: '2px',
                              borderRadius: '3px',
                              background: 'rgba(245, 158, 11, 0.2)',
                            }}
                          >
                            {matched.customer_name.split(' ')[0]} ({matched.party_size}p)
                          </div>
                        ) : (
                          <span style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)', opacity: 0.3 }}>•</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* =========================================================================
         VIEW 3: GUEST RESERVATIONS LOG
         ========================================================================= */}
      {activeTab === 'reservations' && (
        <div className="card" style={{ padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div style={{ position: 'relative', width: '300px' }}>
              <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)' }} />
              <input
                type="text"
                className="form-input"
                placeholder="Search guest name, phone, or request..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ paddingLeft: '32px', fontSize: '0.8rem' }}
              />
            </div>

            <button
              type="button"
              className="btn-primary"
              onClick={() => handleOpenBookingForTable()}
              style={{ fontSize: '0.78rem', padding: '0.35rem 0.85rem' }}
            >
              <Plus size={14} /> New Reservation
            </button>
          </div>

          {searchFilteredReservations.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-tertiary)' }}>
              No dining reservations found.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.82rem' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-surface-elevated)', borderBottom: '1px solid var(--border-medium)', color: 'var(--text-tertiary)', fontSize: '0.74rem' }}>
                    <th style={{ padding: '0.65rem 0.85rem' }}>BOOKING ID</th>
                    <th style={{ padding: '0.65rem 0.85rem' }}>GUEST NAME & PHONE</th>
                    <th style={{ padding: '0.65rem 0.85rem' }}>PARTY</th>
                    <th style={{ padding: '0.65rem 0.85rem' }}>TABLE & SECTION</th>
                    <th style={{ padding: '0.65rem 0.85rem' }}>DATE & TIME</th>
                    <th style={{ padding: '0.65rem 0.85rem' }}>GUEST REQUESTS</th>
                    <th style={{ padding: '0.65rem 0.85rem', textAlign: 'right' }}>ACTION</th>
                  </tr>
                </thead>
                <tbody>
                  {searchFilteredReservations.map((b) => {
                    const tbl = tables.find((t) => t.id === b.resource_id);
                    const isCancelling = cancellingId === b.id;

                    return (
                      <tr key={b.id} style={{ borderBottom: '1px solid var(--border-medium)' }}>
                        <td style={{ padding: '0.75rem 0.85rem', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--color-emerald)', fontWeight: 600 }}>
                          {b.id}
                        </td>
                        <td style={{ padding: '0.75rem 0.85rem' }}>
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{b.customer_name}</div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>{b.customer_phone}</div>
                        </td>
                        <td style={{ padding: '0.75rem 0.85rem' }}>
                          <span style={{ background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-emerald)', padding: '2px 7px', borderRadius: '4px', fontWeight: 600, fontSize: '0.74rem' }}>
                            👥 {b.party_size} Guests
                          </span>
                        </td>
                        <td style={{ padding: '0.75rem 0.85rem' }}>
                          <div style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{tbl?.name || 'Assigned Table'}</div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>{tbl?.section || 'Dining Room'}</div>
                        </td>
                        <td style={{ padding: '0.75rem 0.85rem' }}>
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                            {(b.start_time || '').slice(0, 10)}
                          </div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--color-emerald)', fontFamily: 'var(--font-mono)' }}>
                            {(b.start_time || '').slice(11, 16)} — {(b.end_time || '').slice(11, 16) || addMinutesToTime((b.start_time || '').slice(11, 16), 90)}
                          </div>
                        </td>
                        <td style={{ padding: '0.75rem 0.85rem', color: 'var(--text-secondary)', fontSize: '0.76rem', maxWidth: '240px' }}>
                          {b.special_requests || '—'}
                        </td>
                        <td style={{ padding: '0.75rem 0.85rem', textAlign: 'right' }}>
                          <button
                            type="button"
                            className="btn-secondary"
                            onClick={() => handleCancelReservation(b.id, b.customer_phone)}
                            disabled={isCancelling}
                            style={{ color: '#f43f5e', fontSize: '0.74rem', padding: '0.25rem 0.55rem' }}
                            title="Cancel reservation"
                          >
                            <Trash2 size={12} /> {isCancelling ? 'Cancelling...' : 'Cancel'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
         VIEW 4: MANAGE TABLES & SEATING CAPACITY
         ========================================================================= */}
      {activeTab === 'tables' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', alignItems: 'flex-start' }}>
          {/* Add Table Form */}
          <form onSubmit={handleAddTable} className="card">
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Plus size={18} color="var(--color-emerald)" />
              Add Dining Table / Seating Area
            </div>
            <div className="card-desc">
              Register bookable dining tables, booths, and patio areas for your restaurant.
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">Table Label / Identifier *</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Table 9 (Window Booth) or Patio 3"
                value={newTable.name}
                onChange={(e) => setNewTable((prev) => ({ ...prev, name: e.target.value }))}
                required
              />
            </div>

            <div className="form-grid" style={{ marginBottom: '1rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Dining Section</label>
                <select
                  className="form-input"
                  value={newTable.section}
                  onChange={(e) => setNewTable((prev) => ({ ...prev, section: e.target.value }))}
                >
                  <option value="Main Dining">Main Dining</option>
                  <option value="Outdoor Patio">Outdoor Patio</option>
                  <option value="Private Dining Room">Private Dining Room</option>
                  <option value="Bar Counter">Bar Counter</option>
                  <option value="Terrace Garden">Terrace Garden</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Seating Type</label>
                <select
                  className="form-input"
                  value={newTable.resource_type}
                  onChange={(e) => setNewTable((prev) => ({ ...prev, resource_type: e.target.value }))}
                >
                  {TABLE_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-grid" style={{ marginBottom: '1.25rem', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
              <div className="form-group">
                <label className="form-label">Max Seats</label>
                <input
                  type="number"
                  className="form-input"
                  min="1"
                  max="30"
                  value={newTable.capacity}
                  onChange={(e) => setNewTable((prev) => ({ ...prev, capacity: e.target.value }))}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Min Party</label>
                <input
                  type="number"
                  className="form-input"
                  min="1"
                  max="30"
                  value={newTable.min_party_size}
                  onChange={(e) => setNewTable((prev) => ({ ...prev, min_party_size: e.target.value }))}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Max Party</label>
                <input
                  type="number"
                  className="form-input"
                  min="1"
                  max="30"
                  value={newTable.max_party_size}
                  onChange={(e) => setNewTable((prev) => ({ ...prev, max_party_size: e.target.value }))}
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn-primary"
              disabled={isSubmitting}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              <Plus size={16} /> {isSubmitting ? 'Registering...' : 'Register Table to Floor'}
            </button>
          </form>

          {/* Active Tables List */}
          <div className="card">
            <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Registered Tables ({tables.length})</span>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-tertiary)', fontWeight: 500 }}>
                {totalCovers} total seats
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', maxHeight: '420px', overflowY: 'auto', marginTop: '0.75rem' }}>
              {tables.map((tbl) => (
                <div
                  key={tbl.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '0.65rem 0.85rem',
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-medium)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.84rem' }}>{tbl.name}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '2px', display: 'flex', gap: '8px' }}>
                      <span>📍 {tbl.section}</span>
                      <span>👥 Capacity: {tbl.capacity} ({tbl.min_party_size}–{tbl.max_party_size} guests)</span>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleDeleteTable(tbl.id, tbl.name)}
                    style={{ background: 'none', border: 'none', color: '#f43f5e', cursor: 'pointer', padding: '4px' }}
                    title={`Delete ${tbl.name}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
         NEW DINING RESERVATION MODAL
         ========================================================================= */}
      {isNewBookingModalOpen && (
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
            className="card"
            style={{
              width: '100%',
              maxWidth: '520px',
              padding: '1.75rem',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-medium)',
              boxShadow: 'var(--shadow-card-elevated)',
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{ width: '30px', height: '30px', borderRadius: '6px', background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-emerald)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Utensils size={16} />
                </div>
                <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Reserve Dining Table
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsNewBookingModalOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer', padding: '4px' }}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateReservation} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Guest Full Name *</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Vikram Malhotra"
                  value={newBooking.customer_name}
                  onChange={(e) => setNewBooking((prev) => ({ ...prev, customer_name: e.target.value }))}
                  required
                />
              </div>

              <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Contact Phone *</label>
                  <input
                    type="tel"
                    className="form-input"
                    placeholder="e.g. +91 98765 43210"
                    value={newBooking.customer_phone}
                    onChange={(e) => setNewBooking((prev) => ({ ...prev, customer_phone: e.target.value }))}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Party Size (Guests) *</label>
                  <input
                    type="number"
                    className="form-input"
                    min="1"
                    max="20"
                    value={newBooking.party_size}
                    onChange={(e) => setNewBooking((prev) => ({ ...prev, party_size: e.target.value }))}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Assigned Table *</label>
                <select
                  className="form-input"
                  value={newBooking.resource_id}
                  onChange={(e) => setNewBooking((prev) => ({ ...prev, resource_id: e.target.value }))}
                  required
                >
                  <option value="">Select a dining table...</option>
                  {tables.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.section} • Seats {t.capacity})
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Date *</label>
                  <input
                    type="date"
                    className="form-input"
                    value={newBooking.reservation_date}
                    onChange={(e) => setNewBooking((prev) => ({ ...prev, reservation_date: e.target.value }))}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Meal Service Time *</label>
                  <select
                    className="form-input"
                    value={newBooking.start_time}
                    onChange={(e) => setNewBooking((prev) => ({ ...prev, start_time: e.target.value }))}
                  >
                    {MEAL_TIMES.map((mt) => (
                      <option key={mt.time} value={mt.time}>{mt.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Dining Duration / Table Turn</label>
                <select
                  className="form-input"
                  value={newBooking.duration_minutes}
                  onChange={(e) => setNewBooking((prev) => ({ ...prev, duration_minutes: Number(e.target.value) }))}
                >
                  <option value={60}>60 minutes (Quick Dining)</option>
                  <option value={90}>90 minutes (Standard Dinner Service)</option>
                  <option value={120}>120 minutes (Leisure / Banquet)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Special Seating / Dietary Requests</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Window booth, High chair needed, Anniversary cake"
                  value={newBooking.special_requests}
                  onChange={(e) => setNewBooking((prev) => ({ ...prev, special_requests: e.target.value }))}
                />
              </div>

              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setIsNewBookingModalOpen(false)}
                  style={{ flex: 1, justifyContent: 'center' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={isSubmitting}
                  style={{ flex: 2, justifyContent: 'center' }}
                >
                  {isSubmitting ? 'Confirming...' : 'Confirm Table Reservation'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
