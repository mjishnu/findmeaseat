import { useState } from 'react'
import type { SearchPrefill } from './components/SearchForm'
import { SeatFinderPanel } from './components/SeatFinderPanel'
import { TrainSearchPanel, type DeepLinkPayload } from './components/TrainSearchPanel'

type View = 'finder' | 'search'

const NAV: { value: View; label: string }[] = [
  { value: 'finder', label: 'Seat Finder' },
  { value: 'search', label: 'Train Search' },
]

export default function App() {
  // Train Search (the station-driven tab) is the landing view.
  const [view, setView] = useState<View>('search')
  const [prefill, setPrefill] = useState<SearchPrefill | undefined>(undefined)

  function navTo(next: View) {
    setPrefill(undefined) // a manual tab switch starts the seat-finder clean
    setView(next)
  }

  function handleDeepLink(payload: DeepLinkPayload) {
    setPrefill({
      trainNumber: payload.trainNumber,
      source: payload.source,
      destination: payload.destination,
      date: payload.date,
    })
    setView('finder')
  }

  return (
    <div className="min-h-dvh bg-paper-100 font-body text-rail-950">
      <header className="border-t-4 border-signal-amber bg-rail-950 text-paper-50">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-4 sm:px-6">
          <p className="font-display text-2xl font-bold tracking-tight">
            FindMeASeat<span className="text-signal-amber">.</span>
          </p>
          <nav
            aria-label="Tools"
            className="flex items-center gap-1 font-ticket text-[11px] uppercase tracking-[0.2em]"
          >
            {NAV.map((n) => (
              <button
                key={n.value}
                type="button"
                onClick={() => navTo(n.value)}
                aria-current={view === n.value ? 'page' : undefined}
                className={`border-b-2 px-2 py-1 transition-colors ${
                  view === n.value
                    ? 'border-signal-amber text-paper-50'
                    : 'border-transparent text-paper-50/60 hover:text-paper-50'
                }`}
              >
                {n.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* pb leaves room for the fixed footer so the last card never hides behind it */}
      <main className="mx-auto max-w-5xl px-4 pb-28 pt-10 sm:px-6 sm:pt-14">
        {view === 'finder' ? (
          <SeatFinderPanel initialPrefill={prefill} />
        ) : (
          <TrainSearchPanel onDeepLink={handleDeepLink} />
        )}
      </main>

      {/* Fixed to the viewport bottom so the disclaimer is always visible; cards
          scroll underneath it. z-10 sits above content but below the autocomplete
          dropdown (z-20). bg-paper-100 keeps it opaque over scrolling content. */}
      <footer className="fixed inset-x-0 bottom-0 z-10 border-t border-rail-200 bg-paper-100 py-4 shadow-[0_-2px_8px_rgba(20,30,50,0.06)]">
        <p className="mx-auto max-w-5xl px-4 text-xs text-rail-700 sm:px-6">
          Probabilities are heuristics based on public waitlist-clearance patterns, not guarantees.
          Live data via erail.in &amp; confirmtkt (unofficial sources).
        </p>
      </footer>
    </div>
  )
}
