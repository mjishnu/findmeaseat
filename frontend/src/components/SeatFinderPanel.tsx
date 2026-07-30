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
} from '../api/client'
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
  const [travelClass, setTravelClass] = useState<TravelClass>(DEFAULT_TRAVEL_CLASS)
  const [quota, setQuota] = useState<BookingQuota>(DEFAULT_QUOTA)
  const abortRef = useRef<AbortController | null>(null)

  async function handleSearch(query: SearchQuery) {
    abortRef.current?.abort() // resubmits cancel the stale request
    const controller = new AbortController()
    abortRef.current = controller
    setLastQuery(query) // remembered so the class banner can re-search in another class
    setResults({ status: 'loading' })
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
          : 'Could not reach the server — is the backend running?'
      setResults({ status: 'error', message })
    }
  }

  return (
    <>
      <section className="max-w-2xl">
        <h1 className="font-display text-4xl font-black leading-[1.05] sm:text-5xl lg:text-6xl">
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
      {results.status === 'error' && <ErrorBanner message={results.message} />}
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
