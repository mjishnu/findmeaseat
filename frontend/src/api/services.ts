// ── Public API service functions ─────────────────────────────────────────────

import type { BookingQuota } from './constants'
import type {
  RecommendationResponse,
  SearchQuery,
  Station,
  TrainRoute,
  TrainsBetweenResponse,
} from './types'
import { ApiError } from './http'
import { request } from './http'
import { executeManifest } from './manifest'

export function getTrainRoute(trainNumber: string, signal?: AbortSignal): Promise<TrainRoute> {
  return executeManifest('/api/route/manifest', '/api/route/process',
    { train_number: trainNumber }, signal)
}

export async function findOptimalRoute(
  query: SearchQuery,
  signal?: AbortSignal,
): Promise<RecommendationResponse> {
  const execute = () =>
    executeManifest<RecommendationResponse>(
      '/api/seat-finder/manifest',
      '/api/seat-finder/process',
      {
        train_number: query.trainNumber,
        user_source: query.source,
        user_destination: query.destination,
        date: query.date,
        travel_class: query.travelClass,
        quota: query.quota,
        partial: query.partial ?? false,
        min_coverage_pct: query.minCoveragePct ?? 0.75,
        require_connect: query.requireConnect ?? true,
      },
      signal,
      query.trainNumber,
    )

  try {
    return await execute()
  } catch (err) {
    if (
      err instanceof ApiError &&
      err.status === 404 &&
      err.message.toLowerCase().includes('not found')
    ) {
      await getTrainRoute(query.trainNumber, signal)
      return await execute()
    }
    throw err
  }
}

export function searchStations(q: string, signal?: AbortSignal): Promise<Station[]> {
  const params = new URLSearchParams({ q, limit: '8' })
  return request<Station[]>(`/api/stations?${params}`, signal)
}

export function searchTrainsBetween(
  source: string,
  destination: string,
  date: string,
  quota: BookingQuota = 'GN',
  signal?: AbortSignal,
): Promise<TrainsBetweenResponse> {
  return executeManifest('/api/trains-between/manifest', '/api/trains-between/process',
    { source, destination, date, quota }, signal)
}
