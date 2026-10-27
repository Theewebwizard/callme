import React, { useState, useMemo } from 'react';
import {
  Calendar as CalendarIcon,
  Clock,
  Users,
  ChevronLeft,
  ChevronRight,
  Plus,
  Trash2,
  CheckCircle2,
  AlertCircle,
  X,
  Filter,
  Grid,
  List as ListIcon,
  RefreshCw,
  Phone,
  User,
  FileText,
  MapPin,
} from 'lucide-react';
import { api } from '../api';

/**
 * Interactive Visual Booking Calendar & Timeline Grid
 * Allows receptionists to view occupied nights and reserved tables,
 * inspect guest reservation details, and create first-party bookings.
 */
export default function BookingCalendarView({
  business,
  resources = [],
  reservations = [],
  onRefresh,
}) {
  const [viewMode, setViewMode] = useState('timeline'); // 'timeline' (multi-day), 'day' (hourly), 'list'
  const [selectedDate, setSelectedDate] = useState(() => {
    const today = new Date();
    return today.toISOString().slice(0, 10);
  });
  const [filterType, setFilterType] = useState('all'); // 'all', 'table', 'room', 'clinic_room'
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [isNewModalOpen, setIsNewModalOpen] = useState(false);
  const [cancellingId, setCancellingId] = useState(null);
  const [feedback, setFeedback] = useState(null);

  // New Booking Form State
  const [newBooking, setNewBooking] = useState({
    customer_name: '',
    customer_phone: '',
    resource_id: '',
    resource_type: 'table',
    start_date: new Date().toISOString().slice(0, 10),
    start_time: '19:00',
    end_date: new Date().toISOString().slice(0, 10),
    end_time: '21:00',
    party_size: 2,
    special_requests: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Filtered resources
  const filteredResources = useMemo(() => {
    if (filterType === 'all') return resources;
    return resources.filter((r) => r.resource_type === filterType);
  }, [resources, filterType]);

  // Generate 7 days for the timeline view starting from selectedDate
  const timelineDays = useMemo(() => {
    const days = [];
    const base = new Date(selectedDate + 'T00:00:00');
    for (let i = 0; i < 7; i++) {
      const d = new Date(base);
      d.setDate(base.getDate() + i);
      const iso = d.toISOString().slice(0, 10);
      const dayName = d.toLocaleDateString('en-US', { weekday: 'short' });
      const monthDay = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      const isToday = iso === new Date().toISOString().slice(0, 10);
      days.push({ date: iso, dayName, monthDay, isToday, rawDate: d });
    }
    return days;
  }, [selectedDate]);

  // Hourly slots for Day View (from 09:00 to 22:00)
  const hourlySlots = useMemo(() => {
    const slots = [];
    for (let hour = 9; hour <= 22; hour++) {
      slots.push(`${hour.toString().padStart(2, '0')}:00`);
    }
    return slots;
  }, []);

  // Quick Date Navigation Helpers
  const handlePrev = () => {
    const d = new Date(selectedDate + 'T00:00:00');
    if (viewMode === 'timeline') {
      d.setDate(d.getDate() - 7);
    } else {
      d.setDate(d.getDate() - 1);
    }
    setSelectedDate(d.toISOString().slice(0, 10));
  };

  const handleNext = () => {
    const d = new Date(selectedDate + 'T00:00:00');
    if (viewMode === 'timeline') {
      d.setDate(d.getDate() + 7);
    } else {
      d.setDate(d.getDate() + 1);
    }
    setSelectedDate(d.toISOString().slice(0, 10));
  };

  const handleToday = () => {
    setSelectedDate(new Date().toISOString().slice(0, 10));
  };

  // Helper: Find reservations for a specific resource and date
  const getReservationsForResourceAndDate = (resourceId, dateStr) => {
    return reservations.filter((b) => {
      if (b.status === 'cancelled') return false;
      // Match by resource_id or resource_name
      const resMatch = b.resource_id === resourceId;
      if (!resMatch && b.resource_id) return false;

      // Check date range
      const bStart = (b.start_time || '').slice(0, 10);
      const bEnd = (b.end_time || '').slice(0, 10);
      if (bStart && bEnd && bStart <= dateStr && dateStr <= bEnd) {
        return true;
      }
      return bStart === dateStr;
    });
  };

  // Helper: Find reservations for an hourly slot in Day View
  const getReservationsForResourceAndHour = (resourceId, dateStr, hourStr) => {
    const slotHour = parseInt(hourStr.split(':')[0], 10);
    return reservations.filter((b) => {
      if (b.status === 'cancelled') return false;
      if (b.resource_id && b.resource_id !== resourceId) return false;

      const bStart = (b.start_time || '').slice(0, 10);
      if (bStart !== dateStr) return false;

      const timePart = (b.start_time || '').includes('T')
        ? b.start_time.split('T')[1]
        : b.start_time.split(' ')[1] || '00:00';
      const bStartHour = parseInt(timePart.split(':')[0], 10);

      const endTimePart = (b.end_time || '').includes('T')
        ? b.end_time.split('T')[1]
        : b.end_time.split(' ')[1] || '23:59';
      const bEndHour = parseInt(endTimePart.split(':')[0], 10);

      return slotHour >= bStartHour && slotHour < (bEndHour || bStartHour + 1);
    });
  };

  // Open Quick Booking Modal with defaults
  const handleOpenNewModal = (resource = null, date = null, hour = null) => {
    const targetResource = resource || (filteredResources.length > 0 ? filteredResources[0] : null);
    const targetDate = date || selectedDate;
    const startH = hour ? hour : (targetResource?.resource_type === 'room' ? '15:00' : '19:00');
    const endH = hour
      ? `${(parseInt(hour.split(':')[0], 10) + 1).toString().padStart(2, '0')}:00`
      : (targetResource?.resource_type === 'room' ? '11:00' : '21:00');

    let nextDay = targetDate;
    if (targetResource?.resource_type === 'room') {
      const d = new Date(targetDate + 'T00:00:00');
      d.setDate(d.getDate() + 1);
      nextDay = d.toISOString().slice(0, 10);
    }

    setNewBooking({
      customer_name: '',
      customer_phone: '',
      resource_id: targetResource ? targetResource.id : '',
      resource_type: targetResource ? targetResource.resource_type : 'table',
      start_date: targetDate,
      start_time: startH,
      end_date: targetResource?.resource_type === 'room' ? nextDay : targetDate,
      end_time: endH,
      party_size: targetResource ? Math.max(1, targetResource.min_party_size) : 2,
      special_requests: '',
    });
    setIsNewModalOpen(true);
  };

  // Handle Form Submit for New Reservation
  const handleCreateReservation = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setFeedback(null);

    try {
      const startIso = `${newBooking.start_date}T${newBooking.start_time}:00`;
      const endIso = `${newBooking.end_date}T${newBooking.end_time}:00`;

      const selectedRes = resources.find((r) => r.id === newBooking.resource_id);

      await api.createReservation(business.id, {
        customer_name: newBooking.customer_name,
        customer_phone: newBooking.customer_phone,
        party_size: parseInt(newBooking.party_size, 10) || 1,
        start_time: startIso,
        end_time: endIso,
        resource_id: newBooking.resource_id || undefined,
        resource_type: selectedRes?.resource_type || newBooking.resource_type,
        section: selectedRes?.section,
        special_requests: newBooking.special_requests || undefined,
        status: 'confirmed',
      });

      setFeedback({ type: 'success', text: `Reservation confirmed for ${newBooking.customer_name}!` });
      setIsNewModalOpen(false);
      if (onRefresh) onRefresh();
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      console.error('Reservation creation failed:', err);
      setFeedback({ type: 'error', text: `Failed to create booking: ${err.message}` });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Cancel Reservation
  const handleCancelBooking = async (bookingId, phone) => {
    if (!window.confirm('Are you sure you want to cancel this booking?')) return;
    setCancellingId(bookingId);
    try {
      await api.cancelReservation(business.id, bookingId, phone);
      setFeedback({ type: 'success', text: 'Booking cancelled successfully.' });
      setSelectedBooking(null);
      if (onRefresh) onRefresh();
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      console.error('Failed to cancel reservation:', err);
      setFeedback({ type: 'error', text: `Failed to cancel booking: ${err.message}` });
    } finally {
      setCancellingId(null);
    }
  };

  // Active bookings count
  const activeBookingsCount = useMemo(() => {
    return reservations.filter((b) => b.status !== 'cancelled').length;
  }, [reservations]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '100%' }}>
      {/* Feedback Banner */}
      {feedback && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-md)',
            background: feedback.type === 'success' ? 'var(--emerald-100)' : 'var(--rose-100)',
            color: feedback.type === 'success' ? 'var(--emerald-700)' : 'var(--rose-700)',
            fontSize: '0.875rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>{feedback.text}</span>
          <button
            onClick={() => setFeedback(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Control Header & Toolbar */}
      <div
        className="card"
        style={{
          padding: '1.25rem 1.5rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem',
          border: '1px solid var(--slate-200)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '1rem',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CalendarIcon size={20} color="var(--sky-600)" />
              <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--slate-900)', margin: 0 }}>
                Interactive Booking Calendar & Timeline
              </h3>
            </div>
            <p style={{ fontSize: '0.82rem', color: 'var(--slate-500)', marginTop: '2px', margin: 0 }}>
              Live occupancy grid for rooms and dining tables. Inspect occupied nights, seatings, and guest reservations.
            </p>
          </div>

          {/* Quick Metrics */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'var(--slate-100)',
                padding: '4px 10px',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.78rem',
                color: 'var(--slate-700)',
                fontWeight: 600,
              }}
            >
              <span>Total Resources:</span>
              <strong style={{ color: 'var(--slate-900)' }}>{resources.length}</strong>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'var(--emerald-100)',
                padding: '4px 10px',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.78rem',
                color: 'var(--emerald-700)',
                fontWeight: 600,
              }}
            >
              <span>Confirmed Bookings:</span>
              <strong>{activeBookingsCount}</strong>
            </div>

            <button
              type="button"
              className="btn-primary"
              onClick={() => handleOpenNewModal()}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '0.45rem 0.9rem',
                fontSize: '0.85rem',
                fontWeight: 700,
              }}
            >
              <Plus size={16} /> New Booking
            </button>
          </div>
        </div>

        {/* Toolbar: Navigation, View Toggles, Category Filter */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '0.75rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid var(--slate-100)',
          }}
        >
          {/* Date Navigator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn-secondary"
              onClick={handlePrev}
              title="Previous Range"
              style={{ padding: '0.35rem 0.55rem' }}
            >
              <ChevronLeft size={16} />
            </button>

            <button
              type="button"
              className="btn-secondary"
              onClick={handleToday}
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem', fontWeight: 700 }}
            >
              Today
            </button>

            <button
              type="button"
              className="btn-secondary"
              onClick={handleNext}
              title="Next Range"
              style={{ padding: '0.35rem 0.55rem' }}
            >
              <ChevronRight size={16} />
            </button>

            <input
              type="date"
              className="form-input"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              style={{ padding: '0.3rem 0.6rem', fontSize: '0.82rem', width: 'auto' }}
            />

            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--slate-800)', marginLeft: '4px' }}>
              {viewMode === 'timeline'
                ? `${timelineDays[0]?.monthDay} — ${timelineDays[6]?.monthDay}, ${new Date(selectedDate).getFullYear()}`
                : new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-US', {
                    weekday: 'long',
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })}
            </span>
          </div>

          {/* Filters & View Modes */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            {/* Resource Type Filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Filter size={14} color="var(--slate-400)" />
              <select
                className="form-input"
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem', width: 'auto' }}
              >
                <option value="all">All Types ({resources.length})</option>
                <option value="room">🏨 Hotel Rooms & Suites</option>
                <option value="table">🍽️ Dining Tables</option>
                <option value="clinic_room">🩺 Clinical Suites</option>
              </select>
            </div>

            {/* View Mode Toggle Buttons */}
            <div
              style={{
                display: 'flex',
                background: 'var(--slate-100)',
                borderRadius: 'var(--radius-sm)',
                padding: '2px',
                border: '1px solid var(--slate-200)',
              }}
            >
              <button
                type="button"
                onClick={() => setViewMode('timeline')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '4px 10px',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  background: viewMode === 'timeline' ? 'white' : 'transparent',
                  color: viewMode === 'timeline' ? 'var(--sky-600)' : 'var(--slate-600)',
                  boxShadow: viewMode === 'timeline' ? 'var(--shadow-sm)' : 'none',
                }}
              >
                <Grid size={13} /> Multi-Day
              </button>

              <button
                type="button"
                onClick={() => setViewMode('day')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '4px 10px',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  background: viewMode === 'day' ? 'white' : 'transparent',
                  color: viewMode === 'day' ? 'var(--sky-600)' : 'var(--slate-600)',
                  boxShadow: viewMode === 'day' ? 'var(--shadow-sm)' : 'none',
                }}
              >
                <Clock size={13} /> Day Slots
              </button>

              <button
                type="button"
                onClick={() => setViewMode('list')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '4px 10px',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  background: viewMode === 'list' ? 'white' : 'transparent',
                  color: viewMode === 'list' ? 'var(--sky-600)' : 'var(--slate-600)',
                  boxShadow: viewMode === 'list' ? 'var(--shadow-sm)' : 'none',
                }}
              >
                <ListIcon size={13} /> List View
              </button>
            </div>

            {onRefresh && (
              <button
                type="button"
                className="btn-secondary"
                onClick={onRefresh}
                title="Refresh schedule"
                style={{ padding: '0.35rem 0.55rem' }}
              >
                <RefreshCw size={14} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* =========================================================================
         VIEW 1: MULTI-DAY / NIGHTS TIMELINE GRID
         ========================================================================= */}
      {viewMode === 'timeline' && (
        <div
          className="card"
          style={{
            padding: 0,
            overflowX: 'auto',
            border: '1px solid var(--slate-200)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          {filteredResources.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--slate-500)' }}>
              No resources found for the selected filter. Register a room or table below to enable timeline scheduling.
            </div>
          ) : (
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                minWidth: '780px',
                textAlign: 'left',
              }}
            >
              <thead>
                <tr style={{ background: 'var(--slate-50)', borderBottom: '2px solid var(--slate-200)' }}>
                  <th
                    style={{
                      width: '230px',
                      padding: '0.85rem 1rem',
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      color: 'var(--slate-700)',
                      borderRight: '1px solid var(--slate-200)',
                    }}
                  >
                    RESOURCE (ROOM / TABLE)
                  </th>
                  {timelineDays.map((td) => (
                    <th
                      key={td.date}
                      style={{
                        padding: '0.65rem 0.5rem',
                        fontSize: '0.78rem',
                        textAlign: 'center',
                        color: td.isToday ? 'var(--sky-700)' : 'var(--slate-700)',
                        background: td.isToday ? 'var(--sky-50)' : 'transparent',
                        borderRight: '1px solid var(--slate-200)',
                        minWidth: '105px',
                      }}
                    >
                      <div style={{ fontWeight: 800, fontSize: '0.82rem' }}>{td.dayName}</div>
                      <div
                        style={{
                          fontSize: '0.72rem',
                          color: td.isToday ? 'var(--sky-600)' : 'var(--slate-500)',
                          fontWeight: td.isToday ? 700 : 500,
                        }}
                      >
                        {td.monthDay}
                      </div>
                      {td.isToday && (
                        <span
                          style={{
                            display: 'inline-block',
                            marginTop: '2px',
                            fontSize: '0.65rem',
                            background: 'var(--sky-500)',
                            color: 'white',
                            padding: '1px 6px',
                            borderRadius: '10px',
                            fontWeight: 700,
                          }}
                        >
                          TODAY
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredResources.map((res, idx) => (
                  <tr
                    key={res.id}
                    style={{
                      borderBottom: '1px solid var(--slate-200)',
                      background: idx % 2 === 0 ? 'white' : 'var(--slate-50)',
                    }}
                  >
                    {/* Resource Header Cell */}
                    <td
                      style={{
                        padding: '0.85rem 1rem',
                        borderRight: '1px solid var(--slate-200)',
                        verticalAlign: 'top',
                      }}
                    >
                      <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--slate-900)' }}>
                        {res.name}
                      </div>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          marginTop: '4px',
                          flexWrap: 'wrap',
                        }}
                      >
                        <span
                          style={{
                            fontSize: '0.7rem',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            fontWeight: 700,
                            background:
                              res.resource_type === 'room'
                                ? 'var(--sky-100)'
                                : res.resource_type === 'table'
                                ? 'var(--emerald-100)'
                                : 'var(--slate-200)',
                            color:
                              res.resource_type === 'room'
                                ? 'var(--sky-700)'
                                : res.resource_type === 'table'
                                ? 'var(--emerald-700)'
                                : 'var(--slate-700)',
                          }}
                        >
                          {res.resource_type === 'room' ? 'Room' : res.resource_type === 'table' ? 'Table' : 'Suite'}
                        </span>
                        {res.section && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--slate-500)' }}>
                            • {res.section}
                          </span>
                        )}
                        <span style={{ fontSize: '0.72rem', color: 'var(--slate-500)' }}>
                          • {res.min_party_size}–{res.max_party_size} pax
                        </span>
                      </div>
                    </td>

                    {/* Timeline Day Columns */}
                    {timelineDays.map((td) => {
                      const dayBookings = getReservationsForResourceAndDate(res.id, td.date);
                      const isOccupied = dayBookings.length > 0;

                      return (
                        <td
                          key={td.date}
                          style={{
                            padding: '0.5rem',
                            borderRight: '1px solid var(--slate-200)',
                            verticalAlign: 'top',
                            background: td.isToday ? 'rgba(240, 249, 255, 0.4)' : 'transparent',
                            position: 'relative',
                            minHeight: '60px',
                          }}
                        >
                          {isOccupied ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                              {dayBookings.map((b) => (
                                <div
                                  key={b.id}
                                  onClick={() => setSelectedBooking(b)}
                                  style={{
                                    padding: '5px 8px',
                                    borderRadius: '6px',
                                    background:
                                      b.status === 'confirmed'
                                        ? 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)'
                                        : 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
                                    color: 'white',
                                    fontSize: '0.74rem',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                                    transition: 'transform 0.15s ease',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                  }}
                                  title={`Guest: ${b.customer_name} (${b.party_size} guests)\nClick to inspect details`}
                                >
                                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <span style={{ fontWeight: 700 }}>{b.customer_name}</span>
                                    <span style={{ fontSize: '0.68rem', opacity: 0.9 }}>👥 {b.party_size}</span>
                                  </div>
                                  <div style={{ fontSize: '0.68rem', opacity: 0.85, marginTop: '2px' }}>
                                    {b.start_time?.includes('T') ? b.start_time.split('T')[1].slice(0, 5) : ''}
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div
                              onClick={() => handleOpenNewModal(res, td.date)}
                              style={{
                                height: '100%',
                                minHeight: '44px',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                cursor: 'pointer',
                                borderRadius: '4px',
                                transition: 'background 0.15s ease',
                                color: 'var(--slate-400)',
                              }}
                              className="calendar-empty-slot"
                              title={`Empty slot: Click to book ${res.name} on ${td.date}`}
                            >
                              <span style={{ fontSize: '0.7rem', opacity: 0.4 }}>+ Reserve</span>
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* =========================================================================
         VIEW 2: SINGLE-DAY HOURLY SLOTS SCHEDULE
         ========================================================================= */}
      {viewMode === 'day' && (
        <div
          className="card"
          style={{
            padding: 0,
            overflowX: 'auto',
            border: '1px solid var(--slate-200)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          {filteredResources.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--slate-500)' }}>
              No resources available for this view.
            </div>
          ) : (
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                minWidth: '950px',
                textAlign: 'left',
              }}
            >
              <thead>
                <tr style={{ background: 'var(--slate-50)', borderBottom: '2px solid var(--slate-200)' }}>
                  <th
                    style={{
                      width: '200px',
                      padding: '0.85rem 1rem',
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      color: 'var(--slate-700)',
                      borderRight: '1px solid var(--slate-200)',
                    }}
                  >
                    RESOURCE
                  </th>
                  {hourlySlots.map((hour) => (
                    <th
                      key={hour}
                      style={{
                        padding: '0.65rem 0.4rem',
                        fontSize: '0.75rem',
                        textAlign: 'center',
                        color: 'var(--slate-700)',
                        borderRight: '1px solid var(--slate-200)',
                        minWidth: '65px',
                        fontWeight: 700,
                      }}
                    >
                      {hour}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredResources.map((res, idx) => (
                  <tr
                    key={res.id}
                    style={{
                      borderBottom: '1px solid var(--slate-200)',
                      background: idx % 2 === 0 ? 'white' : 'var(--slate-50)',
                    }}
                  >
                    <td
                      style={{
                        padding: '0.75rem 1rem',
                        borderRight: '1px solid var(--slate-200)',
                        verticalAlign: 'top',
                      }}
                    >
                      <div style={{ fontWeight: 700, fontSize: '0.86rem', color: 'var(--slate-900)' }}>
                        {res.name}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--slate-500)', marginTop: '2px' }}>
                        {res.section || 'General'} • {res.capacity} seats
                      </div>
                    </td>

                    {hourlySlots.map((hour) => {
                      const hourBookings = getReservationsForResourceAndHour(res.id, selectedDate, hour);
                      const isOccupied = hourBookings.length > 0;

                      return (
                        <td
                          key={hour}
                          style={{
                            padding: '0.4rem',
                            borderRight: '1px solid var(--slate-200)',
                            verticalAlign: 'top',
                            minHeight: '50px',
                          }}
                        >
                          {isOccupied ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                              {hourBookings.map((b) => (
                                <div
                                  key={b.id}
                                  onClick={() => setSelectedBooking(b)}
                                  style={{
                                    padding: '4px 6px',
                                    borderRadius: '5px',
                                    background: 'var(--sky-500)',
                                    color: 'white',
                                    fontSize: '0.7rem',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                  }}
                                  title={`${b.customer_name} (${b.party_size} guests)`}
                                >
                                  {b.customer_name}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div
                              onClick={() => handleOpenNewModal(res, selectedDate, hour)}
                              style={{
                                height: '100%',
                                minHeight: '36px',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                cursor: 'pointer',
                                borderRadius: '4px',
                                color: 'var(--slate-300)',
                                fontSize: '0.65rem',
                              }}
                              className="calendar-empty-slot"
                              title={`Empty: Click to reserve at ${hour}`}
                            >
                              +
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* =========================================================================
         VIEW 3: DETAILED TABULAR / AGENDA VIEW
         ========================================================================= */}
      {viewMode === 'list' && (
        <div
          className="card"
          style={{
            padding: 0,
            overflowX: 'auto',
            border: '1px solid var(--slate-200)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          {reservations.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--slate-500)' }}>
              No active reservations committed to the database.
            </div>
          ) : (
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                textAlign: 'left',
                fontSize: '0.85rem',
              }}
            >
              <thead>
                <tr style={{ background: 'var(--slate-50)', borderBottom: '2px solid var(--slate-200)' }}>
                  <th style={{ padding: '0.85rem 1rem', color: 'var(--slate-700)', fontWeight: 700 }}>GUEST</th>
                  <th style={{ padding: '0.85rem 1rem', color: 'var(--slate-700)', fontWeight: 700 }}>PHONE</th>
                  <th style={{ padding: '0.85rem 1rem', color: 'var(--slate-700)', fontWeight: 700 }}>RESOURCE</th>
                  <th style={{ padding: '0.85rem 1rem', color: 'var(--slate-700)', fontWeight: 700 }}>START TIME</th>
                  <th style={{ padding: '0.85rem 1rem', color: 'var(--slate-700)', fontWeight: 700 }}>END TIME</th>
                  <th style={{ padding: '0.85rem 1rem', color: 'var(--slate-700)', fontWeight: 700 }}>GUESTS</th>
                  <th style={{ padding: '0.85rem 1rem', color: 'var(--slate-700)', fontWeight: 700 }}>STATUS</th>
                  <th style={{ padding: '0.85rem 1rem', color: 'var(--slate-700)', fontWeight: 700, textAlign: 'right' }}>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {reservations.map((b, idx) => (
                  <tr
                    key={b.id}
                    style={{
                      borderBottom: '1px solid var(--slate-200)',
                      background: idx % 2 === 0 ? 'white' : 'var(--slate-50)',
                    }}
                  >
                    <td style={{ padding: '0.85rem 1rem', fontWeight: 700, color: 'var(--slate-900)' }}>
                      {b.customer_name}
                    </td>
                    <td style={{ padding: '0.85rem 1rem', color: 'var(--slate-600)' }}>
                      {b.customer_phone}
                    </td>
                    <td style={{ padding: '0.85rem 1rem', color: 'var(--slate-800)', fontWeight: 600 }}>
                      {b.resource_name || b.resource_id || 'Auto-Assigned'}
                    </td>
                    <td style={{ padding: '0.85rem 1rem', color: 'var(--slate-700)' }}>
                      {b.start_time?.replace('T', ' ').slice(0, 16)}
                    </td>
                    <td style={{ padding: '0.85rem 1rem', color: 'var(--slate-700)' }}>
                      {b.end_time?.replace('T', ' ').slice(0, 16)}
                    </td>
                    <td style={{ padding: '0.85rem 1rem', color: 'var(--slate-700)' }}>
                      {b.party_size}
                    </td>
                    <td style={{ padding: '0.85rem 1rem' }}>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          padding: '2px 8px',
                          borderRadius: '10px',
                          fontWeight: 700,
                          background:
                            b.status === 'confirmed'
                              ? 'var(--emerald-100)'
                              : b.status === 'cancelled'
                              ? 'var(--rose-100)'
                              : 'var(--amber-100)',
                          color:
                            b.status === 'confirmed'
                              ? 'var(--emerald-700)'
                              : b.status === 'cancelled'
                              ? 'var(--rose-700)'
                              : 'var(--amber-800)',
                        }}
                      >
                        {b.status}
                      </span>
                    </td>
                    <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => setSelectedBooking(b)}
                          style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
                        >
                          Details
                        </button>
                        {b.status !== 'cancelled' && (
                          <button
                            type="button"
                            onClick={() => handleCancelBooking(b.id, b.customer_phone)}
                            disabled={cancellingId === b.id}
                            style={{
                              padding: '0.3rem 0.6rem',
                              fontSize: '0.75rem',
                              background: 'none',
                              border: '1px solid var(--rose-200)',
                              borderRadius: 'var(--radius-sm)',
                              color: 'var(--rose-600)',
                              cursor: 'pointer',
                            }}
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* =========================================================================
         MODAL 1: RESERVATION DETAILS & INSPECTION MODAL
         ========================================================================= */}
      {selectedBooking && (
        <div className="modal-backdrop" onClick={() => setSelectedBooking(null)}>
          <div
            className="modal-card"
            style={{ maxWidth: '480px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                borderBottom: '1px solid var(--slate-200)',
                paddingBottom: '0.75rem',
                marginBottom: '1rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={20} color="var(--emerald-500)" />
                <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: 'var(--slate-900)' }}>
                  Reservation Details
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedBooking(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--slate-400)' }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.88rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <User size={16} color="var(--slate-400)" />
                <span style={{ color: 'var(--slate-500)', width: '90px' }}>Guest Name:</span>
                <strong style={{ color: 'var(--slate-900)' }}>{selectedBooking.customer_name}</strong>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Phone size={16} color="var(--slate-400)" />
                <span style={{ color: 'var(--slate-500)', width: '90px' }}>Contact Phone:</span>
                <strong style={{ color: 'var(--slate-900)' }}>{selectedBooking.customer_phone}</strong>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Users size={16} color="var(--slate-400)" />
                <span style={{ color: 'var(--slate-500)', width: '90px' }}>Party Size:</span>
                <strong style={{ color: 'var(--slate-900)' }}>{selectedBooking.party_size} guests</strong>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <MapPin size={16} color="var(--slate-400)" />
                <span style={{ color: 'var(--slate-500)', width: '90px' }}>Assigned To:</span>
                <strong style={{ color: 'var(--slate-900)' }}>
                  {selectedBooking.resource_name || selectedBooking.resource_id || 'Standard Inventory'}
                </strong>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Clock size={16} color="var(--slate-400)" />
                <span style={{ color: 'var(--slate-500)', width: '90px' }}>Start Time:</span>
                <strong style={{ color: 'var(--slate-900)' }}>
                  {selectedBooking.start_time?.replace('T', ' ').slice(0, 16)}
                </strong>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Clock size={16} color="var(--slate-400)" />
                <span style={{ color: 'var(--slate-500)', width: '90px' }}>End Time:</span>
                <strong style={{ color: 'var(--slate-900)' }}>
                  {selectedBooking.end_time?.replace('T', ' ').slice(0, 16)}
                </strong>
              </div>

              {selectedBooking.special_requests && (
                <div style={{ marginTop: '0.5rem', padding: '0.75rem', background: 'var(--slate-50)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--slate-200)' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--slate-500)', marginBottom: '2px' }}>
                    SPECIAL REQUESTS / NOTES:
                  </div>
                  <div style={{ color: 'var(--slate-800)', fontSize: '0.82rem' }}>
                    {selectedBooking.special_requests}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.5rem', paddingTop: '0.75rem', borderTop: '1px solid var(--slate-100)' }}>
                <span
                  style={{
                    fontSize: '0.75rem',
                    padding: '3px 10px',
                    borderRadius: '12px',
                    fontWeight: 700,
                    background:
                      selectedBooking.status === 'confirmed' ? 'var(--emerald-100)' : 'var(--amber-100)',
                    color:
                      selectedBooking.status === 'confirmed' ? 'var(--emerald-700)' : 'var(--amber-800)',
                  }}
                >
                  Status: {selectedBooking.status.toUpperCase()}
                </span>

                {selectedBooking.status !== 'cancelled' && (
                  <button
                    type="button"
                    onClick={() => handleCancelBooking(selectedBooking.id, selectedBooking.customer_phone)}
                    disabled={cancellingId === selectedBooking.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      padding: '0.4rem 0.8rem',
                      background: 'none',
                      border: '1px solid var(--rose-200)',
                      borderRadius: 'var(--radius-sm)',
                      color: 'var(--rose-600)',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    <Trash2 size={14} /> Cancel Reservation
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
         MODAL 2: QUICK NEW RESERVATION MODAL
         ========================================================================= */}
      {isNewModalOpen && (
        <div className="modal-backdrop" onClick={() => setIsNewModalOpen(false)}>
          <div
            className="modal-card"
            style={{ maxWidth: '520px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                borderBottom: '1px solid var(--slate-200)',
                paddingBottom: '0.75rem',
                marginBottom: '1rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Plus size={20} color="var(--sky-600)" />
                <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: 'var(--slate-900)' }}>
                  New Reservation / Room Night
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsNewModalOpen(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--slate-400)' }}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateReservation} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Guest Full Name *</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. Robert Vance"
                    value={newBooking.customer_name}
                    onChange={(e) => setNewBooking((prev) => ({ ...prev, customer_name: e.target.value }))}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Contact Phone *</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. +14155552671"
                    value={newBooking.customer_phone}
                    onChange={(e) => setNewBooking((prev) => ({ ...prev, customer_phone: e.target.value }))}
                    required
                  />
                </div>
              </div>

              <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: '1.4fr 0.6fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Assign Resource *</label>
                  <select
                    className="form-input"
                    value={newBooking.resource_id}
                    onChange={(e) => {
                      const sel = resources.find((r) => r.id === e.target.value);
                      setNewBooking((prev) => ({
                        ...prev,
                        resource_id: e.target.value,
                        resource_type: sel ? sel.resource_type : prev.resource_type,
                      }));
                    }}
                    required
                  >
                    <option value="">-- Choose Table or Room --</option>
                    {resources.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name} ({r.resource_type} • fits {r.max_party_size})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Party Size</label>
                  <input
                    type="number"
                    min="1"
                    max="50"
                    className="form-input"
                    value={newBooking.party_size}
                    onChange={(e) => setNewBooking((prev) => ({ ...prev, party_size: e.target.value }))}
                    required
                  />
                </div>
              </div>

              {/* Start & End Date/Time */}
              <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">
                    {newBooking.resource_type === 'room' ? 'Check-in Date' : 'Start Date & Time'}
                  </label>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <input
                      type="date"
                      className="form-input"
                      value={newBooking.start_date}
                      onChange={(e) => setNewBooking((prev) => ({ ...prev, start_date: e.target.value }))}
                      required
                    />
                    <input
                      type="time"
                      className="form-input"
                      value={newBooking.start_time}
                      onChange={(e) => setNewBooking((prev) => ({ ...prev, start_time: e.target.value }))}
                      required
                      style={{ width: '100px' }}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">
                    {newBooking.resource_type === 'room' ? 'Check-out Date' : 'End Date & Time'}
                  </label>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <input
                      type="date"
                      className="form-input"
                      value={newBooking.end_date}
                      onChange={(e) => setNewBooking((prev) => ({ ...prev, end_date: e.target.value }))}
                      required
                    />
                    <input
                      type="time"
                      className="form-input"
                      value={newBooking.end_time}
                      onChange={(e) => setNewBooking((prev) => ({ ...prev, end_time: e.target.value }))}
                      required
                      style={{ width: '100px' }}
                    />
                  </div>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Special Requests / Preferences</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Quiet ocean view, anniversary flowers, window booth"
                  value={newBooking.special_requests}
                  onChange={(e) => setNewBooking((prev) => ({ ...prev, special_requests: e.target.value }))}
                />
              </div>

              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setIsNewModalOpen(false)}
                  style={{ flex: 1 }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={isSubmitting}
                  style={{ flex: 2, justifyContent: 'center' }}
                >
                  {isSubmitting ? 'Confirming...' : 'Confirm & Save Booking'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
