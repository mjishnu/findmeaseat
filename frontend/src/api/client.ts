// Types mirror backend/app/schemas.py — keep the two in sync by hand.

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

export interface ParsedAvailability {
  raw: string
  status: 'AVAILABLE' | 'RAC' | 'WAITLIST' | 'NOT_BOOKABLE' | 'UNKNOWN'
  quota: string | null
  seats: number | null
  series_wl: number | null
  current_wl: number | null
}

export interface Recommendation {
  rank: number
  book_from: string
  book_to: string
  board_at: string
  alight_at: string
  action: string
  availability: ParsedAvailability
  probability: number
  score: number
  booked_distance_km: number
  extra_km: number
  fare: number
  extra_fare: number
  requires_boarding_change: boolean
  notes: string[]
}

export interface UserLeg {
  source: string
  destination: string
  distance_km: number
  fare: number
  availability: ParsedAvailability | null
}

export interface RecommendationResponse {
  train_number: string
  train_name: string
  journey_date: string
  user_leg: UserLeg
  pairs_evaluated: number
  recommendations: Recommendation[]
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
  })
  return request<RecommendationResponse>(`/api/find-optimal-route?${params}`, signal)
}
