import { useRef, useState } from 'react'
import {
  ApiError,
  findOptimalRoute,
  type RecommendationResponse,
  type SearchQuery,
} from './api/client'
import { ErrorBanner } from './components/ErrorBanner'
import { ResultsList } from './components/ResultsList'
import { SearchForm } from './components/SearchForm'
import { SkeletonResults } from './components/SkeletonResults'

type ResultsState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: RecommendationResponse }

export default function App() {
  const [results, setResults] = useState<ResultsState>({ status: 'idle' })
  const abortRef = useRef<AbortController | null>(null)

  async function handleSearch(query: SearchQuery) {
    abortRef.current?.abort() // resubmits cancel the stale request
    const controller = new AbortController()
    abortRef.current = controller
    setResults({ status: 'loading' })
    try {
      const data = await findOptimalRoute(query, controller.signal)
      setResults({ status: 'success', data })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const message =
        err instanceof ApiError
          ? err.message
          : 'Could not reach the server — is the backend running?'
      setResults({ status: 'error', message })
    }
  }

  return (
    <div className="min-h-dvh bg-paper-100 font-body text-rail-950">
      <header className="border-t-4 border-signal-amber bg-rail-950 text-paper-50">
        <div className="mx-auto flex max-w-5xl items-baseline justify-between px-4 py-4 sm:px-6">
          <p className="font-display text-2xl font-bold tracking-tight">
            GetMeASeat<span className="text-signal-amber">.</span>
          </p>
          <p className="hidden font-ticket text-[11px] uppercase tracking-[0.25em] text-paper-50/60 sm:block">
            Alternate-leg berth finder
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 pb-20 pt-10 sm:px-6 sm:pt-14">
        <section className="max-w-2xl">
          <h1 className="font-display text-4xl font-black leading-[1.05] sm:text-5xl lg:text-6xl">
            Waitlisted? <span className="italic text-rail-700">Outsmart the quota.</span>
          </h1>
          <p className="mt-4 text-base leading-relaxed text-rail-700 sm:text-lg">
            The same train hides different quotas on different station pairs. We check every
            booking combination that covers your journey and rank the ones most likely to
            confirm.
          </p>
        </section>

        <SearchForm onSearch={handleSearch} searching={results.status === 'loading'} />

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
        {results.status === 'success' && <ResultsList data={results.data} />}
      </main>

      <footer className="border-t border-rail-200 py-6">
        <p className="mx-auto max-w-5xl px-4 text-xs text-rail-700 sm:px-6">
          Probabilities are heuristics based on public waitlist-clearance patterns, not
          guarantees. Demo data — train 12345, stations A–F.
        </p>
      </footer>
    </div>
  )
}
