// Types mirror backend/app/schemas.py — keep the two in sync by hand.

// Values are the IRCTC class codes the backend's TravelClass enum accepts.
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

export const RECOMMENDATION_NOTE_CODE = {
  QUOTA_TATKAL: 1,
  QUOTA_LADIES: 2,
  QUOTA_SENIOR: 3,
  BOARDING_CHANGE: 4,
  EXTRA_FARE: 5,
  ALIGHT_CHANGE: 6,
  MISSING_PREDICTION: 7,
} as const

export type RecommendationNoteCode =
  (typeof RECOMMENDATION_NOTE_CODE)[keyof typeof RECOMMENDATION_NOTE_CODE]

// Booking quota for the seat-finder. Values are the codes the backend's
// BookingQuota enum accepts (General vs Tatkal).
export const QUOTAS = [
  { value: 'GN', label: 'General' },
  { value: 'TQ', label: 'Tatkal' },
  { value: 'LD', label: 'Ladies' },
  { value: 'SS', label: 'Senior Citizen' },
] as const

export type BookingQuota = (typeof QUOTAS)[number]['value']
export const DEFAULT_QUOTA: BookingQuota = 'GN'

export interface StationStop {
  code: string
  name: string
  distance_km: number
}

export interface TrainRoute {
  train_number: string
  train_name: string
  stations: StationStop[]
}

// Must stay in sync with AvailabilityStatus IntEnum in backend/app/schemas.py
export const AvailabilityStatus = {
  NOT_BOOKABLE: 0,
  UNKNOWN: 1,
  WAITLIST: 2,
  RAC: 3,
  AVAILABLE: 4,
} as const

export type AvailabilityStatus = (typeof AvailabilityStatus)[keyof typeof AvailabilityStatus]

export interface ParsedAvailability {
  raw: string
  status: AvailabilityStatus
  quota: string | null
  seats: number | null
  current_wl: number | null
}

export interface Recommendation {
  rank: number
  book_from: string
  book_to: string
  board_at: string
  alight_at: string
  availability: ParsedAvailability
  probability: number  // -1 when confirmtkt has no estimate
  extra_km: number
  fare: number | null
  extra_fare: number | null
  notes: RecommendationNoteCode[]
}

export interface UserLeg {
  source: string
  destination: string
  distance_km: number
  fare: number | null
  availability: ParsedAvailability | null
}

export interface SwitchAlternative {
  travel_class: TravelClass
  quota: BookingQuota
  availability: ParsedAvailability
  probability: number  // -1 = no estimate
  fare: number | null
  fare_delta: number | null
}

export interface RecommendationResponse {
  train_number: string
  train_name: string
  journey_date: string
  travel_class: TravelClass
  quota: BookingQuota
  user_leg: UserLeg
  pairs_evaluated: number
  pairs_skipped: number
  recommendations: Recommendation[]
  alternatives: SwitchAlternative[]
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal })
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body: unknown = await res.json()
      if (
        typeof body === 'object' &&
        body !== null &&
        'detail' in body &&
        typeof body.detail === 'string'
      ) {
        detail = body.detail
      }
    } catch {
      // non-JSON error body — keep the default message
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export function getTrainRoute(trainNumber: string, signal?: AbortSignal): Promise<TrainRoute> {
  return request<TrainRoute>(`/api/trains/${encodeURIComponent(trainNumber)}`, signal)
}

export interface SearchQuery {
  trainNumber: string
  source: string
  destination: string
  date: string // YYYY-MM-DD
  travelClass: TravelClass
  quota: BookingQuota
}

export function findOptimalRoute(
  query: SearchQuery,
  signal?: AbortSignal,
): Promise<RecommendationResponse> {
  const params = new URLSearchParams({
    train_number: query.trainNumber,
    user_source: query.source,
    user_destination: query.destination,
    date: query.date,
    travel_class: query.travelClass,
    quota: query.quota,
  })
  return request<RecommendationResponse>(`/api/find-optimal-route?${params}`, signal)
}

// --- Train search (between stations) -----------------------------------------

export interface Station {
  code: string
  name: string
  city: string
}

export interface ClassAvailability {
  travel_class: TravelClass
  availability: ParsedAvailability
  probability: number  // -1 when confirmtkt has no estimate
  fare: number | null
}

export interface TrainBetween {
  train_number: string
  train_name: string
  from_code: string
  from_name: string
  to_code: string
  to_name: string
  departure_time: string
  arrival_time: string
  duration_min: number | null
  running_days: string // "1111111", Mon→Sun
  has_pantry: boolean
  distance_km: number | null
  general: ClassAvailability[]
  tatkal: ClassAvailability[]
  allowed_quotas: string[]
}

export interface TrainsBetweenResponse {
  source: string
  destination: string
  journey_date: string
  trains: TrainBetween[]
}

export interface TrainQuotaClasses {
  train_number: string
  from_code: string
  departure_time: string
  classes: ClassAvailability[]
}

export interface TrainsQuotaAvailabilityResponse {
  source: string
  destination: string
  journey_date: string
  quota: BookingQuota
  trains: TrainQuotaClasses[]
}

export function searchStations(q: string, signal?: AbortSignal): Promise<Station[]> {
  const params = new URLSearchParams({ q, limit: '8' })
  return request<Station[]>(`/api/stations?${params}`, signal)
}

export function searchTrainsBetween(
  source: string,
  destination: string,
  date: string, // YYYY-MM-DD
  signal?: AbortSignal,
): Promise<TrainsBetweenResponse> {
  const params = new URLSearchParams({ source, destination, date })
  return request<TrainsBetweenResponse>(`/api/trains-between?${params}`, signal)
}

export function searchTrainsQuotaAvailability(
  source: string,
  destination: string,
  date: string, // YYYY-MM-DD
  quota: BookingQuota,
  signal?: AbortSignal,
): Promise<TrainsQuotaAvailabilityResponse> {
  const params = new URLSearchParams({ source, destination, date, quota })
  return request<TrainsQuotaAvailabilityResponse>(`/api/trains-between/quota?${params}`, signal)
}
