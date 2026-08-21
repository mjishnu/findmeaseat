import { useRef, useState } from 'react'
import {
  ApiError,
  searchTrainsBetween,
  type BookingQuota,
  type ClassAvailability,
  type TrainBetween,
  type TrainsBetweenResponse,
  type TravelClass,
} from '../api'
import { ErrorBanner } from './ErrorBanner'
import { SkeletonResults } from './SkeletonResults'
import { TrainSearchForm } from './TrainSearchForm'
import { TrainSearchResults } from './TrainSearchResults'

const rowKey = (t: { train_number: string; from_code: string; departure_time: string }) =>
  `${t.train_number}-${t.from_code}-${t.departure_time}`

export interface DeepLinkPayload {
  trainNumber: string
  source: string
  sourceName?: string
  destination: string
  destinationName?: string
  date: string
  travelClass?: TravelClass
  quota?: BookingQuota
}

export interface TrainSearchPrefill {
  source?: string
  sourceName?: string
  destination?: string
  destinationName?: string
  date?: string
  quota?: BookingQuota
}

type State =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: TrainsBetweenResponse }

interface TrainSearchPanelProps {
  onDeepLink: (payload: DeepLinkPayload) => void
  initialPrefill?: TrainSearchPrefill
}

export function TrainSearchPanel({ onDeepLink, initialPrefill }: TrainSearchPanelProps) {
  const [state, setState] = useState<State>({ status: 'idle' })
  const [quota, setQuota] = useState<BookingQuota>(initialPrefill?.quota ?? 'GN')
  // Lazily-fetched LD/SS availability, keyed by quota then by composite row key.
  const [quotaCache, setQuotaCache] = useState<Partial<Record<BookingQuota, Map<string, ClassAvailability[]>>>>({})
  const [quotaLoading, setQuotaLoading] = useState(false)
  const quotaAbortRef = useRef<AbortController | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  async function handleSearch(q: {
    source: string
    sourceName?: string
    destination: string
    destinationName?: string
    date: string
  }) {
    abortRef.current?.abort() // resubmits cancel the stale request
    const controller = new AbortController()
    abortRef.current = controller
    setState({ status: 'loading' })
    setQuotaCache({}) // a new route/date invalidates lazily-fetched quotas

    // Keep browser URL in sync so searches are shareable and bookmarkable
    const url = new URL(window.location.href)
    url.searchParams.set('from', q.source)
    if (q.sourceName) {
      url.searchParams.set('fromName', q.sourceName)
    } else {
      url.searchParams.delete('fromName')
    }
    url.searchParams.set('to', q.destination)
    if (q.destinationName) {
      url.searchParams.set('toName', q.destinationName)
    } else {
      url.searchParams.delete('toName')
    }
    url.searchParams.set('date', q.date)
    if (quota && quota !== 'GN') {
      url.searchParams.set('quota', quota)
    } else {
      url.searchParams.delete('quota')
    }
    window.history.replaceState(null, '', url.pathname + url.search)

    try {
      const data = await searchTrainsBetween(q.source, q.destination, q.date, quota, controller.signal)
      setState({ status: 'success', data })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const message =
        err instanceof ApiError
          ? err.message
          : 'Could not reach the server'
      setState({ status: 'error', message })
    }
  }

  function handleFindSeat(train: TrainBetween, travelClass?: TravelClass) {
    if (state.status !== 'success') return
    onDeepLink({
      trainNumber: train.train_number,
      source: train.from_code,
      sourceName: train.from_name,
      destination: train.to_code,
      destinationName: train.to_name,
      date: state.data.journey_date,
      travelClass,
      quota,
    })
  }

  function handleQuotaChange(next: BookingQuota) {
    setQuota(next)
    if (state.status !== 'success') return

    // Update quota in URL
    const url = new URL(window.location.href)
    if (next === 'GN') {
      url.searchParams.delete('quota')
    } else {
      url.searchParams.set('quota', next)
    }
    window.history.replaceState(null, '', url.pathname + url.search)

    if (next === 'GN' || next === 'TQ') return // bundled in the base response
    if (quotaCache[next]) return // already fetched
    quotaAbortRef.current?.abort()
    const controller = new AbortController()
    quotaAbortRef.current = controller
    setQuotaLoading(true)
    searchTrainsBetween(state.data.source, state.data.destination, state.data.journey_date, next, controller.signal)
      .then((res) => {
        const byRow = new Map<string, ClassAvailability[]>()
        for (const t of res.trains) byRow.set(rowKey(t), t.classes)
        setQuotaCache((prev) => ({ ...prev, [next]: byRow }))
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        // A failed quota fetch leaves cards in their empty state; surface nothing fatal.
      })
      .finally(() => {
        if (quotaAbortRef.current === controller) setQuotaLoading(false)
      })
  }

  return (
    <>
      <section className="max-w-2xl">
        <h1 className="font-display text-4xl font-black leading-tight sm:text-5xl lg:text-6xl">
          Which train? <span className="italic text-rail-700">Find them all.</span>
        </h1>
        <p className="mt-4 text-base leading-relaxed text-rail-700 sm:text-lg">
          Search every train running your route, with live fares and seat availability per class
          in all quotas — then jump straight to the seat finder.
        </p>
      </section>

      <TrainSearchForm
        onSearch={handleSearch}
        searching={state.status === 'loading'}
        quota={quota}
        onQuotaChange={handleQuotaChange}
        initial={initialPrefill}
      />

      <p aria-live="polite" className="sr-only">
        {state.status === 'loading'
          ? 'Searching trains…'
          : state.status === 'success'
            ? `${state.data.trains.length} trains found`
            : ''}
      </p>

      {state.status === 'loading' && <SkeletonResults />}
      {state.status === 'error' && <ErrorBanner>{state.message}</ErrorBanner>}
      {state.status === 'success' && (
        <TrainSearchResults
          data={state.data}
          quota={quota}
          quotaLoading={quotaLoading}
          onFindSeat={handleFindSeat}
          classesFor={(t) =>
            quota === 'GN'
              ? t.general
              : quota === 'TQ'
                ? t.tatkal
                : quotaCache[quota]?.get(rowKey(t)) ?? []
          }
        />
      )}
    </>
  )
}
