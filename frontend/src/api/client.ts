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
  PARTIAL_COVERAGE: 8,
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
  fare: number
  extra_fare: number
  coverage_pct: number  // 1.0 for full coverage, < 1.0 for partial
  notes: RecommendationNoteCode[]
}

export interface UserLeg {
  source: string
  destination: string
  distance_km: number
  fare: number
  availability: ParsedAvailability | null
}

export interface SwitchAlternative {
  travel_class: TravelClass
  quota: BookingQuota
  availability: ParsedAvailability
  probability: number  // -1 = no estimate
  fare: number
  fare_delta: number
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
  partial: boolean
  min_coverage_pct: number
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
}

export interface FetchResult {
  fetch_id: string
  status: number
  body: string
}

async function postRequest<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const bodyString = JSON.stringify(body)
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }

  let reqBody: BodyInit = bodyString
  try {
    const stream = new Blob([bodyString]).stream().pipeThrough(new CompressionStream('gzip'))
    reqBody = await new Response(stream).arrayBuffer()
    headers['Content-Encoding'] = 'gzip'
  } catch (e) {
    // Fallback if CompressionStream is not available
  }

  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: reqBody,
    signal,
  })
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const err: unknown = await res.json()
      if (typeof err === 'object' && err !== null && 'detail' in err && typeof err.detail === 'string')
        detail = err.detail
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

// -- Confirmtkt response pre-parser ------------------------------------------
// The backend only reads a small subset of fields from each train dict.
// Strip everything else client-side to shrink the payload sent to /process.

/** Fields the backend reads from each availability cache entry. */
const CACHE_ENTRY_KEYS = ['availability', 'availabilityDisplayName', 'fare', 'predictionPercentage'] as const

function stripCacheEntries(cache: Record<string, unknown> | undefined): Record<string, unknown> | undefined {
  if (!cache || typeof cache !== 'object') return cache
  const out: Record<string, unknown> = {}
  for (const [cls, entry] of Object.entries(cache)) {
    if (!entry || typeof entry !== 'object') continue
    const slim: Record<string, unknown> = {}
    for (const k of CACHE_ENTRY_KEYS) {
      if (k in (entry as Record<string, unknown>)) slim[k] = (entry as Record<string, unknown>)[k]
    }
    out[cls] = slim
  }
  return out
}

/** Fields the backend reads from each train dict (top-level). */
const TRAIN_KEEP_KEYS = [
  'trainNumber', 'trainName',
  'fromStnCode', 'fromStnName', 'toStnCode', 'toStnName',
  'departureTime', 'arrivalTime', 'duration',
  'runningDays', 'hasPantry', 'distance',
  'avlClassesSorted', 'allowedQuotas',
] as const

const CACHE_KEYS = ['availabilityCache', 'availabilityCacheTatkal', 'availabilityCacheForQuota'] as const

function stripTrain(train: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const k of TRAIN_KEEP_KEYS) {
    if (k in train) out[k] = train[k]
  }
  for (const k of CACHE_KEYS) {
    out[k] = stripCacheEntries(train[k] as Record<string, unknown> | undefined) ?? {}
  }
  return out
}

/**
 * Pre-parse a confirmtkt search response: keep only the fields the backend
 * actually uses from each train in data.trainList.  Returns the slimmed JSON
 * string, or the original body unchanged if parsing fails.
 *
 * When `filterTrainNumber` is provided (seat-finder flow), only the matching
 * train is kept — the rest are dropped entirely.
 */
function preParseConfirmtktResponse(body: string, filterTrainNumber?: string): string {
  try {
    const payload = JSON.parse(body)
    const data = payload?.data
    if (!data || !Array.isArray(data.trainList)) return body
    let trains: Record<string, unknown>[] = data.trainList
    // Seat-finder: keep only the train we care about
    if (filterTrainNumber) {
      trains = trains.filter((t) => String(t.trainNumber) === filterTrainNumber)
    }
    data.trainList = trains.map((t: Record<string, unknown>) => stripTrain(t))
    // Also drop bulky top-level keys the backend never reads
    delete data.nearbyTrains
    delete data.nearbyDates
    delete data.alternateTravelModes
    delete data.alternateTravelModesMiddle
    return JSON.stringify(payload)
  } catch {
    return body // parsing failed — send the original
  }
}

