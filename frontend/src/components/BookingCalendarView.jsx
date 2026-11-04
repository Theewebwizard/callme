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
  Stethoscope,
  ShieldAlert,
  Sliders,
} from 'lucide-react';
import { api } from '../api';
import { getDomainForBusiness } from '../domain/businessDomainRegistry';

const WEEKDAYS = [
  { key: 'Mon', label: 'Monday' },
  { key: 'Tue', label: 'Tuesday' },
  { key: 'Wed', label: 'Wednesday' },
  { key: 'Thu', label: 'Thursday' },
  { key: 'Fri', label: 'Friday' },
  { key: 'Sat', label: 'Saturday' },
  { key: 'Sun', label: 'Sunday' },
];

/**
 * Compute the Monday date for any given date string YYYY-MM-DD.
 * Ensures week views consistently start on Monday and end on Sunday.
 */
function getMondayDate(dStr) {
  const base = new Date(dStr + 'T00:00:00');
  const day = base.getDay(); // 0 is Sunday, 1 is Monday...
  const diff = day === 0 ? -6 : 1 - day;
  const monday = new Date(base);
  monday.setDate(base.getDate() + diff);
  return monday;
}

/**
 * Add minutes to HH:MM time string, returning HH:MM.
 */
function addMinutesToTime(timeStr, minutesToAdd) {
  if (!timeStr || !timeStr.includes(':')) return '10:30';
  const [h, m] = timeStr.split(':').map((v) => parseInt(v, 10));
  const total = h * 60 + (m || 0) + minutesToAdd;
  const endH = Math.floor(total / 60) % 24;
  const endM = total % 60;
  return `${endH.toString().padStart(2, '0')}:${endM.toString().padStart(2, '0')}`;
}

/**
 * Interactive Visual Booking & Doctor Appointment Calendar
 * - Multi-Day Weekly Grid (Monday to Sunday)
 * - 30-Minute Consultation Slot Basis for Healthcare / Clinic
 * - Doctor Working Days Scheduling & Visual Blocking
 */
