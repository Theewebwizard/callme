import React, { useState, useMemo } from 'react';
import {
  Stethoscope,
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
  Bot,
  Sparkles,
  MapPin,
  Check,
  Ban,
  Layers,
} from 'lucide-react';
import { api } from '../api';

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

function addMinutesToTime(timeStr, minutesToAdd) {
  if (!timeStr || !timeStr.includes(':')) return '10:30';
  const [h, m] = timeStr.split(':').map((v) => parseInt(v, 10));
  const total = h * 60 + (m || 0) + minutesToAdd;
  const endH = Math.floor(total / 60) % 24;
  const endM = total % 60;
  return `${endH.toString().padStart(2, '0')}:${endM.toString().padStart(2, '0')}`;
}

export default function DoctorAppointmentCalendarView({
  business,
  resources = [],
  reservations = [],
  onRefresh,
}) {
  const [viewMode, setViewMode] = useState('timeline'); // 'timeline' (Mon-Sun), 'day' (30m slots), 'list', 'doctors'
  const [selectedDate, setSelectedDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [filterDoctorId, setFilterDoctorId] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [feedback, setFeedback] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [savingScheduleId, setSavingScheduleId] = useState(null);
  const [isNewBookingModalOpen, setIsNewBookingModalOpen] = useState(false);
  const [isAddDoctorModalOpen, setIsAddDoctorModalOpen] = useState(false);
  const [cancellingId, setCancellingId] = useState(null);

  // New Appointment Form State
  const [newBooking, setNewBooking] = useState({
    customer_name: '',
    customer_phone: '',
    resource_id: '',
    start_date: new Date().toISOString().slice(0, 10),
    start_time: '10:00',
    duration_minutes: 30,
    special_requests: '',
  });

  // New Doctor Form State
  const [newDoctor, setNewDoctor] = useState({
    name: '',
    section: 'Orthodontics',
    capacity: 1,
  });

  // Filter strictly doctor / practitioner resources (no rooms)
  const doctors = useMemo(() => {
    return resources.filter(
      (r) =>
        r.resource_type === 'practitioner' ||
        (!['room', 'table', 'clinic_room', 'procedure_room', 'booth', 'terrace', 'bar'].includes(r.resource_type))
    );
  }, [resources]);

  const filteredDoctors = useMemo(() => {
    if (filterDoctorId === 'all') return doctors;
    return doctors.filter((d) => d.id === filterDoctorId);
  }, [doctors, filterDoctorId]);

  // Active appointments
  const activeAppointments = useMemo(() => {
    return reservations.filter((r) => r.status !== 'cancelled');
  }, [reservations]);

  const todayAppointments = useMemo(() => {
    return activeAppointments.filter((r) => (r.start_time || '').slice(0, 10) === selectedDate);
  }, [activeAppointments, selectedDate]);

  // Generate 7 days for the timeline view starting strictly from MONDAY to SUNDAY (Modular Current Week)
  const timelineDays = useMemo(() => {
    const days = [];
    const monday = getMondayDate(selectedDate);
    for (let i = 0; i < 7; i++) {
      const d = new Date(monday);
      d.setDate(monday.getDate() + i);
      const iso = d.toISOString().slice(0, 10);
      const dayName = d.toLocaleDateString('en-US', { weekday: 'short' });
      const fullDayName = d.toLocaleDateString('en-US', { weekday: 'long' });
      const monthDay = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      const isToday = iso === new Date().toISOString().slice(0, 10);
      days.push({ date: iso, dayName, fullDayName, monthDay, isToday, rawDate: d });
    }
    return days;
  }, [selectedDate]);

  // 30-Minute Interval Slots for Clinic Appointments (09:00 to 18:30)
  const clinicSlots = useMemo(() => {
    const slots = [];
    for (let hour = 9; hour <= 18; hour++) {
      slots.push(`${hour.toString().padStart(2, '0')}:00`);
      if (hour < 18) {
        slots.push(`${hour.toString().padStart(2, '0')}:30`);
      }
    }
    return slots;
  }, []);

  // Retrieve doctor working days
  const getDoctorAvailableDays = (doc) => {
    if (doc?.metadata?.available_days && Array.isArray(doc.metadata.available_days) && doc.metadata.available_days.length > 0) {
      return doc.metadata.available_days;
    }
    const name = (doc?.name || '').toLowerCase();
    if (name.includes('sharma') || name.includes('orthodont')) {
      return ['Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    }
    if (name.includes('ananya') || name.includes('pediatric')) {
      return ['Tue', 'Thu', 'Fri', 'Sat'];
    }
    return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  };

  const getDoctorOffDays = (doc) => {
    const avail = getDoctorAvailableDays(doc);
    return WEEKDAYS.filter((w) => !avail.some((d) => d.toLowerCase() === w.key.toLowerCase())).map((w) => w.key);
  };

  const isDoctorAvailableOnDay = (doc, dayStrOrDate) => {
    const availDays = getDoctorAvailableDays(doc);
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

  // Find appointments for a doctor on a specific date
  const getAppointmentsForDoctorAndDate = (doctorId, dateStr) => {
    return activeAppointments.filter((b) => {
      const match = b.resource_id === doctorId;
      if (!match && b.resource_id) return false;
      const bDate = (b.start_time || '').slice(0, 10);
      return bDate === dateStr;
    });
  };

  // Toggle Doctor Available/Non-Available Day
  const handleToggleDoctorDay = async (doc, dayKey) => {
    setSavingScheduleId(doc.id);
    const currentDays = getDoctorAvailableDays(doc);
    const isCurrentlyActive = currentDays.some((d) => d.toLowerCase() === dayKey.toLowerCase());
    let newDays;

    if (isCurrentlyActive) {
      if (currentDays.length <= 1) {
        setFeedback({ type: 'error', text: `${doc.name} must have at least one scheduled working day.` });
        setSavingScheduleId(null);
        return;
      }
      newDays = currentDays.filter((d) => d.toLowerCase() !== dayKey.toLowerCase());
    } else {
      const order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      const rawList = [...currentDays, dayKey];
      newDays = order.filter((d) => rawList.some((r) => r.toLowerCase() === d.toLowerCase()));
    }

    const newOffDays = WEEKDAYS.filter((w) => !newDays.some((d) => d.toLowerCase() === w.key.toLowerCase())).map((w) => w.key);

    try {
      await api.updateResource(business.id, doc.id, {
        metadata: {
          ...(doc.metadata || {}),
          available_days: newDays,
          off_days: newOffDays,
          slot_duration_minutes: 30,
        },
      });
      setFeedback({
        type: 'success',
        text: isCurrentlyActive
          ? `Clinic marked CLOSED on ${dayKey}s for ${doc.name}. Calendar slots on ${dayKey}s are now locked!`
          : `Clinic marked OPEN on ${dayKey}s for ${doc.name}. Calendar slots on ${dayKey}s are now bookable!`,
      });
      if (onRefresh) onRefresh();
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to update schedule: ${err.message}` });
    } finally {
      setSavingScheduleId(null);
    }
  };

  // Quick preset: Mark Monday as Non-Available (Clinic Closed)
  const handleSetMondayClosed = async (doc) => {
    const currentDays = getDoctorAvailableDays(doc);
    const hasMonday = currentDays.some((d) => d.toLowerCase() === 'mon');
    if (!hasMonday) {
      setFeedback({ type: 'success', text: `${doc.name} is already scheduled OFF on Mondays (Clinic Closed).` });
      return;
    }
    await handleToggleDoctorDay(doc, 'Mon');
  };

  // Open Appointment Booking Modal
  const handleOpenBookingModal = (doc = null, date = null, time = null) => {
    const targetDoc = doc || (doctors.length > 0 ? doctors[0] : null);
    const targetDate = date || selectedDate;
    const targetTime = time || '10:00';

    setNewBooking({
      customer_name: '',
      customer_phone: '',
      resource_id: targetDoc ? targetDoc.id : '',
      start_date: targetDate,
      start_time: targetTime,
      duration_minutes: 30,
      special_requests: '',
    });
    setIsNewBookingModalOpen(true);
  };

  // Create Patient Appointment
  const handleCreateAppointment = async (e) => {
    e.preventDefault();
    if (!newBooking.customer_name.trim() || !newBooking.customer_phone.trim()) {
      setFeedback({ type: 'error', text: 'Please enter patient name and contact number.' });
      return;
    }

    setIsSubmitting(true);
    setFeedback(null);

    try {
      const selectedDoc = doctors.find((d) => d.id === newBooking.resource_id);

      // Validate working day
      if (selectedDoc && !isDoctorAvailableOnDay(selectedDoc, newBooking.start_date)) {
        const avail = getDoctorAvailableDays(selectedDoc);
        const dayName = new Date(newBooking.start_date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long' });
        throw new Error(`${selectedDoc.name} is off on ${dayName}s (Clinic Closed). Working days: ${avail.join(', ')}.`);
      }

      const startIso = `${newBooking.start_date}T${newBooking.start_time}:00`;
      const endTime = addMinutesToTime(newBooking.start_time, 30);
      const endIso = `${newBooking.start_date}T${endTime}:00`;

      await api.createReservation(business.id, {
        customer_name: newBooking.customer_name.trim(),
        customer_phone: newBooking.customer_phone.trim(),
        party_size: 1,
        start_time: startIso,
        end_time: endIso,
        resource_id: newBooking.resource_id || undefined,
        resource_type: 'practitioner',
        section: selectedDoc?.section || 'Consultation',
        special_requests: newBooking.special_requests || undefined,
        status: 'confirmed',
      });

      setFeedback({
        type: 'success',
        text: `30-minute appointment confirmed for ${newBooking.customer_name} with ${selectedDoc?.name || 'Doctor'} on ${newBooking.start_date} at ${newBooking.start_time}!`,
      });
      setIsNewBookingModalOpen(false);
      if (onRefresh) await onRefresh();
      setTimeout(() => setFeedback(null), 5000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to schedule appointment: ${err.message}` });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Cancel Appointment
  const handleCancelAppointment = async (bookingId, phone) => {
    if (!window.confirm('Cancel this patient appointment?')) return;
    setCancellingId(bookingId);
    try {
      await api.cancelReservation(business.id, bookingId, phone);
      setFeedback({ type: 'success', text: 'Appointment cancelled successfully.' });
      if (onRefresh) await onRefresh();
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to cancel appointment: ${err.message}` });
    } finally {
      setCancellingId(null);
    }
  };

  // Add New Doctor
  const handleAddDoctor = async (e) => {
    e.preventDefault();
    if (!newDoctor.name.trim()) return;

    setIsSubmitting(true);
    setFeedback(null);
    try {
      await api.createResource(business.id, {
        name: newDoctor.name.trim(),
        section: newDoctor.section.trim() || 'General Medicine',
        capacity: 1,
        min_party_size: 1,
        max_party_size: 1,
        resource_type: 'practitioner',
        metadata: {
          available_days: ['Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
          off_days: ['Mon', 'Sun'],
          slot_duration_minutes: 30,
        },
      });

      setFeedback({ type: 'success', text: `Doctor "${newDoctor.name.trim()}" registered to practice!` });
      setNewDoctor({ name: '', section: 'Orthodontics', capacity: 1 });
      setIsAddDoctorModalOpen(false);
      if (onRefresh) await onRefresh();
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to add doctor: ${err.message}` });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Delete Doctor
  const handleDeleteDoctor = async (docId, docName) => {
    if (!window.confirm(`Remove ${docName} from clinic practice? Existing appointment records will be preserved.`)) return;
    setIsSubmitting(true);
    try {
      await api.deleteResource(business.id, docId);
      setFeedback({ type: 'success', text: `${docName} removed from practice roster.` });
      if (onRefresh) await onRefresh();
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ type: 'error', text: `Failed to delete doctor: ${err.message}` });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Date Navigator
  const handlePrev = () => {
    const d = new Date(selectedDate + 'T00:00:00');
    d.setDate(d.getDate() - 7);
    setSelectedDate(d.toISOString().slice(0, 10));
  };

  const handleNext = () => {
    const d = new Date(selectedDate + 'T00:00:00');
    d.setDate(d.getDate() + 7);
    setSelectedDate(d.toISOString().slice(0, 10));
  };

  const handleToday = () => {
    setSelectedDate(new Date().toISOString().slice(0, 10));
  };

  const currentModalDoctor = doctors.find((d) => d.id === newBooking.resource_id);
  const isDoctorOffOnBookingDate = currentModalDoctor && !isDoctorAvailableOnDay(currentModalDoctor, newBooking.start_date);
  const currentBookingDayName = new Date(newBooking.start_date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long' });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', width: '100%' }}>
      {/* =========================================================================
         AI VOICE MEDICAL RECEPTIONIST BANNER (CLINIC TAILORED)
         ========================================================================= */}
      <div
        style={{
          background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(16, 185, 129, 0.08) 100%)',
          border: '1px solid rgba(59, 130, 246, 0.25)',
          borderRadius: 'var(--radius-md)',
          padding: '0.9rem 1.25rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '38px',
              height: '38px',
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
            <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>🩺 AI Voice Receptionist Active: Autonomous Doctor Appointments & Live Clinic Schedule</span>
              <span style={{ fontSize: '0.66rem', padding: '1px 7px', borderRadius: '999px', background: 'rgba(16, 185, 129, 0.15)', color: '#10b981', fontWeight: 700, border: '1px solid rgba(16, 185, 129, 0.3)' }}>ONLINE</span>
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
              When patients call, our voice AI receptionist autonomously checks doctor working days, verifies 30-min slot availability, notes patient symptoms, confirms appointments verbally with callers, and commits bookings directly onto this live schedule in real time.
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
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
                  background: 'rgba(59, 130, 246, 0.12)',
                  color: 'var(--primary, #3b82f6)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Stethoscope size={18} />
              </div>
              <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0, letterSpacing: '-0.02em' }}>
                🩺 Doctor Appointments & Schedule (Monday – Sunday)
              </h2>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', marginTop: '3px', margin: 0 }}>
              Modular weekly patient appointment schedule. Select non-available days (e.g. clinic closed on Monday) to block slots automatically.
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
              <span>Active Doctors:</span>
              <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{doctors.length}</strong>
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
              <strong style={{ fontFamily: 'var(--font-mono)' }}>{activeAppointments.length}</strong>
            </div>

            <button
              type="button"
              className="btn-primary"
              onClick={() => handleOpenBookingModal()}
              style={{ display: 'flex', alignItems: 'center', gap: '5px', padding: '0.4rem 0.85rem', fontSize: '0.8rem', fontWeight: 600 }}
            >
              <Plus size={15} /> Schedule 30m Appointment
            </button>
          </div>
        </div>

        {/* Toolbar: Navigation & Views */}
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
            <button type="button" className="btn-secondary" onClick={handlePrev} title="Previous Week" style={{ padding: '0.35rem 0.55rem' }}>
              <ChevronLeft size={15} />
            </button>
            <button type="button" className="btn-secondary" onClick={handleToday} style={{ padding: '0.35rem 0.75rem', fontSize: '0.78rem', fontWeight: 600 }}>
              Current Week (Today)
            </button>
            <button type="button" className="btn-secondary" onClick={handleNext} title="Next Week" style={{ padding: '0.35rem 0.55rem' }}>
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
              Week: {timelineDays[0]?.dayName}, {timelineDays[0]?.monthDay} — {timelineDays[6]?.dayName}, {timelineDays[6]?.monthDay}, {new Date(timelineDays[0]?.date).getFullYear()}
            </span>
          </div>

          {/* Doctor Filter & View Modes */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            {doctors.length > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Filter size={13} color="var(--text-tertiary)" />
                <select
                  className="form-input"
                  value={filterDoctorId}
                  onChange={(e) => setFilterDoctorId(e.target.value)}
                  style={{ padding: '0.3rem 0.6rem', fontSize: '0.78rem', width: 'auto' }}
                >
                  <option value="all">All Doctors ({doctors.length})</option>
                  {doctors.map((d) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
              </div>
            )}

            {/* View Mode Buttons */}
            <div style={{ display: 'flex', background: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', padding: '2px', border: '1px solid var(--border-medium)' }}>
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
                }}
              >
                <ListIcon size={12} /> Appointment Table
              </button>

              <button
                type="button"
                onClick={() => setViewMode('doctors')}
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
                  background: viewMode === 'doctors' ? 'rgba(255, 255, 255, 0.08)' : 'transparent',
                  color: viewMode === 'doctors' ? 'var(--text-primary)' : 'var(--text-tertiary)',
                }}
              >
                <Layers size={12} /> Manage Doctors ({doctors.length})
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
        {doctors.length > 0 && (
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
              {doctors.map((doc) => {
                const avail = getDoctorAvailableDays(doc);
                const offDays = getDoctorOffDays(doc);
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
                            onClick={() => handleToggleDoctorDay(doc, w.key)}
                            disabled={isSaving}
                            title={`Click to mark ${w.label} as ${isOpen ? 'Closed / Off' : 'Open'}`}
                            style={{
                              padding: '3px 8px',
                              borderRadius: '4px',
                              fontSize: '0.72rem',
                              fontWeight: 600,
                              cursor: 'pointer',
                              border: isOpen
                                ? '1px solid rgba(16, 185, 129, 0.4)'
                                : '1px solid rgba(239, 68, 68, 0.4)',
                              background: isOpen
                                ? 'rgba(16, 185, 129, 0.12)'
                                : 'rgba(239, 68, 68, 0.12)',
                              color: isOpen ? 'var(--color-emerald)' : '#f87171',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '3px',
                            }}
                          >
                            <span>{w.key}</span>
                            {isOpen ? <Check size={10} strokeWidth={3} /> : <Ban size={10} strokeWidth={2.5} />}
                          </button>
                        );
                      })}
                    </div>

                    {/* Quick Preset: 1-Click Close on Mondays */}
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '2px' }}>
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
         VIEW 1: MONDAY TO SUNDAY WEEKLY TIMELINE GRID
         ========================================================================= */}
      {viewMode === 'timeline' && (
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          {filteredDoctors.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3.5rem', color: 'var(--text-tertiary)' }}>
              No doctors or specialists registered. Click "Manage Doctors" to add practitioners to your clinic.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '780px', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: 'var(--bg-surface-elevated)', borderBottom: '1px solid var(--border-medium)' }}>
                  <th style={{ width: '230px', padding: '0.85rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', borderRight: '1px solid var(--border-medium)' }}>
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
                      <div style={{ fontSize: '0.72rem', color: td.isToday ? 'var(--color-emerald)' : 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: '1px' }}>
                        {td.monthDay}
                      </div>
                      {td.isToday && (
                        <span style={{ display: 'inline-block', marginTop: '2px', fontSize: '0.62rem', background: 'rgba(16, 185, 129, 0.15)', color: 'var(--color-emerald)', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '1px 5px', borderRadius: 'var(--radius-full)', fontWeight: 700 }}>
                          TODAY
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredDoctors.map((doc, idx) => (
                  <tr key={doc.id} style={{ borderBottom: '1px solid var(--border-medium)', background: idx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.015)' }}>
                    <td style={{ padding: '0.85rem 1rem', borderRight: '1px solid var(--border-medium)', verticalAlign: 'top' }}>
                      <div style={{ fontWeight: 600, fontSize: '0.86rem', color: 'var(--text-primary)' }}>
                        {doc.name}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: '0.68rem', padding: '2px 6px', borderRadius: 'var(--radius-sm)', fontWeight: 600, background: 'rgba(59, 130, 246, 0.12)', color: '#3b82f6', border: '1px solid rgba(59, 130, 246, 0.3)' }}>
                          Doctor / Specialist
                        </span>
                        {doc.section && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                            • {doc.section}
                          </span>
                        )}
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                          • 30m Slots
                        </span>
                      </div>
                    </td>

                    {timelineDays.map((td) => {
                      const isAvailable = isDoctorAvailableOnDay(doc, td.rawDate);
                      const dayBookings = getAppointmentsForDoctorAndDate(doc.id, td.date);

                      if (!isAvailable) {
                        return (
                          <td
                            key={td.date}
                            style={{
                              padding: '0.65rem 0.5rem',
                              borderRight: '1px solid var(--border-medium)',
                              background: 'rgba(239, 68, 68, 0.04)',
                              textAlign: 'center',
                              verticalAlign: 'middle',
                            }}
                          >
                            <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: '3px' }}>
                              <span style={{ fontSize: '0.7rem', color: '#f87171', fontWeight: 700, background: 'rgba(239, 68, 68, 0.1)', padding: '2px 6px', borderRadius: '4px', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                                🔒 Closed
                              </span>
                              <span style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>
                                Off on {td.dayName}s
                              </span>
                            </div>
                          </td>
                        );
                      }

                      return (
                        <td
                          key={td.date}
                          style={{
                            padding: '0.5rem',
                            borderRight: '1px solid var(--border-medium)',
                            verticalAlign: 'top',
                            background: td.isToday ? 'rgba(16, 185, 129, 0.02)' : 'transparent',
                          }}
                        >
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', minHeight: '60px' }}>
                            {dayBookings.length === 0 ? (
                              <button
                                type="button"
                                onClick={() => handleOpenBookingModal(doc, td.date)}
                                style={{
                                  border: '1px dashed var(--border-medium)',
                                  background: 'transparent',
                                  borderRadius: '4px',
                                  padding: '8px 4px',
                                  fontSize: '0.68rem',
                                  color: 'var(--text-tertiary)',
                                  cursor: 'pointer',
                                  textAlign: 'center',
                                  height: '100%',
                                }}
                              >
                                + Book 30m
                              </button>
                            ) : (
                              dayBookings.map((b) => (
                                <div
                                  key={b.id}
                                  style={{
                                    padding: '4px 6px',
                                    borderRadius: '4px',
                                    background: 'rgba(59, 130, 246, 0.1)',
                                    border: '1px solid rgba(59, 130, 246, 0.25)',
                                    fontSize: '0.7rem',
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center',
                                  }}
                                >
                                  <div>
                                    <strong style={{ color: 'var(--text-primary)', display: 'block' }}>
                                      {(b.start_time || '').slice(11, 16)} • {b.customer_name}
                                    </strong>
                                    <span style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>
                                      {b.special_requests || 'Consultation'}
                                    </span>
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() => handleCancelAppointment(b.id, b.customer_phone)}
                                    style={{ background: 'none', border: 'none', color: '#f43f5e', cursor: 'pointer', padding: '1px' }}
                                    title="Cancel appointment"
                                  >
                                    <X size={11} />
                                  </button>
                                </div>
                              ))
                            )}
                          </div>
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
         VIEW 2: 30-MINUTE DAY SLOTS VIEW
         ========================================================================= */}
      {viewMode === 'day' && (
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          <div style={{ padding: '0.85rem 1.25rem', background: 'var(--bg-surface-elevated)', borderBottom: '1px solid var(--border-medium)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              🕒 30-Minute Consultation Slots: {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' })}
            </span>
            <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
              Clinical Hours: 09:00 AM – 06:30 PM (30m increments)
            </span>
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '850px', textAlign: 'left' }}>
            <thead>
              <tr style={{ background: 'var(--bg-card)', borderBottom: '1px solid var(--border-medium)' }}>
                <th style={{ width: '220px', padding: '0.75rem 1rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', borderRight: '1px solid var(--border-medium)' }}>
                  DOCTOR / SPECIALIST
                </th>
                {clinicSlots.map((slot) => (
                  <th key={slot} style={{ padding: '0.6rem 0.4rem', fontSize: '0.72rem', textAlign: 'center', color: 'var(--text-secondary)', borderRight: '1px solid var(--border-medium)', minWidth: '60px' }}>
                    {slot}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredDoctors.map((doc, idx) => {
                const isAvailToday = isDoctorAvailableOnDay(doc, selectedDate);
                const dayBookings = getAppointmentsForDoctorAndDate(doc.id, selectedDate);

                return (
                  <tr key={doc.id} style={{ borderBottom: '1px solid var(--border-medium)', background: idx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.015)' }}>
                    <td style={{ padding: '0.75rem 1rem', borderRight: '1px solid var(--border-medium)' }}>
                      <div style={{ fontWeight: 600, fontSize: '0.84rem', color: 'var(--text-primary)' }}>{doc.name}</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                        {doc.section} • {isAvailToday ? 'Open Today' : 'Closed Today'}
                      </div>
                    </td>

                    {clinicSlots.map((slot) => {
                      if (!isAvailToday) {
                        return (
                          <td key={slot} style={{ padding: '4px', borderRight: '1px solid var(--border-medium)', background: 'rgba(239, 68, 68, 0.04)', textAlign: 'center' }}>
                            <span style={{ fontSize: '0.65rem', color: '#f87171' }}>🔒</span>
                          </td>
                        );
                      }

                      const matched = dayBookings.find((b) => {
                        const bTime = (b.start_time || '').slice(11, 16);
                        return bTime === slot;
                      });

                      return (
                        <td
                          key={slot}
                          style={{
                            padding: '4px',
                            borderRight: '1px solid var(--border-medium)',
                            background: matched ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                            textAlign: 'center',
                            verticalAlign: 'middle',
                          }}
                        >
                          {matched ? (
                            <div
                              title={`${matched.customer_name}\n${matched.special_requests || 'Consultation'}`}
                              style={{
                                fontSize: '0.66rem',
                                fontWeight: 700,
                                color: '#3b82f6',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                                padding: '2px',
                                borderRadius: '3px',
                                background: 'rgba(59, 130, 246, 0.2)',
                              }}
                            >
                              {matched.customer_name.split(' ')[0]}
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleOpenBookingModal(doc, selectedDate, slot)}
                              style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--text-tertiary)', fontSize: '0.7rem' }}
                              title={`Schedule 30m appointment at ${slot}`}
                            >
                              +
                            </button>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* =========================================================================
         VIEW 3: APPOINTMENT TABLE (LIST VIEW)
         ========================================================================= */}
      {viewMode === 'list' && (
        <div className="card" style={{ padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div style={{ position: 'relative', width: '300px' }}>
              <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)' }} />
              <input
                type="text"
                className="form-input"
                placeholder="Search patient name, phone, or symptom..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ paddingLeft: '32px', fontSize: '0.8rem' }}
              />
            </div>

            <button
              type="button"
              className="btn-primary"
              onClick={() => handleOpenBookingModal()}
              style={{ fontSize: '0.78rem', padding: '0.35rem 0.85rem' }}
            >
              <Plus size={14} /> Schedule Appointment
            </button>
          </div>

          {activeAppointments.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-tertiary)' }}>
              No appointments scheduled.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.82rem' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-surface-elevated)', borderBottom: '1px solid var(--border-medium)', color: 'var(--text-tertiary)', fontSize: '0.74rem' }}>
                    <th style={{ padding: '0.65rem 0.85rem' }}>APPOINTMENT ID</th>
                    <th style={{ padding: '0.65rem 0.85rem' }}>PATIENT NAME & PHONE</th>
                    <th style={{ padding: '0.65rem 0.85rem' }}>DOCTOR / SPECIALIST</th>
                    <th style={{ padding: '0.65rem 0.85rem' }}>DATE & 30M SLOT</th>
                    <th style={{ padding: '0.65rem 0.85rem' }}>SYMPTOMS / NOTES</th>
                    <th style={{ padding: '0.65rem 0.85rem', textAlign: 'right' }}>ACTION</th>
                  </tr>
                </thead>
                <tbody>
                  {activeAppointments.map((b) => {
                    const doc = doctors.find((d) => d.id === b.resource_id);
                    const isCancelling = cancellingId === b.id;

                    return (
                      <tr key={b.id} style={{ borderBottom: '1px solid var(--border-medium)' }}>
                        <td style={{ padding: '0.75rem 0.85rem', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: '#3b82f6', fontWeight: 600 }}>
                          {b.id}
                        </td>
                        <td style={{ padding: '0.75rem 0.85rem' }}>
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{b.customer_name}</div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>{b.customer_phone}</div>
                        </td>
                        <td style={{ padding: '0.75rem 0.85rem' }}>
                          <div style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{doc?.name || 'Assigned Doctor'}</div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>{doc?.section || 'Specialist Consultation'}</div>
                        </td>
                        <td style={{ padding: '0.75rem 0.85rem' }}>
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                            {(b.start_time || '').slice(0, 10)}
                          </div>
                          <div style={{ fontSize: '0.72rem', color: '#3b82f6', fontFamily: 'var(--font-mono)' }}>
                            {(b.start_time || '').slice(11, 16)} — {(b.end_time || '').slice(11, 16) || addMinutesToTime((b.start_time || '').slice(11, 16), 30)} (30m)
                          </div>
                        </td>
                        <td style={{ padding: '0.75rem 0.85rem', color: 'var(--text-secondary)', fontSize: '0.76rem', maxWidth: '240px' }}>
                          {b.special_requests || '—'}
                        </td>
                        <td style={{ padding: '0.75rem 0.85rem', textAlign: 'right' }}>
                          <button
                            type="button"
                            className="btn-secondary"
                            onClick={() => handleCancelAppointment(b.id, b.customer_phone)}
                            disabled={isCancelling}
                            style={{ color: '#f43f5e', fontSize: '0.74rem', padding: '0.25rem 0.55rem' }}
                            title="Cancel appointment"
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
         VIEW 4: MANAGE DOCTORS ROSTER
         ========================================================================= */}
      {viewMode === 'doctors' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', alignItems: 'flex-start' }}>
          {/* Add Doctor Form */}
          <form onSubmit={handleAddDoctor} className="card">
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Plus size={18} color="var(--primary, #3b82f6)" />
              Add Doctor / Specialist
            </div>
            <div className="card-desc">
              Register licensed practitioners and specialists taking patient appointments.
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">Doctor Name & Title *</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Dr. Rajesh Sharma (Senior Orthodontist)"
                value={newDoctor.name}
                onChange={(e) => setNewDoctor((prev) => ({ ...prev, name: e.target.value }))}
                required
              />
            </div>

            <div className="form-group" style={{ marginBottom: '1.25rem' }}>
              <label className="form-label">Specialization / Department</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Orthodontics, Pediatric Dentistry, General Medicine"
                value={newDoctor.section}
                onChange={(e) => setNewDoctor((prev) => ({ ...prev, section: e.target.value }))}
              />
            </div>

            <button
              type="submit"
              className="btn-primary"
              disabled={isSubmitting}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              <Plus size={16} /> {isSubmitting ? 'Registering...' : 'Register Doctor to Practice'}
            </button>
          </form>

          {/* Active Doctors List */}
          <div className="card">
            <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Clinic Practice Doctors ({doctors.length})</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', maxHeight: '420px', overflowY: 'auto', marginTop: '0.75rem' }}>
              {doctors.map((doc) => (
                <div
                  key={doc.id}
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
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.84rem' }}>{doc.name}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '2px', display: 'flex', gap: '8px' }}>
                      <span>🩺 {doc.section || 'General Practice'}</span>
                      <span>📅 Working: {getDoctorAvailableDays(doc).join(' • ')}</span>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleDeleteDoctor(doc.id, doc.name)}
                    style={{ background: 'none', border: 'none', color: '#f43f5e', cursor: 'pointer', padding: '4px' }}
                    title={`Delete ${doc.name}`}
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
         NEW PATIENT APPOINTMENT MODAL
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
                <div style={{ width: '30px', height: '30px', borderRadius: '6px', background: 'rgba(59, 130, 246, 0.12)', color: '#3b82f6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Stethoscope size={16} />
                </div>
                <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Schedule 30m Patient Appointment
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

            <form onSubmit={handleCreateAppointment} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Patient Full Name *</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Rahul Sharma"
                  value={newBooking.customer_name}
                  onChange={(e) => setNewBooking((prev) => ({ ...prev, customer_name: e.target.value }))}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Patient Contact Phone *</label>
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
                <label className="form-label">Doctor / Specialist *</label>
                <select
                  className="form-input"
                  value={newBooking.resource_id}
                  onChange={(e) => setNewBooking((prev) => ({ ...prev, resource_id: e.target.value }))}
                  required
                >
                  <option value="">Select doctor...</option>
                  {doctors.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} ({d.section || 'Specialist'})
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Appointment Date *</label>
                  <input
                    type="date"
                    className="form-input"
                    value={newBooking.start_date}
                    onChange={(e) => setNewBooking((prev) => ({ ...prev, start_date: e.target.value }))}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">30m Time Slot *</label>
                  <select
                    className="form-input"
                    value={newBooking.start_time}
                    onChange={(e) => setNewBooking((prev) => ({ ...prev, start_time: e.target.value }))}
                  >
                    {clinicSlots.map((slot) => (
                      <option key={slot} value={slot}>{slot}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Doctor Off Warning */}
              {isDoctorOffOnBookingDate && (
                <div
                  style={{
                    padding: '0.65rem 0.85rem',
                    borderRadius: '6px',
                    background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.25)',
                    color: '#f87171',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                  }}
                >
                  ⚠️ Warning: {currentModalDoctor.name} is scheduled OFF on {currentBookingDayName}s (Clinic Closed).
                </div>
              )}

              <div className="form-group">
                <label className="form-label">Consultation Notes / Patient Symptoms</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Routine Scaling & Cleaning, Toothache, Braces Wire Check"
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
