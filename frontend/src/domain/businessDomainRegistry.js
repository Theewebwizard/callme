/**
 * Modular Business Domain Registry
 *
 * Provides declarative business domain configurations, industry normalization,
 * and modular domain cards/features tailored to each business type.
 *
 * Eliminates repetitive hardcoding across different industries and keeps
 * domain capabilities (menus, tables, clinical suites, hotel rooms) modular.
 */

import {
  Utensils,
  Stethoscope,
  Bed,
  Scissors,
  Briefcase,
  Database,
} from 'lucide-react';

export function getCanonicalIndustry(rawIndustry) {
  if (!rawIndustry || typeof rawIndustry !== 'string') return 'other';
  const clean = rawIndustry.toLowerCase().trim();

  if (
    clean.includes('restaurant') ||
    clean.includes('dining') ||
    clean.includes('cafe') ||
    clean.includes('food') ||
    clean.includes('bistro') ||
    clean.includes('bakery') ||
    clean.includes('eatery') ||
    clean.includes('bar') ||
    clean.includes('pub') ||
    clean.includes('catering')
  ) {
    return 'restaurant';
  }

  // Check hotel / hospitality BEFORE clinic to prevent 'hospitality' falsely matching 'hospital'
  if (
    clean.includes('hotel') ||
    clean.includes('resort') ||
    clean.includes('hospitality') ||
    clean.includes('stay') ||
    clean.includes('lodging') ||
    clean.includes('suites')
  ) {
    return 'hotel';
  }

  if (
    clean.includes('clinic') ||
    clean.includes('dental') ||
    clean.includes('doctor') ||
    clean.includes('health') ||
    clean.includes('medical') ||
    (clean.includes('hospital') && !clean.includes('hospitality')) ||
    clean.includes('therapy')
  ) {
    return 'clinic';
  }

  if (
    clean.includes('salon') ||
    clean.includes('spa') ||
    clean.includes('stylist') ||
    clean.includes('wellness') ||
    clean.includes('aesthetic')
  ) {
    return 'salon';
  }

  if (
    clean.includes('astrology') ||
    clean.includes('spiritual') ||
    clean.includes('consulting') ||
    clean.includes('legal') ||
    clean.includes('service')
  ) {
    return 'services';
  }

  return 'other';
}