const CONFIRMTKT_HOST = 'cttrainsapi.confirmtkt.com'

async function fetchWithRetry(
  f: FetchDescriptor, signal?: AbortSignal, retries = 3,
  filterTrainNumber?: string,
): Promise<FetchResult> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      if (attempt > 0) await new Promise(r => setTimeout(r, 500 * attempt))
      const res = await fetch(f.url, { 
        method: f.method || 'GET',
        headers: f.headers, 
        body: f.body,
        signal 
      })
      let body = await res.text()
      // Pre-parse confirmtkt responses to reduce payload size
      if (f.url.includes(CONFIRMTKT_HOST)) {
        body = preParseConfirmtktResponse(body, filterTrainNumber)
      }
      return { fetch_id: f.fetch_id, status: res.status, body }
    } catch {
      if (attempt === retries) break
    }
  }
  return { fetch_id: f.fetch_id, status: 0, body: '' }
}

function isContinue(r: unknown): r is ManifestResponse {
  return typeof r === 'object' && r !== null && 'fetches' in r &&
    Array.isArray((r as Record<string, unknown>).fetches) &&
    ((r as Record<string, unknown>).fetches as unknown[]).length > 0
}

async function executeManifest<T>(
  manifestUrl: string, processUrl: string, body: unknown, signal?: AbortSignal,
  filterTrainNumber?: string,
): Promise<T> {
  let response: unknown = await postRequest(manifestUrl, body, signal)

  if (!isContinue(response)) return response as T

  while (true) {
    const manifest = response as ManifestResponse
    const results = await Promise.all(
      manifest.fetches.map(f => fetchWithRetry(f, signal, 3, filterTrainNumber))
    )
    const validResults = results.filter(r => !r.body.includes('"trainList":[]'))
    response = await postRequest(processUrl,
      { manifest_id: manifest.manifest_id, results: validResults }, signal)
    if (!isContinue(response)) return response as T
  }
}

export function getTrainRoute(trainNumber: string, signal?: AbortSignal): Promise<TrainRoute> {
  return executeManifest('/api/route/manifest', '/api/route/process',
    { train_number: trainNumber }, signal)
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

export function findOptimalRoute(
  query: SearchQuery,
  signal?: AbortSignal,
): Promise<RecommendationResponse> {
  return executeManifest('/api/seat-finder/manifest', '/api/seat-finder/process', {
    train_number: query.trainNumber,
    user_source: query.source,
    user_destination: query.destination,
    date: query.date,
    travel_class: query.travelClass,
    quota: query.quota,
    partial: query.partial ?? false,
    min_coverage_pct: query.minCoveragePct ?? 0.75,
    require_connect: query.requireConnect ?? true,
  }, signal, query.trainNumber)
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
  fare: number
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

export function searchStations(q: string, signal?: AbortSignal): Promise<Station[]> {
  const params = new URLSearchParams({ q, limit: '8' })
  return request<Station[]>(`/api/stations?${params}`, signal)
}

export function searchTrainsBetween(
  source: string,
  destination: string,
  date: string, // YYYY-MM-DD
  quota: BookingQuota = 'GN',
  signal?: AbortSignal,
): Promise<TrainsBetweenResponse> {
  return executeManifest('/api/trains-between/manifest', '/api/trains-between/process',
    { source, destination, date, quota }, signal)
}

export function searchTrainsQuotaAvailability(
  source: string,
  destination: string,
  date: string, // YYYY-MM-DD
  quota: BookingQuota,
  signal?: AbortSignal,
): Promise<TrainsBetweenResponse> {
  return searchTrainsBetween(source, destination, date, quota, signal)
}
