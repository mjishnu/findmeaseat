// ── Domain constants ─────────────────────────────────────────────────────────
// Values are IRCTC codes the backend enums accept.

export const TRAVEL_CLASSES = [
  { value: 'SL', label: 'Sleeper (SL)' },
  { value: '3A', label: 'AC 3-Tier (3A)' },
  { value: '3E', label: 'AC 3-Tier Economy (3E)' },
  { value: '2A', label: 'AC 2-Tier (2A)' },
  { value: '1A', label: 'AC First (1A)' },
  { value: 'CC', label: 'Chair Car (CC)' },
  { value: 'EC', label: 'Exec Chair (EC)' },
  { value: '2S', label: 'Second Sitting (2S)' },
  { value: 'FC', label: 'First Class (FC)' },
] as const

export type TravelClass = (typeof TRAVEL_CLASSES)[number]['value']

export const DEFAULT_TRAVEL_CLASS: TravelClass = 'SL'

export const QUOTAS = [
  { value: 'GN', label: 'General' },
  { value: 'TQ', label: 'Tatkal' },
  { value: 'LD', label: 'Ladies' },
  { value: 'SS', label: 'Senior Citizen' },
] as const

export type BookingQuota = (typeof QUOTAS)[number]['value']

export const DEFAULT_QUOTA: BookingQuota = 'GN'

export const RECOMMENDATION_NOTE_CODE = {
  QUOTA_TATKAL: 1,
  QUOTA_LADIES: 2,
  QUOTA_SENIOR: 3,
  BOARDING_CHANGE: 4,
  EXTRA_FARE: 5,
  ALIGHT_CHANGE: 6,
  MISSING_PREDICTION: 7,
  PARTIAL_COVERAGE: 8,
} as const

export type RecommendationNoteCode =
  (typeof RECOMMENDATION_NOTE_CODE)[keyof typeof RECOMMENDATION_NOTE_CODE]

// Must stay in sync with AvailabilityStatus IntEnum in backend/app/schemas/
export const AvailabilityStatus = {
  NOT_BOOKABLE: 0,
  UNKNOWN: 1,
  WAITLIST: 2,
  RAC: 3,
  AVAILABLE: 4,
} as const

export type AvailabilityStatus = (typeof AvailabilityStatus)[keyof typeof AvailabilityStatus]