export const DOMAIN_CONFIGS = {
  restaurant: {
    key: 'restaurant',
    name: 'Restaurant & Dining',
    hasMenu: true,
    menuConfig: {
      title: 'Restaurant Menu & Semantic Pricing Store',
      shortTitle: 'Menu & Pricing',
      icon: Utensils,
      description: 'Upload dishes, categories, and prices so your receptionist answers price queries in real time.',
    },
    resourceConfig: {
      title: 'Dining Tables & Seating',
      shortTitle: 'Tables & Seating',
      subtitle: 'Manage bookable tables and private booths for conflict-free dining reservations.',
      noun: 'Dining Table / Seating Area',
      icon: Utensils,
      calendarTitle: 'Dining Reservations Timeline',
      namePlaceholder: 'e.g. Table 4 (Window) or VIP Booth 2',
      sectionPlaceholder: 'e.g. Main Dining, Terrace, Rooftop, VIP Lounge',
      capacityLabel: 'Seating Capacity (Guests)',
      defaultSection: 'Main Dining',
      defaultType: 'table',
      allowedTypes: [
        { value: 'table', label: 'Dining Table' },
        { value: 'booth', label: 'Private Booth' },
        { value: 'terrace', label: 'Terrace Seating' },
        { value: 'bar', label: 'Bar Counter' },
        { value: 'private_room', label: 'Private Dining Room' },
      ],
    },
  },

  clinic: {
    key: 'clinic',
    name: 'Clinic & Healthcare',
    hasMenu: false, // Menus strictly disabled for medical / clinic
    hasTreatments: true,
    treatmentConfig: {
      title: 'Clinic Treatments, Services & Fee Store',
      shortTitle: 'Treatments & Fees',
      icon: Stethoscope,
      description: 'Upload and manage clinical procedures, consultation charges, doctor specializations, and patient preparation notes so your receptionist answers fee queries in real time.',
    },
    resourceConfig: {
      title: 'Consultation Suites & Doctors',
      shortTitle: 'Suites & Doctors',
      subtitle: 'Register consultation rooms and doctors for conflict-free patient appointments.',
      noun: 'Consultation Suite / Doctor',
      icon: Stethoscope,
      calendarTitle: 'Patient Appointments Timeline',
      namePlaceholder: 'e.g. Dr. Sharma (Orthodontics) or Suite 101',
      sectionPlaceholder: 'e.g. Dental Wing, General OPD, Consultation Block B',
      capacityLabel: 'Patient Capacity',
      defaultSection: 'Consultation Wing',
      defaultType: 'clinic_room',
      allowedTypes: [
        { value: 'clinic_room', label: 'Consultation Suite / Examination Room' },
        { value: 'practitioner', label: 'Doctor / Specialist' },
        { value: 'procedure_room', label: 'Procedure / Dental Bay' },
        { value: 'therapy_room', label: 'Therapy & Recovery Room' },
      ],
    },
  },

  hotel: {
    key: 'hotel',
    name: 'Hotel & Hospitality',
    hasMenu: false,
    hasRooms: true,
    roomConfig: {
      title: 'Hotel Room Types, Rates & Amenities Store',
      shortTitle: 'Room Types & Rates',
      icon: Bed,
      description: 'Upload and manage room tiers, nightly tariffs, bed configurations, and amenities so your receptionist answers rate and room inquiries in real time.',
    },
    resourceConfig: {
      title: 'Rooms & Suites Inventory',
      shortTitle: 'Units & Calendar',
      subtitle: 'Manage reservable rooms, luxury suites, and conference halls.',
      noun: 'Room / Suite',
      icon: Bed,
      calendarTitle: 'Room Occupancy Timeline',
      namePlaceholder: 'e.g. Deluxe Room 304 or Executive Penthouse Suite',
      sectionPlaceholder: 'e.g. Ocean Wing, Floor 3, Poolside Villas',
      capacityLabel: 'Max Guests (Occupancy)',
      defaultSection: 'Main Building',
      defaultType: 'room',
      allowedTypes: [
        { value: 'room', label: 'Standard Hotel Room' },
        { value: 'suite', label: 'Executive Suite' },
        { value: 'deluxe', label: 'Deluxe Suite / Villa' },
        { value: 'hall', label: 'Banquet / Conference Hall' },
      ],
    },
  },

  salon: {
    key: 'salon',
    name: 'Salon & Spa Wellness',
    hasMenu: false,
    resourceConfig: {
      title: 'Stylists & Service Stations',
      shortTitle: 'Stylists & Stations',
      subtitle: 'Manage hair stations, massage suites, and specialist staff.',
      noun: 'Station / Stylist',
      icon: Scissors,
      calendarTitle: 'Client Appointment Schedule',
      namePlaceholder: 'e.g. Chair 3 (Senior Stylist Priya) or Spa Suite 1',
      sectionPlaceholder: 'e.g. Hair Studio, Nail Bar, Facial Suite',
      capacityLabel: 'Client Capacity',
      defaultSection: 'Main Salon Floor',
      defaultType: 'service_staff',
      allowedTypes: [
        { value: 'service_staff', label: 'Stylist / Specialist' },
        { value: 'desk', label: 'Styling Chair / Station' },
        { value: 'treatment_room', label: 'Spa Treatment Room' },
      ],
    },
  },

  services: {
    key: 'services',
    name: 'Consulting & Services',
    hasMenu: false,
    resourceConfig: {
      title: 'Consultation Desks & Offices',
      shortTitle: 'Desks & Offices',
      subtitle: 'Manage advisor suites, consultation desks, and meeting rooms.',
      noun: 'Consultation Desk / Office',
      icon: Briefcase,
      calendarTitle: 'Client Consultation Calendar',
      namePlaceholder: 'e.g. Consultation Desk 1 or Meeting Room A',
      sectionPlaceholder: 'e.g. Main Office, Executive Suite, Floor 2',
      capacityLabel: 'Client Capacity',
      defaultSection: 'Main Office',
      defaultType: 'desk',
      allowedTypes: [
        { value: 'desk', label: 'Consultation Desk' },
        { value: 'room', label: 'Private Consultation Room' },
        { value: 'consultant', label: 'Advisor / Consultant' },
      ],
    },
  },

  other: {
    key: 'other',
    name: 'Business Workspace',
    hasMenu: false,
    resourceConfig: {
      title: 'Resource Inventory & Bookings',
      shortTitle: 'Resource Inventory',
      subtitle: 'Register bookable units and meeting resources for conflict-free scheduling.',
      noun: 'Reservable Resource',
      icon: Database,
      calendarTitle: 'Resource Bookings Schedule',
      namePlaceholder: 'e.g. Desk 1 or Suite A',
      sectionPlaceholder: 'e.g. Area 1, Floor 2',
      capacityLabel: 'Capacity',
      defaultSection: 'Main Section',
      defaultType: 'desk',
      allowedTypes: [
        { value: 'desk', label: 'Service Desk' },
        { value: 'room', label: 'Meeting Room / Suite' },
        { value: 'service_staff', label: 'Service Staff' },
      ],
    },
  },
};

/**
 * Retrieve domain configuration for a business instance.
 */
export function getDomainForBusiness(business) {
  const canonicalKey = getCanonicalIndustry(business?.industry);
  return DOMAIN_CONFIGS[canonicalKey] || DOMAIN_CONFIGS.other;
}
