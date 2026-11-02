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
          <button
            onClick={() => setFeedback(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}
          >
            <X size={15} />
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
              <div style={{ width: '30px', height: '30px', borderRadius: 'var(--radius-sm)', background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-emerald)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <CalendarIcon size={16} />
              </div>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0, letterSpacing: '-0.02em' }}>
                Interactive Booking Calendar & Timeline
              </h3>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', marginTop: '3px', margin: 0 }}>
              Live occupancy grid for rooms, tables, and consultation suites. Inspect occupied nights, seatings, and guest reservations.
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
              <span>Total Resources:</span>
              <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{resources.length}</strong>
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
              <span>Confirmed:</span>
              <strong style={{ fontFamily: 'var(--font-mono)' }}>{activeBookingsCount}</strong>
            </div>

            <button
              type="button"
              className="btn-primary"
              onClick={() => handleOpenNewModal()}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                padding: '0.4rem 0.85rem',
                fontSize: '0.8rem',
                fontWeight: 600,
              }}
            >
              <Plus size={15} /> New Booking
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
            paddingTop: '0.85rem',
            borderTop: '1px solid var(--border-medium)',
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
              <ChevronLeft size={15} />
            </button>

            <button
              type="button"
              className="btn-secondary"
              onClick={handleToday}
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.78rem', fontWeight: 600 }}
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
              <ChevronRight size={15} />
            </button>

            <input
              type="date"
              className="form-input"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem', width: 'auto' }}
            />

            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginLeft: '4px' }}>
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
              <Filter size={13} color="var(--text-tertiary)" />
              <select
                className="form-input"
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                style={{ padding: '0.3rem 0.6rem', fontSize: '0.78rem', width: 'auto' }}
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
                background: 'var(--bg-surface-elevated)',
                borderRadius: 'var(--radius-sm)',
                padding: '2px',
                border: '1px solid var(--border-medium)',
              }}
            >
              <button
                type="button"
                onClick={() => setViewMode('timeline')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '4px 9px',
                  fontSize: '0.76rem',
                  fontWeight: 600,
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  background: viewMode === 'timeline' ? 'rgba(255, 255, 255, 0.08)' : 'transparent',
                  color: viewMode === 'timeline' ? 'var(--text-primary)' : 'var(--text-tertiary)',
                  boxShadow: viewMode === 'timeline' ? 'var(--shadow-sm)' : 'none',
                  transition: 'all 0.15s ease',
                }}
              >
                <Grid size={12} /> Multi-Day
              </button>

              <button
                type="button"
                onClick={() => setViewMode('day')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '4px 9px',
                  fontSize: '0.76rem',
                  fontWeight: 600,
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  background: viewMode === 'day' ? 'rgba(255, 255, 255, 0.08)' : 'transparent',
                  color: viewMode === 'day' ? 'var(--text-primary)' : 'var(--text-tertiary)',
                  boxShadow: viewMode === 'day' ? 'var(--shadow-sm)' : 'none',
                  transition: 'all 0.15s ease',
                }}
              >
                <Clock size={12} /> Day Slots
              </button>

              <button
                type="button"
                onClick={() => setViewMode('list')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '4px 9px',
                  fontSize: '0.76rem',
                  fontWeight: 600,
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  background: viewMode === 'list' ? 'rgba(255, 255, 255, 0.08)' : 'transparent',
                  color: viewMode === 'list' ? 'var(--text-primary)' : 'var(--text-tertiary)',
                  boxShadow: viewMode === 'list' ? 'var(--shadow-sm)' : 'none',
                  transition: 'all 0.15s ease',
                }}
              >
                <ListIcon size={12} /> List View
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
                <RefreshCw size={13} />
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
          }}
        >
          {filteredResources.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3.5rem', color: 'var(--text-tertiary)' }}>
              No resources found for the selected filter. Register a room or table to enable timeline scheduling.
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
                <tr style={{ background: 'var(--bg-surface-elevated)', borderBottom: '1px solid var(--border-medium)' }}>
                  <th
                    style={{
                      width: '230px',
                      padding: '0.85rem 1rem',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      color: 'var(--text-tertiary)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      borderRight: '1px solid var(--border-medium)',
                    }}
                  >
                    RESOURCE (ROOM / TABLE)
                  </th>
                  {timelineDays.map((td) => (
                    <th
                      key={td.date}
                      style={{
                        padding: '0.65rem 0.5rem',
                        fontSize: '0.76rem',
                        textAlign: 'center',
                        color: td.isToday ? 'var(--color-emerald)' : 'var(--text-secondary)',
                        background: td.isToday ? 'rgba(16, 185, 129, 0.05)' : 'transparent',
                        borderRight: '1px solid var(--border-medium)',
                        minWidth: '105px',
                      }}
                    >
                      <div style={{ fontWeight: 700, fontSize: '0.8rem' }}>{td.dayName}</div>
                      <div
                        style={{
                          fontSize: '0.72rem',
                          color: td.isToday ? 'var(--color-emerald)' : 'var(--text-tertiary)',
                          fontFamily: 'var(--font-mono)',
                          marginTop: '1px',
                        }}
                      >
                        {td.monthDay}
                      </div>
                      {td.isToday && (
                        <span
                          style={{
                            display: 'inline-block',
                            marginTop: '2px',
                            fontSize: '0.62rem',
                            background: 'rgba(16, 185, 129, 0.15)',
                            color: 'var(--color-emerald)',
                            border: '1px solid rgba(16, 185, 129, 0.3)',
                            padding: '1px 5px',
                            borderRadius: 'var(--radius-full)',
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
                      borderBottom: '1px solid var(--border-medium)',
                      background: idx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.015)',
                    }}
                  >
                    {/* Resource Header Cell */}
                    <td
                      style={{
                        padding: '0.85rem 1rem',
                        borderRight: '1px solid var(--border-medium)',
                        verticalAlign: 'top',
                      }}
                    >
                      <div style={{ fontWeight: 600, fontSize: '0.86rem', color: 'var(--text-primary)' }}>
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
                            fontSize: '0.68rem',
                            padding: '2px 6px',
                            borderRadius: 'var(--radius-sm)',
                            fontWeight: 600,
                            background:
                              res.resource_type === 'room'
                                ? 'rgba(56, 189, 248, 0.1)'
                                : res.resource_type === 'table'
                                ? 'rgba(16, 185, 129, 0.1)'
                                : 'rgba(255, 255, 255, 0.05)',
                            color:
                              res.resource_type === 'room'
                                ? '#38bdf8'
                                : res.resource_type === 'table'
                                ? 'var(--color-emerald)'
                                : 'var(--text-secondary)',
                            border: `1px solid ${
                              res.resource_type === 'room'
                                ? 'rgba(56, 189, 248, 0.25)'
                                : res.resource_type === 'table'
                                ? 'rgba(16, 185, 129, 0.25)'
                                : 'var(--border-medium)'
                            }`,
                          }}
                        >
                          {res.resource_type === 'room' ? 'Room' : res.resource_type === 'table' ? 'Table' : 'Suite'}
                        </span>
                        {res.section && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                            • {res.section}
                          </span>
                        )}
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
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
                            padding: '0.45rem',
                            borderRight: '1px solid var(--border-medium)',
                            verticalAlign: 'top',
                            background: td.isToday ? 'rgba(16, 185, 129, 0.02)' : 'transparent',
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
                                    padding: '5px 7px',
                                    borderRadius: '5px',
                                    background:
                                      b.status === 'confirmed'
                                        ? 'rgba(16, 185, 129, 0.12)'
                                        : 'rgba(245, 158, 11, 0.12)',
                                    border: `1px solid ${
                                      b.status === 'confirmed'
                                        ? 'rgba(16, 185, 129, 0.3)'
                                        : 'rgba(245, 158, 11, 0.3)'
                                    }`,
                                    color: b.status === 'confirmed' ? 'var(--color-emerald)' : 'var(--color-amber)',
                                    fontSize: '0.72rem',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                                    transition: 'all 0.15s ease',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                  }}
                                  title={`Guest: ${b.customer_name} (${b.party_size} guests)\nClick to inspect details`}
                                >
                                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{b.customer_name}</span>
                                    <span style={{ fontSize: '0.66rem', opacity: 0.85, fontFamily: 'var(--font-mono)' }}>{b.party_size}p</span>
                                  </div>
                                  <div style={{ fontSize: '0.66rem', opacity: 0.8, marginTop: '2px', fontFamily: 'var(--font-mono)' }}>
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
                                color: 'var(--text-tertiary)',
                              }}
                              className="calendar-empty-slot"
                              title={`Empty slot: Click to book ${res.name} on ${td.date}`}
                            >
                              <span style={{ fontSize: '0.68rem', opacity: 0.5 }}>+ Reserve</span>
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
          }}
        >
          {filteredResources.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3.5rem', color: 'var(--text-tertiary)' }}>
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
                <tr style={{ background: 'var(--bg-surface-elevated)', borderBottom: '1px solid var(--border-medium)' }}>
                  <th
                    style={{
                      width: '200px',
                      padding: '0.85rem 1rem',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      color: 'var(--text-tertiary)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      borderRight: '1px solid var(--border-medium)',
                    }}
                  >
                    RESOURCE
                  </th>
                  {hourlySlots.map((hour) => (
                    <th
                      key={hour}
                      style={{
                        padding: '0.65rem 0.4rem',
                        fontSize: '0.74rem',
                        textAlign: 'center',
                        color: 'var(--text-secondary)',
                        borderRight: '1px solid var(--border-medium)',
                        minWidth: '65px',
                        fontWeight: 600,
                        fontFamily: 'var(--font-mono)',
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
                      borderBottom: '1px solid var(--border-medium)',
                      background: idx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.015)',
                    }}
                  >
                    <td
                      style={{
                        padding: '0.75rem 1rem',
                        borderRight: '1px solid var(--border-medium)',
                        verticalAlign: 'top',
                      }}
                    >
                      <div style={{ fontWeight: 600, fontSize: '0.86rem', color: 'var(--text-primary)' }}>
                        {res.name}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '2px' }}>
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
                            padding: '0.35rem',
                            borderRight: '1px solid var(--border-medium)',
                            verticalAlign: 'top',
                            minHeight: '48px',
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
                                    borderRadius: '4px',
                                    background: 'rgba(16, 185, 129, 0.12)',
                                    border: '1px solid rgba(16, 185, 129, 0.3)',
                                    color: 'var(--color-emerald)',
                                    fontSize: '0.68rem',
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
                                color: 'var(--text-tertiary)',
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
          }}
        >
          {reservations.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3.5rem', color: 'var(--text-tertiary)' }}>
              No active reservations committed to the database.
            </div>
          ) : (
            <table className="modern-table">
              <thead>
                <tr>
                  <th>GUEST</th>
                  <th>PHONE</th>
                  <th>RESOURCE</th>
                  <th>START TIME</th>
                  <th>END TIME</th>
                  <th>GUESTS</th>
                  <th>STATUS</th>
                  <th style={{ textAlign: 'right' }}>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {reservations.map((b) => (
                  <tr key={b.id}>
                    <td>
                      <strong style={{ color: 'var(--text-primary)' }}>{b.customer_name}</strong>
                    </td>
                    <td>
                      <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                        {b.customer_phone}
                      </code>
                    </td>
                    <td>
                      <span style={{
                        background: 'rgba(255, 255, 255, 0.04)',
                        border: '1px solid var(--border-medium)',
                        padding: '2px 7px',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        color: 'var(--text-primary)',
                      }}>
                        {b.resource_name || b.resource_id || 'Auto-Assigned'}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                      {b.start_time?.replace('T', ' ').slice(0, 16)}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                      {b.end_time?.replace('T', ' ').slice(0, 16)}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--text-primary)' }}>
                      {b.party_size}
                    </td>
                    <td>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          padding: '2px 8px',
                          borderRadius: 'var(--radius-full)',
                          fontWeight: 700,
                          background:
                            b.status === 'confirmed'
                              ? 'rgba(16, 185, 129, 0.1)'
                              : b.status === 'cancelled'
                              ? 'rgba(244, 63, 94, 0.1)'
                              : 'rgba(245, 158, 11, 0.1)',
                          color:
                            b.status === 'confirmed'
                              ? 'var(--color-emerald)'
                              : b.status === 'cancelled'
                              ? 'var(--color-rose)'
                              : 'var(--color-amber)',
                          border: `1px solid ${
                            b.status === 'confirmed'
                              ? 'rgba(16, 185, 129, 0.25)'
                              : b.status === 'cancelled'
                              ? 'rgba(244, 63, 94, 0.25)'
                              : 'rgba(245, 158, 11, 0.25)'
                          }`,
                        }}
                      >
                        {b.status}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
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
                              background: 'rgba(244, 63, 94, 0.08)',
                              border: '1px solid rgba(244, 63, 94, 0.25)',
                              borderRadius: 'var(--radius-sm)',
                              color: 'var(--color-rose)',
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
         MODAL 1: RESERVATION DETAILS & INSPECTION MODAL (Obsidian Sheet)
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
                borderBottom: '1px solid var(--border-medium)',
                padding: '1.25rem 1.4rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={18} color="var(--color-emerald)" />
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Reservation Telemetry
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedBooking(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)' }}
              >
                <X size={16} />
              </button>
            </div>

            <div style={{ padding: '1.25rem 1.4rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.84rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <User size={15} color="var(--text-tertiary)" />
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>Guest Name:</span>
                <strong style={{ color: 'var(--text-primary)' }}>{selectedBooking.customer_name}</strong>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Phone size={15} color="var(--text-tertiary)" />
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>Contact Phone:</span>
                <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-mint)' }}>{selectedBooking.customer_phone}</code>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Users size={15} color="var(--text-tertiary)" />
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>Party Size:</span>
                <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{selectedBooking.party_size} guests</strong>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <MapPin size={15} color="var(--text-tertiary)" />
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>Assigned To:</span>
                <strong style={{ color: 'var(--text-primary)' }}>
                  {selectedBooking.resource_name || selectedBooking.resource_id || 'Standard Inventory'}
                </strong>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Clock size={15} color="var(--text-tertiary)" />
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>Start Time:</span>
                <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                  {selectedBooking.start_time?.replace('T', ' ').slice(0, 16)}
                </strong>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Clock size={15} color="var(--text-tertiary)" />
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>End Time:</span>
                <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                  {selectedBooking.end_time?.replace('T', ' ').slice(0, 16)}
                </strong>
              </div>

              {selectedBooking.special_requests && (
                <div style={{ marginTop: '0.5rem', padding: '0.75rem', background: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-medium)' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '2px' }}>
                    SPECIAL REQUESTS / NOTES:
                  </div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                    {selectedBooking.special_requests}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.5rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-medium)' }}>
                <span
                  style={{
                    fontSize: '0.72rem',
                    padding: '3px 9px',
                    borderRadius: 'var(--radius-full)',
                    fontWeight: 700,
                    background:
                      selectedBooking.status === 'confirmed'
                        ? 'rgba(16, 185, 129, 0.1)'
                        : 'rgba(245, 158, 11, 0.1)',
                    color:
                      selectedBooking.status === 'confirmed'
                        ? 'var(--color-emerald)'
                        : 'var(--color-amber)',
                    border: `1px solid ${
                      selectedBooking.status === 'confirmed'
                        ? 'rgba(16, 185, 129, 0.25)'
                        : 'rgba(245, 158, 11, 0.25)'
                    }`,
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
                      padding: '0.35rem 0.75rem',
                      background: 'rgba(244, 63, 94, 0.08)',
                      border: '1px solid rgba(244, 63, 94, 0.25)',
                      borderRadius: 'var(--radius-sm)',
                      color: 'var(--color-rose)',
                      fontSize: '0.78rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    <Trash2 size={13} /> Cancel Reservation
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
         MODAL 2: QUICK NEW RESERVATION MODAL (Obsidian Sheet)
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
                borderBottom: '1px solid var(--border-medium)',
                padding: '1.25rem 1.4rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Plus size={18} color="var(--color-emerald)" />
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  New Reservation / Room Night
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsNewModalOpen(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)' }}
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleCreateReservation} style={{ padding: '1.25rem 1.4rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
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
