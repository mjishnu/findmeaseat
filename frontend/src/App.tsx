import { NavLink, Navigate, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom'
import type { SearchPrefill } from './components/SearchForm'
import { SeatFinderPanel } from './components/SeatFinderPanel'
import { TrainSearchPanel, type DeepLinkPayload } from './components/TrainSearchPanel'

// Train Search is the leftmost (landing) tab; each view has its own URL so it is
// linkable, reloadable, and back/forward-navigable.
const NAV: { to: string; label: string }[] = [
  { to: '/train-search', label: 'Train Search' },
  { to: '/seat-finder', label: 'Seat Finder' },
]

// The Seat Finder reads its prefill from the URL query, so a deep-linked (and
// thus auto-searching) finder is itself shareable and bookmarkable.
function SeatFinderRoute() {
  const [params] = useSearchParams()
  const seeded =
    params.has('train') || params.has('from') || params.has('to') || params.has('date')
  const prefill: SearchPrefill | undefined = seeded
    ? {
        trainNumber: params.get('train') ?? undefined,
        source: params.get('from') ?? undefined,
        destination: params.get('to') ?? undefined,
        date: params.get('date') ?? undefined,
      }
    : undefined
  // Key by the query string so navigating in a fresh prefill remounts the form —
  // its "auto-search once" guard lives in component state.
  return <SeatFinderPanel key={params.toString()} initialPrefill={prefill} />
}

function TrainSearchRoute() {
  const navigate = useNavigate()
  function handleDeepLink(p: DeepLinkPayload) {
    const q = new URLSearchParams({
      train: p.trainNumber,
      from: p.source,
      to: p.destination,
      date: p.date,
    })
    navigate(`/seat-finder?${q.toString()}`)
  }
  return <TrainSearchPanel onDeepLink={handleDeepLink} />
}

export default function App() {
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
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  `border-b-2 px-2 py-1 transition-colors ${
                    isActive
                      ? 'border-signal-amber text-paper-50'
                      : 'border-transparent text-paper-50/60 hover:text-paper-50'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {/* pb leaves room for the fixed footer so the last card never hides behind it */}
      <main className="mx-auto max-w-5xl px-4 pb-28 pt-10 sm:px-6 sm:pt-14">
        <Routes>
          <Route path="/" element={<Navigate to="/train-search" replace />} />
          <Route path="/train-search" element={<TrainSearchRoute />} />
          <Route path="/seat-finder" element={<SeatFinderRoute />} />
          {/* Unknown paths land on the default view rather than a blank screen. */}
          <Route path="*" element={<Navigate to="/train-search" replace />} />
        </Routes>
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