export default function BookingCalendarView({
  business,
  domainConfig = null,
  resources = [],
  reservations = [],
  onRefresh,
}) {
  const effectiveDomain = domainConfig || getDomainForBusiness(business?.industry || '');
  const isClinic = effectiveDomain.key === 'clinic';
  const isHotel = effectiveDomain.key === 'hotel';
  const isRestaurant = effectiveDomain.key === 'restaurant';

  const [viewMode, setViewMode] = useState('timeline'); // 'timeline' (Mon-Sun), 'day' (slots), 'list'
  const [selectedDate, setSelectedDate] = useState(() => {
    const today = new Date();
    return today.toISOString().slice(0, 10);
  });
  const [filterType, setFilterType] = useState('all');
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [isNewModalOpen, setIsNewModalOpen] = useState(false);
  const [cancellingId, setCancellingId] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [savingScheduleId, setSavingScheduleId] = useState(null);

  // New Booking Form State
  const [newBooking, setNewBooking] = useState({
    customer_name: '',
    customer_phone: '',
    resource_id: '',
    resource_type: 'practitioner',
    start_date: new Date().toISOString().slice(0, 10),
    start_time: '10:00',
    end_date: new Date().toISOString().slice(0, 10),
    end_time: '10:30',
    duration_minutes: 30,
    party_size: 1,
    special_requests: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Helper: Retrieve doctor/resource available days
  const getResourceAvailableDays = (res) => {
    if (res?.metadata?.available_days && Array.isArray(res.metadata.available_days) && res.metadata.available_days.length > 0) {
      return res.metadata.available_days;
    }
    const name = (res?.name || '').toLowerCase();
    if (name.includes('sharma') || name.includes('orthodont')) {
      return ['Mon', 'Wed', 'Fri', 'Sat'];
    }
    if (name.includes('ananya') || name.includes('pediatric')) {
      return ['Tue', 'Thu', 'Fri', 'Sat'];
    }
    if (res?.resource_type === 'practitioner') {
      return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
    }
    return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  };

  // Helper: Check if resource is available on a specific day
  const isResourceAvailableOnDay = (res, dayStrOrDate) => {
    const availDays = getResourceAvailableDays(res);
    let dayShort = '';
    if (typeof dayStrOrDate === 'string') {
      if (dayStrOrDate.includes('-')) {
        const d = new Date(dayStrOrDate + 'T00:00:00');
        dayShort = d.toLocaleDateString('en-US', { weekday: 'short' });
      } else {
        dayShort = dayStrOrDate.slice(0, 3);
      }
    } else if (dayStrOrDate instanceof Date) {
      dayShort = dayStrOrDate.toLocaleDateString('en-US', { weekday: 'short' });
    }
    return availDays.some((d) => d.toLowerCase() === dayShort.toLowerCase());
  };

  // Doctors / Practitioners list for schedule management
  const doctorsList = useMemo(() => {
    return resources.filter((r) => r.resource_type === 'practitioner' || (isClinic && r.resource_type !== 'room'));
  }, [resources, isClinic]);

  // Filtered resources based on UI category dropdown
  const filteredResources = useMemo(() => {
    if (filterType === 'all') return resources;
    return resources.filter((r) => r.resource_type === filterType);
  }, [resources, filterType]);

  // Generate 7 days for the timeline view starting strictly from MONDAY to SUNDAY
  const timelineDays = useMemo(() => {
    const days = [];
    const monday = getMondayDate(selectedDate);
    for (let i = 0; i < 7; i++) {
      const d = new Date(monday);
      d.setDate(monday.getDate() + i);
      const iso = d.toISOString().slice(0, 10);
      const dayName = d.toLocaleDateString('en-US', { weekday: 'short' }); // Mon, Tue, Wed, Thu, Fri, Sat, Sun
      const fullDayName = d.toLocaleDateString('en-US', { weekday: 'long' });
      const monthDay = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      const isToday = iso === new Date().toISOString().slice(0, 10);
      days.push({ date: iso, dayName, fullDayName, monthDay, isToday, rawDate: d });
    }
    return days;
  }, [selectedDate]);

  // 30-Minute Interval Slots for Clinic Appointments (09:00 to 19:30)
  const clinicSlots = useMemo(() => {
    const slots = [];
    for (let hour = 9; hour <= 19; hour++) {
      slots.push(`${hour.toString().padStart(2, '0')}:00`);
      if (hour < 19) {
        slots.push(`${hour.toString().padStart(2, '0')}:30`);
      }
    }
    return slots;
  }, []);

  // Standard 1-Hour Slots for Hospitality & Dining (09:00 to 22:00)
  const standardHourlySlots = useMemo(() => {
    const slots = [];
    for (let hour = 9; hour <= 22; hour++) {
      slots.push(`${hour.toString().padStart(2, '0')}:00`);
    }
    return slots;
  }, []);

  const activeDaySlots = isClinic ? clinicSlots : standardHourlySlots;

  // Quick Date Navigation Helpers (Shift by 1 full week Monday-Sunday)
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
      const resMatch = b.resource_id === resourceId;
      if (!resMatch && b.resource_id) return false;

      const bStart = (b.start_time || '').slice(0, 10);
      const bEnd = (b.end_time || '').slice(0, 10);
      if (bStart && bEnd && bStart <= dateStr && dateStr <= bEnd) {
        return true;
      }
      return bStart === dateStr;
    });
  };

  // Helper: Find reservations for a 30-min or 1-hour slot in Day View
  const getReservationsForResourceAndSlot = (resourceId, dateStr, slotStr) => {
    const [slotH, slotM] = slotStr.split(':').map((v) => parseInt(v, 10));
    const slotTotalMins = slotH * 60 + (slotM || 0);
    const slotStep = isClinic ? 30 : 60;
    const slotEndMins = slotTotalMins + slotStep;

    return reservations.filter((b) => {
      if (b.status === 'cancelled') return false;
      if (b.resource_id && b.resource_id !== resourceId) return false;

      const bStart = (b.start_time || '').slice(0, 10);
      if (bStart !== dateStr) return false;

      const timePart = (b.start_time || '').includes('T')
        ? b.start_time.split('T')[1]
        : b.start_time.split(' ')[1] || '00:00';
      const [startH, startM] = timePart.split(':').map((v) => parseInt(v, 10));
      const bStartTotal = startH * 60 + (startM || 0);

      const endTimePart = (b.end_time || '').includes('T')
        ? b.end_time.split('T')[1]
        : b.end_time.split(' ')[1] || '23:59';
      const [endH, endM] = endTimePart.split(':').map((v) => parseInt(v, 10));
      const bEndTotal = endH * 60 + (endM || 0);

      return bStartTotal < slotEndMins && bEndTotal > slotTotalMins;
    });
  };

  // Toggle Doctor Available Working Days on the fly
  const handleToggleDoctorDay = async (doctor, dayKey) => {
    setSavingScheduleId(doctor.id);
    const currentDays = getResourceAvailableDays(doctor);
    const exists = currentDays.some((d) => d.toLowerCase() === dayKey.toLowerCase());
    let newDays;
    if (exists) {
      if (currentDays.length <= 1) {
        setFeedback({ type: 'error', text: `${doctor.name} must have at least one scheduled working day.` });
        setSavingScheduleId(null);
        return;
      }
      newDays = currentDays.filter((d) => d.toLowerCase() !== dayKey.toLowerCase());
    } else {
      const order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      const rawList = [...currentDays, dayKey];
      newDays = order.filter((d) => rawList.some((r) => r.toLowerCase() === d.toLowerCase()));
    }

    try {
      await api.updateResource(business.id, doctor.id, {
        metadata: {
          ...(doctor.metadata || {}),
          available_days: newDays,
          slot_duration_minutes: 30,
        },
      });
      setFeedback({
        type: 'success',
        text: `Updated ${doctor.name}'s schedule: ${newDays.join(', ')}. Blocked days updated on calendar!`,
      });
      if (onRefresh) onRefresh();
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to update doctor schedule: ${err.message}` });
    } finally {
      setSavingScheduleId(null);
    }
  };

  // Open Quick Booking Modal with 30-min slot defaults
  const handleOpenNewModal = (resource = null, date = null, hour = null) => {
    const targetResource = resource || (filteredResources.length > 0 ? filteredResources[0] : null);
    const targetDate = date || selectedDate;
    const durMins = isClinic ? 30 : 60;
    const startH = hour ? hour : (isClinic ? '10:00' : targetResource?.resource_type === 'room' ? '15:00' : '19:00');
    const endH = isClinic ? addMinutesToTime(startH, durMins) : hour ? addMinutesToTime(hour, 60) : '21:00';

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
      resource_type: targetResource ? targetResource.resource_type : (isClinic ? 'practitioner' : 'table'),
      start_date: targetDate,
      start_time: startH,
      end_date: targetResource?.resource_type === 'room' ? nextDay : targetDate,
      end_time: endH,
      duration_minutes: durMins,
      party_size: isClinic ? 1 : targetResource ? Math.max(1, targetResource.min_party_size) : 2,
      special_requests: '',
    });
    setIsNewModalOpen(true);
  };

  // Handle Form Submit for New Reservation / Doctor Appointment
  const handleCreateReservation = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setFeedback(null);

    try {
      const selectedRes = resources.find((r) => r.id === newBooking.resource_id);

      // Validate that doctor is available on the selected date
      if (selectedRes && !isResourceAvailableOnDay(selectedRes, newBooking.start_date)) {
        const avail = getResourceAvailableDays(selectedRes);
        const dayName = new Date(newBooking.start_date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long' });
        throw new Error(`${selectedRes.name} is off on ${dayName}s. Scheduled working days: ${avail.join(', ')}.`);
      }

      const startIso = `${newBooking.start_date}T${newBooking.start_time}:00`;
      const endIso = `${newBooking.end_date}T${newBooking.end_time}:00`;

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

      setFeedback({
        type: 'success',
        text: isClinic
          ? `Appointment confirmed for ${newBooking.customer_name} with ${selectedRes?.name || 'Doctor'} on ${newBooking.start_date} at ${newBooking.start_time}!`
          : `Reservation confirmed for ${newBooking.customer_name}!`,
      });
      setIsNewModalOpen(false);
      if (onRefresh) onRefresh();
      setTimeout(() => setFeedback(null), 5000);
    } catch (err) {
      console.error('Reservation creation failed:', err);
      setFeedback({ type: 'error', text: `Failed to create appointment: ${err.message}` });
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

  // Selected doctor object in modal for dynamic validation
  const currentModalDoctor = resources.find((r) => r.id === newBooking.resource_id);
  const isDoctorOffOnBookingDate = currentModalDoctor && !isResourceAvailableOnDay(currentModalDoctor, newBooking.start_date);
  const currentBookingDayName = new Date(newBooking.start_date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long' });

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
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: 'var(--radius-sm)',
                  background: isClinic ? 'rgba(59, 130, 246, 0.12)' : 'rgba(16, 185, 129, 0.1)',
                  color: isClinic ? 'var(--primary, #3b82f6)' : 'var(--color-emerald)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {isClinic ? <Stethoscope size={18} /> : <CalendarIcon size={16} />}
              </div>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0, letterSpacing: '-0.02em' }}>
                {isClinic ? '🩺 Doctor Appointments & Consultation Calendar (Monday – Sunday)' : (effectiveDomain.resourceConfig?.calendarTitle || 'Interactive Booking Calendar')}
              </h3>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', marginTop: '3px', margin: 0 }}>
              {isClinic
                ? 'Weekly patient appointment schedule from Monday to Sunday. Doctor off-days are blocked automatically; appointments are booked in 30-minute intervals.'
                : isHotel
                ? 'Live occupancy grid for rooms and suites. Inspect occupied nights, check-ins, and guest stays.'
                : 'Live table reservation timeline. Inspect reserved seatings, party sizes, and dining schedules.'}
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
              <span>{isClinic ? 'Doctors & Suites:' : 'Total Resources:'}</span>
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
              <Plus size={15} /> {isClinic ? 'Schedule 30m Consult' : 'New Booking'}
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
              title="Previous Week (Monday - Sunday)"
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
              Current Week
            </button>

            <button
              type="button"
              className="btn-secondary"
              onClick={handleNext}
              title="Next Week (Monday - Sunday)"
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
                ? `Week: ${timelineDays[0]?.dayName}, ${timelineDays[0]?.monthDay} — ${timelineDays[6]?.dayName}, ${timelineDays[6]?.monthDay}, ${new Date(timelineDays[0]?.date).getFullYear()}`
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
                <option value="all">All {isClinic ? 'Medical Resources' : effectiveDomain.resourceConfig?.shortTitle || 'Resources'} ({resources.length})</option>
                {isClinic ? (
                  <>
                    <option value="practitioner">👨‍⚕️ Doctors & Specialists</option>
                    <option value="clinic_room">🩺 Consultation Suites</option>
                    <option value="procedure_room">🔬 Dental & Procedure Bays</option>
                    <option value="therapy_room">🧘 Therapy & Recovery Rooms</option>
                  </>
                ) : isHotel ? (
                  <>
                    <option value="room">🏨 Standard Hotel Rooms</option>
                    <option value="suite">🛏️ Executive Suites</option>
                    <option value="deluxe">✨ Deluxe Suites & Villas</option>
                    <option value="hall">🏛️ Banquet / Event Halls</option>
                  </>
                ) : (
                  <>
                    <option value="table">🍽️ Dining Tables</option>
                    <option value="booth">🛋️ Private Booths</option>
                    <option value="bar">🍸 Bar & Lounge</option>
                    <option value="patio">🌿 Outdoor Patio</option>
                  </>
                )}
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
                }}
              >
                <Grid size={12} /> {isClinic ? 'Mon–Sun Week' : 'Multi-Day'}
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
                }}
              >
                <Clock size={12} /> {isClinic ? '30m Day Slots' : 'Day Slots'}
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

        {/* Doctor Working Days & Clinic Hours Banner (Interactive Schedule Customizer) */}
        {isClinic && doctorsList.length > 0 && (
          <div
            style={{
              marginTop: '0.25rem',
              padding: '0.85rem 1rem',
              background: 'rgba(59, 130, 246, 0.04)',
              border: '1px solid rgba(59, 130, 246, 0.18)',
              borderRadius: 'var(--radius-sm)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.65rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Stethoscope size={15} color="var(--primary, #3b82f6)" />
                Doctor Available Working Days & Schedule
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                Days off are blocked automatically on the calendar. Click day pills to toggle doctor working schedule.
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.75rem' }}>
              {doctorsList.map((doc) => {
                const avail = getResourceAvailableDays(doc);
                const isSaving = savingScheduleId === doc.id;
                return (
                  <div
                    key={doc.id}
                    style={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border-medium)',
                      padding: '0.65rem 0.85rem',
                      borderRadius: '6px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.45rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '0.82rem', color: 'var(--text-primary)' }}>{doc.name}</strong>
                      <span style={{ fontSize: '0.68rem', color: 'var(--color-emerald)', fontWeight: 600 }}>
                        {isSaving ? 'Saving...' : `${avail.length} days/week`}
                      </span>
                    </div>

                    <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                      {WEEKDAYS.map((w) => {
                        const isActive = avail.some((d) => d.toLowerCase() === w.key.toLowerCase());
                        return (
                          <button
                            key={w.key}
                            type="button"
                            disabled={isSaving}
                            onClick={() => handleToggleDoctorDay(doc, w.key)}
                            style={{
                              padding: '2px 7px',
                              fontSize: '0.7rem',
                              fontWeight: 700,
                              borderRadius: '4px',
                              cursor: isSaving ? 'wait' : 'pointer',
                              border: isActive ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid var(--border-medium)',
                              background: isActive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(255, 255, 255, 0.02)',
                              color: isActive ? 'var(--color-emerald)' : 'var(--text-tertiary)',
                              transition: 'all 0.15s ease',
                            }}
                            title={`Click to ${isActive ? 'block' : 'enable'} ${w.label} for ${doc.name}`}
                          >
                            {w.key}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* =========================================================================
         VIEW 1: MONDAY TO SUNDAY WEEKLY TIMELINE GRID (WITH BLOCKED DOCTOR DAYS)
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
              {isClinic
                ? 'No consultation suites or doctors found for the selected filter. Register suites and doctors to enable appointment scheduling.'
                : isHotel
                ? 'No hotel rooms found for the selected filter. Register rooms under Units & Calendar to enable timeline scheduling.'
                : 'No dining tables found for the selected filter. Register tables to enable reservation scheduling.'}
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
                    {isClinic ? 'DOCTOR / CLINIC SUITE' : 'RESOURCE (ROOM / TABLE)'}
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
                              res.resource_type === 'practitioner'
                                ? 'rgba(16, 185, 129, 0.12)'
                                : res.resource_type === 'clinic_room'
                                ? 'rgba(56, 189, 248, 0.12)'
                                : res.resource_type === 'procedure_room'
                                ? 'rgba(168, 85, 247, 0.12)'
                                : res.resource_type === 'table'
                                ? 'rgba(16, 185, 129, 0.1)'
                                : 'rgba(56, 189, 248, 0.1)',
                            color:
                              res.resource_type === 'practitioner'
                                ? '#10b981'
                                : res.resource_type === 'clinic_room'
                                ? '#38bdf8'
                                : res.resource_type === 'procedure_room'
                                ? '#c084fc'
                                : res.resource_type === 'table'
                                ? 'var(--color-emerald)'
                                : '#38bdf8',
                            border: `1px solid ${
                              res.resource_type === 'practitioner'
                                ? 'rgba(16, 185, 129, 0.3)'
                                : res.resource_type === 'clinic_room'
                                ? 'rgba(56, 189, 248, 0.3)'
                                : res.resource_type === 'procedure_room'
                                ? 'rgba(168, 85, 247, 0.3)'
                                : 'var(--border-medium)'
                            }`,
                          }}
                        >
                          {res.resource_type === 'practitioner'
                            ? 'Doctor / Specialist'
                            : res.resource_type === 'clinic_room'
                            ? 'Consultation Suite'
                            : res.resource_type === 'procedure_room'
                            ? 'Procedure Bay'
                            : res.resource_type === 'therapy_room'
                            ? 'Therapy Room'
                            : res.resource_type === 'table'
                            ? 'Dining Table'
                            : (isClinic ? 'Clinical Suite' : 'Room')}
                        </span>
                        {res.section && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                            • {res.section}
                          </span>
                        )}
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                          • {isClinic ? '30m Slots' : `${res.min_party_size}–${res.max_party_size} pax`}
                        </span>
                      </div>
                    </td>

                    {/* Timeline Day Columns (Mon through Sun) */}
                    {timelineDays.map((td) => {
                      const isAvailable = isResourceAvailableOnDay(res, td.rawDate);
                      const dayBookings = getReservationsForResourceAndDate(res.id, td.date);
                      const isOccupied = dayBookings.length > 0;

                      // BLOCKED DAY: Doctor is off on this weekday
                      if (!isAvailable) {
                        const docDays = getResourceAvailableDays(res);
                        return (
                          <td
                            key={td.date}
                            onClick={() => {
                              setFeedback({
                                type: 'error',
                                text: `${res.name} does not take appointments on ${td.dayName}s. Scheduled working days: ${docDays.join(', ')}.`,
                              });
                            }}
                            style={{
                              padding: '0.45rem',
                              borderRight: '1px solid var(--border-medium)',
                              verticalAlign: 'middle',
                              background: 'repeating-linear-gradient(45deg, rgba(255, 255, 255, 0.012), rgba(255, 255, 255, 0.012) 8px, rgba(0, 0, 0, 0.28) 8px, rgba(0, 0, 0, 0.28) 16px)',
                              position: 'relative',
                              minHeight: '60px',
                              cursor: 'not-allowed',
                            }}
                            title={`${res.name} is not available on ${td.dayName}s`}
                          >
                            <div
                              style={{
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                justifyContent: 'center',
                                opacity: 0.65,
                                userSelect: 'none',
                                gap: '2px',
                              }}
                            >
                              <span
                                style={{
                                  fontSize: '0.64rem',
                                  fontWeight: 700,
                                  background: 'rgba(239, 68, 68, 0.12)',
                                  color: '#f87171',
                                  border: '1px solid rgba(239, 68, 68, 0.25)',
                                  padding: '2px 6px',
                                  borderRadius: '4px',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '3px',
                                }}
                              >
                                🔒 Day Off
                              </span>
                              <span style={{ fontSize: '0.60rem', color: 'var(--text-tertiary)' }}>
                                Not Available
                              </span>
                            </div>
                          </td>
                        );
                      }

                      // AVAILABLE DAY: Render appointments or +30m slot
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
                                  title={`Patient: ${b.customer_name}
Time: ${b.start_time?.slice(11, 16)} - ${b.end_time?.slice(11, 16)}
Click to inspect details`}
                                >
                                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{b.customer_name}</span>
                                    <span style={{ fontSize: '0.64rem', opacity: 0.85, fontFamily: 'var(--font-mono)' }}>30m</span>
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
                              title={`Empty slot: Click to book 30m consult with ${res.name} on ${td.date}`}
                            >
                              <span style={{ fontSize: '0.68rem', opacity: 0.55 }}>+ 30m Slot</span>
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
         VIEW 2: 30-MINUTE INTERVAL DAY SLOTS SCHEDULE (CLINIC PARITY)
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
                    {isClinic ? 'DOCTOR / SUITE' : 'RESOURCE'}
                  </th>
                  {activeDaySlots.map((slot) => (
                    <th
                      key={slot}
                      style={{
                        padding: '0.65rem 0.35rem',
                        fontSize: '0.72rem',
                        textAlign: 'center',
                        color: 'var(--text-secondary)',
                        borderRight: '1px solid var(--border-medium)',
                        minWidth: isClinic ? '58px' : '65px',
                        fontWeight: 600,
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {slot}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredResources.map((res, idx) => {
                  const isAvailableToday = isResourceAvailableOnDay(res, selectedDate);
                  const selectedDateWeekday = new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long' });

                  return (
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
                          {res.section || 'General'} • {isClinic ? '30m Slots' : `${res.capacity} seats`}
                        </div>
                      </td>

                      {/* If doctor is off today, render blocked banner across columns */}
                      {!isAvailableToday ? (
                        <td
                          colSpan={activeDaySlots.length}
                          style={{
                            padding: '0.85rem',
                            textAlign: 'center',
                            background: 'repeating-linear-gradient(45deg, rgba(255, 255, 255, 0.012), rgba(255, 255, 255, 0.012) 8px, rgba(0, 0, 0, 0.28) 8px, rgba(0, 0, 0, 0.28) 16px)',
                          }}
                        >
                          <span style={{ fontSize: '0.78rem', color: '#f87171', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            🔒 {res.name} is off on {selectedDateWeekday}s (Scheduled working days: {getResourceAvailableDays(res).join(', ')})
                          </span>
                        </td>
                      ) : (
                        activeDaySlots.map((slot) => {
                          const slotBookings = getReservationsForResourceAndSlot(res.id, selectedDate, slot);
                          const isOccupied = slotBookings.length > 0;

                          return (
                            <td
                              key={slot}
                              style={{
                                padding: '0.35rem',
                                borderRight: '1px solid var(--border-medium)',
                                verticalAlign: 'top',
                                minHeight: '48px',
                              }}
                            >
                              {isOccupied ? (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                  {slotBookings.map((b) => (
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
                                      title={`${b.customer_name} (30 mins)`}
                                    >
                                      {b.customer_name}
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div
                                  onClick={() => handleOpenNewModal(res, selectedDate, slot)}
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
                                  title={`Available: Click to book 30m appointment at ${slot}`}
                                >
                                  +
                                </div>
                              )}
                            </td>
                          );
                        })
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* =========================================================================
         VIEW 3: LIST VIEW OF UPCOMING BOOKINGS / APPOINTMENTS
         ========================================================================= */}
      {viewMode === 'list' && (
        <div className="card" style={{ padding: 0 }}>
          {reservations.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3.5rem', color: 'var(--text-tertiary)' }}>
              No bookings or patient appointments committed yet.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: 'var(--bg-surface-elevated)', borderBottom: '1px solid var(--border-medium)' }}>
                  <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                    {isClinic ? 'PATIENT NAME' : 'GUEST / CUSTOMER'}
                  </th>
                  <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                    CONTACT PHONE
                  </th>
                  <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                    {isClinic ? 'DOCTOR / SUITE' : 'ASSIGNED RESOURCE'}
                  </th>
                  <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                    START TIME
                  </th>
                  <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                    STATUS
                  </th>
                  <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', textAlign: 'right' }}>
                    ACTIONS
                  </th>
                </tr>
              </thead>
              <tbody>
                {reservations.map((b) => (
                  <tr key={b.id} style={{ borderBottom: '1px solid var(--border-medium)' }}>
                    <td style={{ padding: '0.75rem 1rem', fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.85rem' }}>
                      {b.customer_name}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-mint)' }}>
                      {b.customer_phone}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                      {b.resource_name || b.resource_id || 'Standard Inventory'}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                      {b.start_time?.replace('T', ' ').slice(0, 16)}
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          padding: '3px 8px',
                          borderRadius: 'var(--radius-full)',
                          fontWeight: 700,
                          background: b.status === 'confirmed' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
                          color: b.status === 'confirmed' ? 'var(--color-emerald)' : 'var(--color-rose)',
                          border: `1px solid ${b.status === 'confirmed' ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)'}`,
                        }}
                      >
                        {b.status.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '0.5rem' }}>
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => setSelectedBooking(b)}
                          style={{ padding: '0.25rem 0.55rem', fontSize: '0.74rem' }}
                        >
                          Details
                        </button>
                        {b.status !== 'cancelled' && (
                          <button
                            type="button"
                            className="btn-secondary"
                            onClick={() => handleCancelBooking(b.id, b.customer_phone)}
                            disabled={cancellingId === b.id}
                            style={{ padding: '0.25rem 0.55rem', fontSize: '0.74rem', color: 'var(--color-rose)' }}
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
         MODAL 1: INSPECT RESERVATION DETAILS (Obsidian Sheet)
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
                <FileText size={18} color="var(--color-emerald)" />
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {isClinic ? 'Patient Appointment Details' : 'Reservation Details'}
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
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>{isClinic ? 'Patient Name:' : 'Guest Name:'}</span>
                <strong style={{ color: 'var(--text-primary)' }}>{selectedBooking.customer_name}</strong>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Phone size={15} color="var(--text-tertiary)" />
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>Contact Phone:</span>
                <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-mint)' }}>{selectedBooking.customer_phone}</code>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <MapPin size={15} color="var(--text-tertiary)" />
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>{isClinic ? 'Doctor / Suite:' : 'Assigned To:'}</span>
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
                    {isClinic ? 'CONSULTATION NOTES / SYMPTOMS:' : 'SPECIAL REQUESTS / NOTES:'}
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
                    <Trash2 size={13} /> Cancel Appointment
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
         MODAL 2: 30-MINUTE CONSULTATION / NEW RESERVATION MODAL
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
                  {isClinic ? '🩺 Schedule Patient Consultation (30m Slot)' : isHotel ? 'New Room Reservation' : 'New Table Reservation'}
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
              {/* Doctor Off-Day Alert Banner */}
              {isClinic && isDoctorOffOnBookingDate && (
                <div
                  style={{
                    background: 'rgba(239, 68, 68, 0.12)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    color: '#f87171',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <AlertCircle size={16} style={{ flexShrink: 0 }} />
                  <span>
                    <strong>{currentModalDoctor?.name}</strong> does not take appointments on {currentBookingDayName}s.
                    Available days: <strong>{getResourceAvailableDays(currentModalDoctor).join(', ')}</strong>.
                  </span>
                </div>
              )}

              <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{isClinic ? 'Patient Full Name *' : isHotel ? 'Guest Full Name *' : 'Customer Name *'}</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder={isClinic ? 'e.g. Priya Sharma' : 'e.g. Robert Vance'}
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
                    placeholder="e.g. +91 98765 43210"
                    value={newBooking.customer_phone}
                    onChange={(e) => setNewBooking((prev) => ({ ...prev, customer_phone: e.target.value }))}
                    required
                  />
                </div>
              </div>

              {/* Resource / Doctor Selection */}
              <div className="form-group">
                <label className="form-label">{isClinic ? 'Assign Doctor / Specialist *' : 'Assign Resource *'}</label>
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
                  <option value="">{isClinic ? '-- Select Doctor or Consultation Suite --' : isHotel ? '-- Choose Room / Suite --' : '-- Choose Dining Table --'}</option>
                  {resources.map((r) => {
                    const days = getResourceAvailableDays(r);
                    return (
                      <option key={r.id} value={r.id}>
                        {r.name} {isClinic ? `(${days.join('•')})` : `(${r.resource_type} • fits ${r.max_party_size})`}
                      </option>
                    );
                  })}
                </select>
              </div>

              {/* Date & 30-Minute Slot Duration */}
              <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: isClinic ? '1.2fr 1fr 1fr' : '1fr 1fr', gap: '0.75rem' }}>
                <div className="form-group">
                  <label className="form-label">{isClinic ? 'Consultation Date *' : 'Start Date'}</label>
                  <input
                    type="date"
                    className="form-input"
                    value={newBooking.start_date}
                    onChange={(e) => {
                      const newDate = e.target.value;
                      setNewBooking((prev) => ({
                        ...prev,
                        start_date: newDate,
                        end_date: prev.resource_type === 'room' ? prev.end_date : newDate,
                      }));
                    }}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">{isClinic ? 'Start Slot (30m) *' : 'Start Time *'}</label>
                  {isClinic ? (
                    <select
                      className="form-input"
                      value={newBooking.start_time}
                      onChange={(e) => {
                        const newStart = e.target.value;
                        const newEnd = addMinutesToTime(newStart, newBooking.duration_minutes || 30);
                        setNewBooking((prev) => ({ ...prev, start_time: newStart, end_time: newEnd }));
                      }}
                      required
                    >
                      {clinicSlots.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="time"
                      className="form-input"
                      value={newBooking.start_time}
                      onChange={(e) => setNewBooking((prev) => ({ ...prev, start_time: e.target.value }))}
                      required
                    />
                  )}
                </div>

                {isClinic ? (
                  <div className="form-group">
                    <label className="form-label">Consult Duration</label>
                    <select
                      className="form-input"
                      value={newBooking.duration_minutes}
                      onChange={(e) => {
                        const dur = parseInt(e.target.value, 10);
                        const newEnd = addMinutesToTime(newBooking.start_time, dur);
                        setNewBooking((prev) => ({ ...prev, duration_minutes: dur, end_time: newEnd }));
                      }}
                    >
                      <option value={30}>30 mins (Standard)</option>
                      <option value={45}>45 mins (Comprehensive)</option>
                      <option value={60}>60 mins (Specialist)</option>
                    </select>
                  </div>
                ) : (
                  <div className="form-group">
                    <label className="form-label">End Time</label>
                    <input
                      type="time"
                      className="form-input"
                      value={newBooking.end_time}
                      onChange={(e) => setNewBooking((prev) => ({ ...prev, end_time: e.target.value }))}
                      required
                    />
                  </div>
                )}
              </div>

              {/* Slot Summary Confirmation for Clinic */}
              {isClinic && (
                <div
                  style={{
                    padding: '0.5rem 0.75rem',
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-medium)',
                    borderRadius: '6px',
                    fontSize: '0.78rem',
                    color: 'var(--text-secondary)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <span>Calculated Consultation Window:</span>
                  <strong style={{ color: 'var(--color-emerald)', fontFamily: 'var(--font-mono)' }}>
                    {newBooking.start_time} — {newBooking.end_time} ({newBooking.duration_minutes}m)
                  </strong>
                </div>
              )}

              <div className="form-group">
                <label className="form-label">{isClinic ? 'Consultation Notes / Patient Symptoms' : 'Special Requests / Preferences'}</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder={isClinic ? 'e.g. Toothache, Scaling & Polishing, Orthodontic braces follow-up' : 'e.g. Window booth, quiet table, ocean view'}
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
                  disabled={isSubmitting || (isClinic && isDoctorOffOnBookingDate)}
                  style={{ flex: 2, justifyContent: 'center', opacity: (isClinic && isDoctorOffOnBookingDate) ? 0.5 : 1 }}
                >
                  {isSubmitting
                    ? 'Confirming...'
                    : (isClinic && isDoctorOffOnBookingDate)
                    ? 'Doctor Unavailable on This Day'
                    : isClinic
                    ? 'Confirm 30m Appointment'
                    : 'Confirm & Save Booking'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
