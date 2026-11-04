import React, { useState } from 'react';
import {
  Database,
  Building2,
  Calendar,
  Utensils,
  Stethoscope,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { api } from '../api';
import RestaurantTableFloorView from './RestaurantTableFloorView';
import DoctorAppointmentCalendarView from './DoctorAppointmentCalendarView';
import HotelFloorGridView from './HotelFloorGridView';
import BookingCalendarView from './BookingCalendarView';
import { getDomainForBusiness } from '../domain/businessDomainRegistry';

export default function ResourceInventoryCard({
  business,
  resources = [],
  reservations = [],
  onRefresh,
  domainConfig: propDomainConfig,
}) {
  const domainConfig = propDomainConfig || getDomainForBusiness(business);

  // 1. Restaurant Domain -> Dedicated Table & Seating Management
  if (domainConfig.key === 'restaurant') {
    return (
      <RestaurantTableFloorView
        business={business}
        resources={resources}
        reservations={reservations}
        onRefresh={onRefresh}
      />
    );
  }

  // 2. Clinic Domain -> Dedicated Doctor Appointments & Schedule
  if (domainConfig.key === 'clinic') {
    return (
      <DoctorAppointmentCalendarView
        business={business}
        resources={resources}
        reservations={reservations}
        onRefresh={onRefresh}
      />
    );
  }

  // 3. Hotel Domain -> Dedicated Floor Grid & PMS
  if (domainConfig.key === 'hotel') {
    return (
      <HotelFloorGridView
        business={business}
        onLayoutUpdated={onRefresh}
      />
    );
  }

  // 4. Fallback (Salon, Professional Services, General Business)
  return (
    <BookingCalendarView
      business={business}
      domainConfig={domainConfig}
      resources={resources}
      reservations={reservations}
      onRefresh={onRefresh}
    />
  );
}
