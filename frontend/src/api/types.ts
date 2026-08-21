import type { AvailabilityStatus, BookingQuota, RecommendationNoteCode, TravelClass } from './constants'

// ── Shared Domain ────────────────────────────────────────────────────────────

export interface TrainIdentity {
  train_number: string
  train_name: string
}

export interface StationStop {
  code: string
  name: string
  distance_km: number
  day_offset?: number
}

export interface Station {
  code: string
  name: string
  city: string
}

// ── Availability ─────────────────────────────────────────────────────────────

export interface ParsedAvailability {
  raw: string
  status: AvailabilityStatus
}

export interface ClassAvailability {
  travel_class: TravelClass
  availability: ParsedAvailability
  probability: number // -1 when confirmtkt has no estimate
  fare: number
}

// ── Route ────────────────────────────────────────────────────────────────────

export interface TrainRoute extends TrainIdentity {
  stations: StationStop[]
  running_days?: string // "1111111", Mon→Sun
  classes?: TravelClass[]
}

// ── Seat-finder ──────────────────────────────────────────────────────────────

export interface Recommendation {
  rank: number
  book_from: string
  book_to: string
  board_at: string
  alight_at: string
  availability: ParsedAvailability
  probability: number // -1 when confirmtkt has no estimate
  extra_km: number
  fare: number
  extra_fare: number
  coverage_pct: number // 1.0 for full coverage, < 1.0 for partial
  notes: RecommendationNoteCode[]
}

export interface UserLeg {
  source: string
  destination: string
  distance_km: number
  fare: number
  availability: ParsedAvailability | null
}

export interface SwitchAlternative extends ClassAvailability {
  quota: BookingQuota
  fare_delta: number
}

export interface RecommendationResponse extends TrainIdentity {
  journey_date: string
  travel_class: TravelClass
  quota: BookingQuota
  user_leg: UserLeg
  pairs_evaluated: number
  pairs_skipped: number
  recommendations: Recommendation[]
  alternatives: SwitchAlternative[]
  partial: boolean
  min_coverage_pct: number
}

export interface SearchQuery {
  trainNumber: string
  source: string
  destination: string
  date: string // YYYY-MM-DD
  travelClass: TravelClass
  quota: BookingQuota
  partial?: boolean
  minCoveragePct?: number
  requireConnect?: boolean
}

// ── Manifest protocol ────────────────────────────────────────────────────────

export interface FetchDescriptor {
  url: string
  headers: Record<string, string>
  fetch_id: string
  method?: string
  body?: string
}

export interface ManifestResponse {
  manifest_id: string
  fetches: FetchDescriptor[]
  total_count?: number
  cached_count?: number
}

export interface FetchResult {
  fetch_id: string
  status: number
  body: string
}

export type ManifestProgressPhase =
  | 'init'
  | 'routing'
  | 'fetching_pairs'
  | 'verifying'
  | 'complete'

export interface ManifestProgress {
  phase: ManifestProgressPhase
  completedUnits: number
  totalUnits: number
  percent: number // 0 to 100
  label: string
  subLabel?: string
  currentPhaseStep?: number // 1 for checking routes, 2 for verifying availability
  totalPhaseSteps?: number // 2
}

export type ProgressCallback = (progress: ManifestProgress) => void

// ── Train search ─────────────────────────────────────────────────────────────

export interface TrainBetween extends TrainIdentity {
  from_code: string
  from_name: string
  to_code: string
  to_name: string
  departure_time: string
  arrival_time: string
  duration_min: number
  running_days: string // "1111111", Mon→Sun
  has_pantry: boolean
  distance_km: number
  general: ClassAvailability[]
  tatkal: ClassAvailability[]
  classes: ClassAvailability[]
  allowed_quotas: string[]
}

export interface TrainsBetweenResponse {
  source: string
  destination: string
  journey_date: string
  trains: TrainBetween[]
}
