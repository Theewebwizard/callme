import React, { useState, useMemo } from 'react';
import {
  Calendar as CalendarIcon,
  Clock,
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
  Bot,
  Sparkles,
  Ban,
  Check,
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
    resource_type: isClinic ? 'practitioner' : 'table',
    start_date: new Date().toISOString().slice(0, 10),
    start_time: '10:00',
    end_date: new Date().toISOString().slice(0, 10),
    end_time: '10:30',
    duration_minutes: 30,
    party_size: 1,
    special_requests: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Retrieve doctor available working days
  const getResourceAvailableDays = (res) => {
    if (res?.metadata?.available_days && Array.isArray(res.metadata.available_days) && res.metadata.available_days.length > 0) {
      return res.metadata.available_days;
    }
    const name = (res?.name || '').toLowerCase();
    if (name.includes('sharma') || name.includes('orthodont')) {
      // Default: Off on Monday & Sunday, open Tue-Sat
      return ['Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    }
    if (name.includes('ananya') || name.includes('pediatric')) {
      return ['Tue', 'Thu', 'Fri', 'Sat'];
    }
    if (res?.resource_type === 'practitioner' || isClinic) {
      return ['Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    }
    return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  };

  // Retrieve non-available / closed days
  const getResourceOffDays = (res) => {
    const avail = getResourceAvailableDays(res);
    return WEEKDAYS.filter((w) => !avail.some((d) => d.toLowerCase() === w.key.toLowerCase())).map((w) => w.key);
  };

  // Check if resource is available on a specific day
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

  // Clinic doctors list (strictly practitioners, no rooms)
  const doctorsList = useMemo(() => {
    if (isClinic) {
      return resources.filter((r) => r.resource_type === 'practitioner' || !['room', 'table', 'clinic_room', 'procedure_room'].includes(r.resource_type));
    }
    return resources.filter((r) => r.resource_type === 'practitioner');
  }, [resources, isClinic]);

  // Filtered resources: For clinic, strictly exclude any room artifacts
  const filteredResources = useMemo(() => {
    let list = resources;
    if (isClinic) {
      list = resources.filter((r) => r.resource_type === 'practitioner' || !['room', 'table', 'clinic_room', 'procedure_room'].includes(r.resource_type));
    }
    if (filterType === 'all') return list;
    return list.filter((r) => r.id === filterType || r.resource_type === filterType);
  }, [resources, filterType, isClinic]);

  // Generate 7 days for the timeline view starting strictly from MONDAY to SUNDAY (Modular Current Week)
  const timelineDays = useMemo(() => {
    const days = [];
    const monday = getMondayDate(selectedDate);
    for (let i = 0; i < 7; i++) {
      const d = new Date(monday);
      d.setDate(monday.getDate() + i);
      const iso = d.toISOString().slice(0, 10);
      const dayName = d.toLocaleDateString('en-US', { weekday: 'short' }); // Mon, Tue, ...
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

  const standardHourlySlots = useMemo(() => {
    const slots = [];
    for (let hour = 9; hour <= 22; hour++) {
      slots.push(`${hour.toString().padStart(2, '0')}:00`);
    }
    return slots;
  }, []);

  const activeDaySlots = isClinic ? clinicSlots : standardHourlySlots;

  // Week Navigation
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

  // Find reservations for a specific doctor and date
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

  // Find reservations for a 30-min slot in Day View
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

  // Toggle Doctor Available/Non-Available Day
  const handleToggleDoctorDay = async (doctor, dayKey) => {
    setSavingScheduleId(doctor.id);
    const currentDays = getResourceAvailableDays(doctor);
    const isCurrentlyActive = currentDays.some((d) => d.toLowerCase() === dayKey.toLowerCase());
    let newDays;

    if (isCurrentlyActive) {
      // Mark as Non-Available (Closed on this day)
      if (currentDays.length <= 1) {
        setFeedback({ type: 'error', text: `${doctor.name} must have at least one scheduled working day.` });
        setSavingScheduleId(null);
        return;
      }
      newDays = currentDays.filter((d) => d.toLowerCase() !== dayKey.toLowerCase());
    } else {
      // Mark as Available (Open on this day)
      const order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      const rawList = [...currentDays, dayKey];
      newDays = order.filter((d) => rawList.some((r) => r.toLowerCase() === d.toLowerCase()));
    }

    const newOffDays = WEEKDAYS.filter((w) => !newDays.some((d) => d.toLowerCase() === w.key.toLowerCase())).map((w) => w.key);

    try {
      await api.updateResource(business.id, doctor.id, {
        metadata: {
          ...(doctor.metadata || {}),
          available_days: newDays,
          off_days: newOffDays,
          slot_duration_minutes: 30,
        },
      });
      setFeedback({
        type: 'success',
        text: isCurrentlyActive
          ? `Clinic marked CLOSED on ${dayKey}s for ${doctor.name}. Calendar slots on ${dayKey}s are now blocked!`
          : `Clinic marked OPEN on ${dayKey}s for ${doctor.name}. Calendar slots on ${dayKey}s are now bookable!`,
      });
      if (onRefresh) onRefresh();
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to update schedule: ${err.message}` });
    } finally {
      setSavingScheduleId(null);
    }
  };

  // Quick preset: Mark Monday as Non-Available (Clinic Closed)
  const handleSetMondayClosed = async (doctor) => {
    const currentDays = getResourceAvailableDays(doctor);
    const hasMonday = currentDays.some((d) => d.toLowerCase() === 'mon');
    if (!hasMonday) {
      setFeedback({ type: 'success', text: `${doctor.name} is already scheduled OFF on Mondays (Clinic Closed).` });
      return;
    }
    await handleToggleDoctorDay(doctor, 'Mon');
  };

  // Open Quick Booking Modal
  const handleOpenNewModal = (resource = null, date = null, hour = null) => {
    const targetResource = resource || (filteredResources.length > 0 ? filteredResources[0] : null);
    const targetDate = date || selectedDate;
    const durMins = isClinic ? 30 : 60;
    const startH = hour ? hour : (isClinic ? '10:00' : '19:00');
    const endH = isClinic ? addMinutesToTime(startH, durMins) : addMinutesToTime(startH, 60);

    setNewBooking({
      customer_name: '',
      customer_phone: '',
      resource_id: targetResource ? targetResource.id : '',
      resource_type: isClinic ? 'practitioner' : (targetResource ? targetResource.resource_type : 'table'),
      start_date: targetDate,
      start_time: startH,
      end_date: targetDate,
      end_time: endH,
      duration_minutes: durMins,
      party_size: 1,
      special_requests: '',
    });
    setIsNewModalOpen(true);
  };

  // Create Appointment / Reservation
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
        throw new Error(`${selectedRes.name} is off on ${dayName}s (Clinic Closed). Scheduled working days: ${avail.join(', ')}.`);
      }

      const startIso = `${newBooking.start_date}T${newBooking.start_time}:00`;
      const endIso = `${newBooking.end_date}T${newBooking.end_time}:00`;

      await api.createReservation(business.id, {
        customer_name: newBooking.customer_name,
        customer_phone: newBooking.customer_phone,
        party_size: 1,
        start_time: startIso,
        end_time: endIso,
        resource_id: newBooking.resource_id || undefined,
        resource_type: selectedRes?.resource_type || (isClinic ? 'practitioner' : 'table'),
        section: selectedRes?.section,
        special_requests: newBooking.special_requests || undefined,
        status: 'confirmed',
      });

      setFeedback({
        type: 'success',
        text: `Appointment confirmed for ${newBooking.customer_name} with ${selectedRes?.name || 'Doctor'} on ${newBooking.start_date} at ${newBooking.start_time}!`,
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

  // Cancel Reservation
  const handleCancelBooking = async (bookingId, phone) => {
    if (!window.confirm('Are you sure you want to cancel this appointment?')) return;
    setCancellingId(bookingId);
    try {
      await api.cancelReservation(business.id, bookingId, phone);
      setFeedback({ type: 'success', text: 'Appointment cancelled successfully.' });
      setSelectedBooking(null);
      if (onRefresh) onRefresh();
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to cancel appointment: ${err.message}` });
    } finally {
      setCancellingId(null);
    }
  };

  const activeBookingsCount = useMemo(() => {
    return reservations.filter((b) => b.status !== 'cancelled').length;
  }, [reservations]);

  const currentModalDoctor = resources.find((r) => r.id === newBooking.resource_id);
  const isDoctorOffOnBookingDate = currentModalDoctor && !isResourceAvailableOnDay(currentModalDoctor, newBooking.start_date);
  const currentBookingDayName = new Date(newBooking.start_date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long' });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', width: '100%' }}>
      {/* =========================================================================
         AI AGENT AUTONOMY & CAPABILITY REASSURANCE BANNER
         ========================================================================= */}
      <div
        style={{
          background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(16, 185, 129, 0.08) 100%)',
          border: '1px solid rgba(59, 130, 246, 0.25)',
          borderRadius: 'var(--radius-md)',
          padding: '0.85rem 1.25rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '8px',
              background: 'rgba(59, 130, 246, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#3b82f6',
            }}
          >
            <Bot size={20} />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>🤖 AI Voice Receptionist Active: Autonomous Appointments & Live Calendar Booking</span>
              <span style={{ fontSize: '0.66rem', padding: '1px 6px', borderRadius: '999px', background: 'rgba(16, 185, 129, 0.15)', color: '#10b981', fontWeight: 700, border: '1px solid rgba(16, 185, 129, 0.3)' }}>ONLINE</span>
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
              When patients call, our voice AI agent autonomously checks doctor working days, verifies 30-min slot availability, confirms bookings verbally with the caller, and commits new appointments directly onto this live schedule in real time.
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', background: 'var(--bg-card)', padding: '4px 8px', borderRadius: '6px', border: '1px solid var(--border-medium)' }}>
            ⚡ 2-Way Atomic Sync
          </span>
          <span style={{ fontSize: '0.72rem', color: 'var(--color-emerald)', background: 'rgba(16, 185, 129, 0.08)', padding: '4px 8px', borderRadius: '6px', border: '1px solid rgba(16, 185, 129, 0.25)' }}>
            30m Slot Enforcement
          </span>
        </div>
      </div>

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
                {isClinic ? '🩺 Doctor Appointments Schedule (Monday – Sunday)' : 'Interactive Booking Calendar'}
              </h3>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', marginTop: '3px', margin: 0 }}>
              {isClinic
                ? 'Modular weekly patient appointment schedule. Select non-available days (e.g. clinic closed on Monday) to block slots automatically.'
                : 'Live reservations timeline grid.'}
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
              <span>{isClinic ? 'Active Doctors:' : 'Total Resources:'}</span>
              <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{filteredResources.length}</strong>
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
              <span>Confirmed Appointments:</span>
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
              <Plus size={15} /> {isClinic ? 'Schedule 30m Appointment' : 'New Booking'}
            </button>
          </div>
        </div>

        {/* Toolbar: Navigation, View Toggles, Doctor Filter */}
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
          {/* Modular Date Navigator */}
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
              Current Week (Today)
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

          {/* Doctor Filter & View Modes */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            {doctorsList.length > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Filter size={13} color="var(--text-tertiary)" />
                <select
                  className="form-input"
                  value={filterType}
                  onChange={(e) => setFilterType(e.target.value)}
                  style={{ padding: '0.3rem 0.6rem', fontSize: '0.78rem', width: 'auto' }}
                >
                  <option value="all">All Doctors ({doctorsList.length})</option>
                  {doctorsList.map((d) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
              </div>
            )}

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
                <Grid size={12} /> Mon–Sun Week Grid
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
                <Clock size={12} /> 30m Day Slots
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
                <ListIcon size={12} /> Appointment Table
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

        {/* =========================================================================
           DOCTOR NON-AVAILABLE DAYS (CLINIC CLOSED) SELECTOR & SCHEDULE CUSTOMIZER
           ========================================================================= */}
        {isClinic && doctorsList.length > 0 && (
          <div
            style={{
              marginTop: '0.35rem',
              padding: '0.85rem 1rem',
              background: 'rgba(59, 130, 246, 0.04)',
              border: '1px solid rgba(59, 130, 246, 0.2)',
              borderRadius: 'var(--radius-sm)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div style={{ fontSize: '0.84rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Stethoscope size={16} color="var(--primary, #3b82f6)" />
                Doctor Schedule: Select Non-Available / Weekly Off Days (e.g. Clinic Closed on Mondays)
              </div>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                Green = Open for Appointments • Red = Clinic Closed / Doctor Off (Slots Blocked)
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '0.85rem' }}>
              {doctorsList.map((doc) => {
                const avail = getResourceAvailableDays(doc);
                const offDays = getResourceOffDays(doc);
                const isMonClosed = offDays.includes('Mon');
                const isSaving = savingScheduleId === doc.id;

                return (
                  <div
                    key={doc.id}
                    style={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border-medium)',
                      padding: '0.75rem 0.95rem',
                      borderRadius: '8px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.5rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <strong style={{ fontSize: '0.84rem', color: 'var(--text-primary)' }}>{doc.name}</strong>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '1px' }}>
                          {doc.section || 'Specialist Consultation'}
                        </div>
                      </div>
                      <span
                        style={{
                          fontSize: '0.68rem',
                          fontWeight: 700,
                          padding: '2px 7px',
                          borderRadius: '4px',
                          background: isMonClosed ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)',
                          color: isMonClosed ? '#f87171' : 'var(--color-emerald)',
                          border: `1px solid ${isMonClosed ? 'rgba(239, 68, 68, 0.25)' : 'rgba(16, 185, 129, 0.25)'}`,
                        }}
                      >
                        {isMonClosed ? 'Closed on Mondays' : 'Open on Mondays'}
                      </span>
                    </div>

                    {/* Day Selector Pills: Open vs Closed */}
                    <div style={{ display: 'flex', gap: '5px', flexWrap: 'wrap', alignItems: 'center' }}>
                      {WEEKDAYS.map((w) => {
                        const isOpen = avail.some((d) => d.toLowerCase() === w.key.toLowerCase());
                        return (
                          <button
                            key={w.key}
                            type="button"
                            disabled={isSaving}
                            onClick={() => handleToggleDoctorDay(doc, w.key)}
                            style={{
                              padding: '4px 8px',
                              fontSize: '0.72rem',
                              fontWeight: 700,
                              borderRadius: '5px',
                              cursor: isSaving ? 'wait' : 'pointer',
                              border: isOpen
                                ? '1px solid rgba(16, 185, 129, 0.45)'
                                : '1px solid rgba(239, 68, 68, 0.35)',
                              background: isOpen
                                ? 'rgba(16, 185, 129, 0.15)'
                                : 'rgba(239, 68, 68, 0.12)',
                              color: isOpen ? 'var(--color-emerald)' : '#f87171',
                              transition: 'all 0.15s ease',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '3px',
                            }}
                            title={`Click to toggle ${w.label} (Currently ${isOpen ? 'OPEN' : 'CLOSED'})`}
                          >
                            {isOpen ? <Check size={11} /> : <Ban size={11} />}
                            {w.key}
                          </button>
                        );
                      })}
                    </div>

                    {/* Quick 1-Click Monday Preset */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-medium)', paddingTop: '0.45rem', marginTop: '0.2rem' }}>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>
                        Non-available: <strong style={{ color: '#f87171' }}>{offDays.length > 0 ? offDays.join(', ') : 'None'}</strong>
                      </span>
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => handleToggleDoctorDay(doc, 'Mon')}
                        disabled={isSaving}
                        style={{ fontSize: '0.7rem', padding: '2px 8px' }}
                      >
                        {isMonClosed ? '✓ Open on Mondays' : '❌ Close on Mondays'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* =========================================================================
         VIEW 1: MONDAY TO SUNDAY WEEKLY TIMELINE GRID (WITH MODULAR CURRENT DATES)
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
              No doctors or practitioners found. Register doctors to enable clinical appointment scheduling.
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
                    DOCTOR / SPECIALIST
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
                    {/* Doctor Info Cell */}
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
                            background: 'rgba(59, 130, 246, 0.12)',
                            color: '#3b82f6',
                            border: '1px solid rgba(59, 130, 246, 0.3)',
                          }}
                        >
                          Doctor / Specialist
                        </span>
                        {res.section && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                            • {res.section}
                          </span>
                        )}
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                          • 30m Slots
                        </span>
                      </div>
                    </td>

                    {/* Timeline Day Columns (Mon to Sun) */}
                    {timelineDays.map((td) => {
                      const isAvailable = isResourceAvailableOnDay(res, td.rawDate);
                      const dayBookings = getReservationsForResourceAndDate(res.id, td.date);
                      const isOccupied = dayBookings.length > 0;

                      // BLOCKED / NON-AVAILABLE DAY: e.g. Clinic Closed on Mondays
                      if (!isAvailable) {
                        return (
                          <td
                            key={td.date}
                            onClick={() => {
                              const docDays = getResourceAvailableDays(res);
                              setFeedback({
                                type: 'error',
                                text: `${res.name} does not open clinic on ${td.fullDayName}s. Scheduled working days: ${docDays.join(', ')}.`,
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
                            title={`${res.name} does not open clinic on ${td.dayName}s`}
                          >
                            <div
                              style={{
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                justifyContent: 'center',
                                opacity: 0.7,
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
                                🔒 Closed
                              </span>
                              <span style={{ fontSize: '0.60rem', color: 'var(--text-tertiary)' }}>
                                {td.dayName === 'Mon' ? 'Off on Mondays' : 'Clinic Closed'}
                              </span>
                            </div>
                          </td>
                        );
                      }

                      // AVAILABLE DAY: Render active appointments or +30m slot
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
                                  title={`Patient: ${b.customer_name}\nTime: ${b.start_time?.slice(11, 16)} - ${b.end_time?.slice(11, 16)}\nClick to inspect details`}
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
                              title={`Click to schedule 30m appointment with ${res.name} on ${td.date}`}
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
         VIEW 2: 30-MINUTE INTERVAL DAY SLOTS SCHEDULE
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
              No doctors available for this view.
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
                    DOCTOR / SPECIALIST
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
                        minWidth: '58px',
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
                          {res.section || 'Specialist Consultation'} • 30m Slots
                        </div>
                      </td>

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
                            🔒 Clinic Closed on {selectedDateWeekday}s (Non-Available Day for {res.name})
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
         VIEW 3: MODULAR APPOINTMENT TABLE VIEW (UPDATES ON CURRENT DATES)
         ========================================================================= */}
      {viewMode === 'list' && (
        <div className="card" style={{ padding: 0 }}>
          {reservations.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3.5rem', color: 'var(--text-tertiary)' }}>
              No patient appointments committed yet. Use the calendar or voice agent to schedule.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: 'var(--bg-surface-elevated)', borderBottom: '1px solid var(--border-medium)' }}>
                  <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                    PATIENT FULL NAME
                  </th>
                  <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                    CONTACT PHONE
                  </th>
                  <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                    DOCTOR / SPECIALIST
                  </th>
                  <th style={{ padding: '0.85rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
                    APPOINTMENT DATE & TIME (MODULAR)
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
                {reservations.map((b) => {
                  const bDateStr = b.start_time?.slice(0, 10);
                  const isToday = bDateStr === new Date().toISOString().slice(0, 10);
                  const dateObj = new Date(b.start_time);
                  const formattedDate = dateObj.toLocaleDateString('en-US', {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  });
                  const formattedTime = b.start_time?.includes('T') ? b.start_time.split('T')[1].slice(0, 5) : '';

                  return (
                    <tr key={b.id} style={{ borderBottom: '1px solid var(--border-medium)' }}>
                      <td style={{ padding: '0.75rem 1rem', fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.85rem' }}>
                        {b.customer_name}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--color-mint)' }}>
                        {b.customer_phone}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                        {b.resource_name || 'Dr. Sharma'}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ fontWeight: 600 }}>{formattedDate}</span>
                          <span style={{ color: 'var(--color-emerald)', fontFamily: 'var(--font-mono)' }}>{formattedTime} (30m)</span>
                          {isToday && (
                            <span style={{ fontSize: '0.62rem', background: 'rgba(16, 185, 129, 0.15)', color: 'var(--color-emerald)', padding: '1px 5px', borderRadius: '4px', fontWeight: 700 }}>
                              TODAY
                            </span>
                          )}
                        </div>
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
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* =========================================================================
         MODAL 1: INSPECT APPOINTMENT DETAILS
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
                  Patient Appointment Details
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
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>Patient Name:</span>
                <strong style={{ color: 'var(--text-primary)' }}>{selectedBooking.customer_name}</strong>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Phone size={15} color="var(--text-tertiary)" />
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>Contact Phone:</span>
                <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-mint)' }}>{selectedBooking.customer_phone}</code>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <MapPin size={15} color="var(--text-tertiary)" />
                <span style={{ color: 'var(--text-tertiary)', width: '95px' }}>Doctor:</span>
                <strong style={{ color: 'var(--text-primary)' }}>
                  {selectedBooking.resource_name || 'Dr. Sharma'}
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
                    CONSULTATION NOTES / PATIENT SYMPTOMS:
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
         MODAL 2: 30-MINUTE CONSULTATION SCHEDULING MODAL
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
                  🩺 Schedule Patient Appointment (30m Slot)
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
              {isDoctorOffOnBookingDate && (
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
                    <strong>{currentModalDoctor?.name}</strong> does not open clinic on {currentBookingDayName}s.
                    Available open days: <strong>{getResourceAvailableDays(currentModalDoctor).join(', ')}</strong>.
                  </span>
                </div>
              )}

              <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Patient Full Name *</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. Priya Sharma"
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

              {/* Doctor Selection */}
              <div className="form-group">
                <label className="form-label">Assign Doctor / Specialist *</label>
                <select
                  className="form-input"
                  value={newBooking.resource_id}
                  onChange={(e) => {
                    const sel = resources.find((r) => r.id === e.target.value);
                    setNewBooking((prev) => ({
                      ...prev,
                      resource_id: e.target.value,
                      resource_type: sel ? sel.resource_type : 'practitioner',
                    }));
                  }}
                  required
                >
                  <option value="">-- Choose Doctor / Specialist --</option>
                  {doctorsList.map((r) => {
                    const days = getResourceAvailableDays(r);
                    return (
                      <option key={r.id} value={r.id}>
                        {r.name} (Open: {days.join('•')})
                      </option>
                    );
                  })}
                </select>
              </div>

              {/* Date & 30-Minute Slot Duration */}
              <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: '0.75rem' }}>
                <div className="form-group">
                  <label className="form-label">Appointment Date *</label>
                  <input
                    type="date"
                    className="form-input"
                    value={newBooking.start_date}
                    onChange={(e) => {
                      const newDate = e.target.value;
                      setNewBooking((prev) => ({
                        ...prev,
                        start_date: newDate,
                        end_date: newDate,
                      }));
                    }}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Start Slot (30m) *</label>
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
                </div>

                <div className="form-group">
                  <label className="form-label">Duration</label>
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
              </div>

              {/* Calculated Consultation Window */}
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
                <span>Calculated Consultation Slot:</span>
                <strong style={{ color: 'var(--color-emerald)', fontFamily: 'var(--font-mono)' }}>
                  {newBooking.start_time} — {newBooking.end_time} ({newBooking.duration_minutes}m)
                </strong>
              </div>

              <div className="form-group">
                <label className="form-label">Consultation Notes / Patient Symptoms</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Toothache, Routine Scaling & Cleaning, Braces Wire Check"
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
                  disabled={isSubmitting || isDoctorOffOnBookingDate}
                  style={{ flex: 2, justifyContent: 'center', opacity: isDoctorOffOnBookingDate ? 0.5 : 1 }}
                >
                  {isSubmitting
                    ? 'Confirming...'
                    : isDoctorOffOnBookingDate
                    ? 'Doctor Closed on This Day'
                    : 'Confirm 30m Appointment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
