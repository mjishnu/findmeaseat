// ── Manifest execution & payload stripping ──────────────────────────────────
// Internal module — not re-exported from the barrel.

import type { FetchDescriptor, FetchResult, ManifestResponse, ProgressCallback } from './types'
import { postRequest } from './http'

// ── Confirmtkt search pre-parser ─────────────────────────────────────────────
// The backend only reads a small subset of fields from each train dict.
// Strip everything else client-side to shrink the payload sent to /process.

type JsonRecord = Record<string, unknown>

function pick(obj: JsonRecord, keys: readonly string[]): JsonRecord {
  const result: JsonRecord = {}
  for (const k of keys) {
    if (k in obj) result[k] = obj[k]
  }
  return result
}

const CACHE_ENTRY_KEYS = ['availability', 'availabilityDisplayName', 'fare', 'predictionPercentage'] as const

function stripCacheEntries(cache?: JsonRecord): JsonRecord | undefined {
  if (!cache || typeof cache !== 'object') return cache

  const out: JsonRecord = {}
  for (const [cls, entry] of Object.entries(cache)) {
    if (entry && typeof entry === 'object') {
      out[cls] = pick(entry as JsonRecord, CACHE_ENTRY_KEYS)
    }
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

function stripTrain(train: JsonRecord): JsonRecord {
  const out = pick(train, TRAIN_KEEP_KEYS)
  for (const k of CACHE_KEYS) {
    out[k] = stripCacheEntries(train[k] as JsonRecord | undefined) ?? {}
  }
  return out
}

function preParseConfirmtktResponse(body: string, filterTrainNumber?: string): string {
  try {
    const payload = JSON.parse(body)
    const rawTrains = payload?.data?.trainList
    if (!Array.isArray(rawTrains)) return body

    const targetTrains = filterTrainNumber
      ? rawTrains.filter((t: JsonRecord) => String(t.trainNumber) === filterTrainNumber)
      : rawTrains

    return JSON.stringify({
      data: {
        trainList: targetTrains.map(stripTrain),
      },
    })
  } catch {
    return body
  }
}


// ── Confirmtkt live-verify pre-parser ────────────────────────────────────────

function stripVerifyResponse(body: string): string {
  try {
    const payload = JSON.parse(body)
    const data = payload?.data
    if (!data || !Array.isArray(data.avlDayList) || data.avlDayList.length === 0) return body
    const liveDay = data.avlDayList[0]
    const minimal = {
      data: {
        avlDayList: [
          {
            availablityStatus: liveDay?.availablityStatus,
            predictionPercentage: liveDay?.predictionPercentage,
          },
        ],
        fareInfo: {
          totalFare: data.fareInfo?.totalFare,
        },
      },
    }
    return JSON.stringify(minimal)
  } catch {
    return body
  }
}

// ── Erail pre-parsers ────────────────────────────────────────────────────────

function stripErailHeader(body: string): string {
  if (!body || body.toLowerCase().includes('train not found')) return body
  try {
    const segs = body.split('~~~~~~~~')
    if (segs.length < 2) return body
    let d1 = segs[0].split('~').filter((x) => x !== '')
    if (d1[1] && d1[1].length > 6) {
      d1 = d1.slice(1)
    }
    const d2 = segs[1].split('~').filter((x) => x !== '')
    if (d2.length > 12 && d1.length > 2) {
      const runningDays = d1.find((x) => x.length === 7 && /^[01]{7}$/.test(x)) || '1111111'
      const classes: string[] = []
      const known = new Set(['1A', '2A', '3A', '3E', 'CC', 'EC', 'EA', 'SL', '2S', 'FC'])
      for (const item of d2) {
        if (item.includes('|') && item.includes(':')) {
          const parts = item.split('|')
          for (const p of parts) {
            const code = p.split(':')[0]
            if (known.has(code) && !classes.includes(code)) {
              classes.push(code)
            }
          }
        }
      }
      return JSON.stringify({
        train_id: d2[12],
        train_name: d1[2],
        running_days: runningDays,
        classes,
      })
    }
  } catch {
    // fallback to raw body
  }
  return body
}

function stripErailRoute(body: string): string {
  if (!body) return body
  try {
    const stops: { code: string; name: string; distance_km: number; day_offset: number }[] = []
    for (const item of body.split('~^')) {
      const det = item.split('~').filter((x) => x !== '')
      if (det.length < 10) continue
      const distMatch = det[6].match(/-?\d[\d,]*(?:\.\d+)?/)
      if (!distMatch) continue
      const dist = Math.round(parseFloat(distMatch[0].replace(/,/g, '')))
      if (isNaN(dist) || dist < 0) continue
      const rawDay = parseInt(det[7], 10) || 1
      const dayOffset = Math.max(0, rawDay - 1)
      stops.push({ code: det[1], name: det[2], distance_km: dist, day_offset: dayOffset })
    }
    if (stops.length > 0) {
      return JSON.stringify({ stops })
    }
  } catch {
    // fallback to raw body
  }
  return body
}

// ── Fetch with retry ─────────────────────────────────────────────────────────

async function fetchWithRetry(
  f: FetchDescriptor,
  signal?: AbortSignal,
  retries = 3,
  filterTrainNumber?: string,
): Promise<FetchResult> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      if (attempt > 0) await new Promise((r) => setTimeout(r, 500 * attempt))
      const res = await fetch(f.url, {
        method: f.method || 'GET',
        headers: f.headers,
        body: f.body,
        signal,
      })
      let body = await res.text()
      if (f.url.includes('api/v1/trains/search')) {
        body = preParseConfirmtktResponse(body, filterTrainNumber)
      } else if (f.url.includes('api/v1/availability/fetchAvailability')) {
        body = stripVerifyResponse(body)
      } else if (f.url.includes('getTrains.aspx')) {
        body = stripErailHeader(body)
      } else if (f.url.includes('data.aspx')) {
        body = stripErailRoute(body)
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
  const fetches = (r as Partial<ManifestResponse>)?.fetches
  return Array.isArray(fetches) && fetches.length > 0
}

export async function executeManifest<T>(
  manifestUrl: string,
  processUrl: string,
  body: unknown,
  signal?: AbortSignal,
  filterTrainNumber?: string,
  onProgress?: ProgressCallback,
): Promise<T> {
  onProgress?.({
    phase: 'init',
    completedUnits: 0,
    totalUnits: 1,
    percent: 5,
    label: 'Finding station combinations…',
    subLabel: 'Preparing route search',
    currentPhaseStep: 1,
    totalPhaseSteps: 2,
  })

  let response = await postRequest(manifestUrl, body, signal)

  while (isContinue(response)) {
    const phaseConfig = response.fetches[0]?.fetch_id.startsWith('verify:')
      ? {
          phase: 'verifying' as const,
          label: 'Verifying seat availability for best options…',
          unitNoun: 'options verified',
          basePercent: 90,
          maxPercent: 98,
          step: 2,
        }
      : {
          phase: 'fetching_pairs' as const,
          label: 'Checking seat availability across route combinations…',
          unitNoun: 'routes checked',
          basePercent: 5,
          maxPercent: 90,
          step: 1,
        }

    const cachedCount = response.cached_count ?? 0
    const totalPairs = response.total_count ?? (cachedCount + response.fetches.length)
    let completedFetches = 0

    const reportProgress = () => {
      const currentCompleted = cachedCount + completedFetches
      const fraction = totalPairs > 0 ? currentCompleted / totalPairs : 1
      const percent = Math.round(
        phaseConfig.basePercent + fraction * (phaseConfig.maxPercent - phaseConfig.basePercent),
      )

      onProgress?.({
        phase: phaseConfig.phase,
        completedUnits: currentCompleted,
        totalUnits: totalPairs,
        percent,
        label: phaseConfig.label,
        subLabel: `${currentCompleted} of ${totalPairs} ${phaseConfig.unitNoun}`,
        currentPhaseStep: phaseConfig.step,
        totalPhaseSteps: 2,
      })
    }

    reportProgress()

    const results = await Promise.all(
      response.fetches.map(async (f) => {
        const res = await fetchWithRetry(f, signal, 3, filterTrainNumber)
        completedFetches++
        reportProgress()
        return res
      }),
    )

    response = await postRequest(
      processUrl,
      { manifest_id: response.manifest_id, results },
      signal,
    )
  }

  if (onProgress) {
    onProgress({
      phase: 'complete',
      completedUnits: 1,
      totalUnits: 1,
      percent: 100,
      label: 'Search complete',
      subLabel: 'Displaying results',
      currentPhaseStep: 2,
      totalPhaseSteps: 2,
    })
    // Brief split-second pause so the user sees 100% & the green checkmark before unmounting
    await new Promise((resolve) => setTimeout(resolve, 300))
  }

  return response as T
}

