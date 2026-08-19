// ── Manifest execution & confirmtkt payload stripping ────────────────────────
// Internal module — not re-exported from the barrel.

import type { FetchDescriptor, FetchResult, ManifestResponse } from './types'
import { postRequest } from './http'

// ── Confirmtkt pre-parser ────────────────────────────────────────────────────
// The backend only reads a small subset of fields from each train dict.
// Strip everything else client-side to shrink the payload sent to /process.

const CACHE_ENTRY_KEYS = ['availability', 'availabilityDisplayName', 'fare', 'predictionPercentage'] as const

function stripCacheEntries(cache: Record<string, unknown> | undefined): Record<string, unknown> | undefined {
  if (!cache || typeof cache !== 'object') return cache
  const out: Record<string, unknown> = {}
  for (const [cls, entry] of Object.entries(cache)) {
    if (!entry || typeof entry !== 'object') continue
    const slim: Record<string, unknown> = {}
    for (const k of CACHE_ENTRY_KEYS) {
      if (k in (entry as Record<string, unknown>)) { slim[k] = (entry as Record<string, unknown>)[k] }
    }
    out[cls] = slim
  }
  return out
}

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

const CONFIRMTKT_HOST = 'cttrainsapi.confirmtkt.com'

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
    if (filterTrainNumber) {
      trains = trains.filter((t) => String(t.trainNumber) === filterTrainNumber)
    }
    data.trainList = trains.map((t: Record<string, unknown>) => stripTrain(t))
    delete data.nearbyTrains
    delete data.nearbyDates
    delete data.alternateTravelModes
    delete data.alternateTravelModesMiddle
    return JSON.stringify(payload)
  } catch {
    return body
  }
}

// ── Fetch with retry ─────────────────────────────────────────────────────────

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

// ── Manifest loop ────────────────────────────────────────────────────────────

function isContinue(r: unknown): r is ManifestResponse {
  return typeof r === 'object' && r !== null && 'fetches' in r &&
    Array.isArray((r as Record<string, unknown>).fetches) &&
    ((r as Record<string, unknown>).fetches as unknown[]).length > 0
}

export async function executeManifest<T>(
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
