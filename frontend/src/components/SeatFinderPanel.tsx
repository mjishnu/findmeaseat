import { useRef, useState } from 'react'
import {
  ApiError,
  DEFAULT_QUOTA,
  DEFAULT_TRAVEL_CLASS,
  findOptimalRoute,
  type BookingQuota,
  type RecommendationResponse,
  type SearchQuery,
  type TravelClass,
} from '../api'
import { ErrorBanner } from './ErrorBanner'
import { ResultsList } from './ResultsList'
import { SearchForm, type SearchPrefill } from './SearchForm'
import { SkeletonResults } from './SkeletonResults'
import { SwitchSuggestionBanner } from './SwitchSuggestionBanner'

type ResultsState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: RecommendationResponse }

interface SeatFinderPanelProps {
  // Seeded from a Train Search deep-link; undefined for a normal visit.
  initialPrefill?: SearchPrefill
}

export function SeatFinderPanel({ initialPrefill }: SeatFinderPanelProps) {
  const [results, setResults] = useState<ResultsState>({ status: 'idle' })
  const [lastQuery, setLastQuery] = useState<SearchQuery | null>(null)
  const [travelClass, setTravelClass] = useState<TravelClass>(initialPrefill?.travelClass ?? DEFAULT_TRAVEL_CLASS)
  const [quota, setQuota] = useState<BookingQuota>(initialPrefill?.quota ?? DEFAULT_QUOTA)
  const [partial, setPartial] = useState(false)
  const [minCoveragePct, setMinCoveragePct] = useState(0.75)
  const [requireConnect, setRequireConnect] = useState(true)
  const abortRef = useRef<AbortController | null>(null)

  async function handleSearch(query: SearchQuery) {
    abortRef.current?.abort() // resubmits cancel the stale request
    const controller = new AbortController()
    abortRef.current = controller
    setLastQuery(query) // remembered so the class banner can re-search in another class
    setResults({ status: 'loading' })

    // Keep browser URL in sync so searches are shareable and bookmarkable
    const url = new URL(window.location.href)
    url.searchParams.set('train', query.trainNumber)
    if (url.searchParams.get('from') !== query.source) {
      url.searchParams.delete('fromName')
    }
    url.searchParams.set('from', query.source)
    if (url.searchParams.get('to') !== query.destination) {
      url.searchParams.delete('toName')
    }
    url.searchParams.set('to', query.destination)
    url.searchParams.set('date', query.date)
    if (query.travelClass && query.travelClass !== DEFAULT_TRAVEL_CLASS) {
      url.searchParams.set('class', query.travelClass)
    } else {
      url.searchParams.delete('class')
    }
    if (query.quota && query.quota !== DEFAULT_QUOTA) {
      url.searchParams.set('quota', query.quota)
    } else {
      url.searchParams.delete('quota')
    }
    window.history.replaceState(null, '', url.pathname + url.search)

    try {
      const data = await findOptimalRoute(query, controller.signal)
      setResults({ status: 'success', data })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const message =
        err instanceof ApiError
          ? err.status === 404
            ? 'Search expired — please retry'
            : err.message
          : 'Could not reach the server'
      setResults({ status: 'error', message })
    }
  }

  return (
    <>
      <section className="max-w-2xl">
        <h1 className="font-display text-4xl font-black leading-tight sm:text-5xl lg:text-6xl">
          Waitlisted? <span className="italic text-rail-700">Outsmart the quota.</span>
        </h1>
        <p className="mt-4 text-base leading-relaxed text-rail-700 sm:text-lg">
          The same train hides different quotas on different station pairs. We check every booking
          combination that covers your journey and rank the ones most likely to confirm.
        </p>
      </section>

      <SearchForm
        onSearch={handleSearch}
        searching={results.status === 'loading'}
        travelClass={travelClass}
        onTravelClassChange={setTravelClass}
        quota={quota}
        onQuotaChange={setQuota}
        partial={partial}
        onPartialChange={setPartial}
        minCoveragePct={minCoveragePct}
        onMinCoveragePctChange={setMinCoveragePct}
        requireConnect={requireConnect}
        onRequireConnectChange={setRequireConnect}
        initial={initialPrefill}
      />

      {/* The visual skeleton is aria-hidden; this narrates search progress */}
      <p aria-live="polite" className="sr-only">
        {results.status === 'loading'
          ? 'Checking combinations…'
          : results.status === 'success'
            ? `${results.data.recommendations.length} recommendations found`
            : ''}
      </p>

      {results.status === 'loading' && <SkeletonResults />}
      {results.status === 'error' && <ErrorBanner>{results.message}</ErrorBanner>}
      {results.status === 'success' && (
        <>
          {lastQuery && (
            <SwitchSuggestionBanner
              alternatives={results.data.alternatives}
              searchedClass={results.data.travel_class}
              searchedQuota={results.data.quota}
              onSwitch={(nextClass, nextQuota) => {
                setTravelClass(nextClass) // sync the form's Class selector
                setQuota(nextQuota) // sync the form's Quota toggle
                handleSearch({ ...lastQuery, travelClass: nextClass, quota: nextQuota })
              }}
            />
          )}
          <ResultsList data={results.data} />
        </>
      )}
    </>
  )
}
