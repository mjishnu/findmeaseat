import {
  Navigate,
  Route,
  Routes,
  createSearchParams,
  useNavigate,
  useSearchParams,
} from 'react-router-dom'
import { QUOTAS, TRAVEL_CLASSES, type BookingQuota, type TravelClass } from './api'
import type { SearchPrefill } from './components/SearchForm'
import { SeatFinderPanel } from './components/SeatFinderPanel'
import {
  TrainSearchPanel,
  type DeepLinkPayload,
  type TrainSearchPrefill,
} from './components/TrainSearchPanel'
import { Navbar } from './components/Navbar'
import { Footer } from './components/Footer'

function parsePrefill(params: URLSearchParams): SearchPrefill | undefined {
  const trainNumber = params.get('train') ?? undefined
  const source = params.get('from') ?? undefined
  const sourceName = params.get('fromName') ?? undefined
  const destination = params.get('to') ?? undefined
  const destinationName = params.get('toName') ?? undefined
  const date = params.get('date') ?? undefined
  const classParam = params.get('class') ?? undefined
  const travelClass = TRAVEL_CLASSES.some((c) => c.value === classParam)
    ? (classParam as TravelClass)
    : undefined
  const quotaParam = params.get('quota') ?? undefined
  const quota = QUOTAS.some((q) => q.value === quotaParam)
    ? (quotaParam as BookingQuota)
    : undefined

  if (!trainNumber && !source && !destination && !date && !travelClass && !quota) return undefined
  return { trainNumber, source, sourceName, destination, destinationName, date, travelClass, quota }
}

function parseTrainSearchPrefill(params: URLSearchParams): TrainSearchPrefill | undefined {
  const source = params.get('from') ?? undefined
  const sourceName = params.get('fromName') ?? undefined
  const destination = params.get('to') ?? undefined
  const destinationName = params.get('toName') ?? undefined
  const date = params.get('date') ?? undefined
  const quotaParam = params.get('quota') ?? undefined
  const quota = QUOTAS.some((q) => q.value === quotaParam)
    ? (quotaParam as BookingQuota)
    : undefined

  if (!source && !destination && !date && !quota) return undefined
  return { source, sourceName, destination, destinationName, date, quota }
}

function SeatFinderRoute() {
  const [params] = useSearchParams()
  const prefill = parsePrefill(params)

  // Key by the query string so navigating in a fresh prefill remounts the form
  return <SeatFinderPanel key={params.toString()} initialPrefill={prefill} />
}

function TrainSearchRoute() {
  const [params] = useSearchParams()
  const prefill = parseTrainSearchPrefill(params)
  const navigate = useNavigate()

  function handleDeepLink(p: DeepLinkPayload) {
    const searchParams: Record<string, string> = {
      train: p.trainNumber,
      from: p.source,
      to: p.destination,
      date: p.date,
    }
    if (p.sourceName) searchParams.fromName = p.sourceName
    if (p.destinationName) searchParams.toName = p.destinationName
    if (p.travelClass) searchParams.class = p.travelClass
    if (p.quota) searchParams.quota = p.quota

    navigate({
      pathname: '/seat-finder',
      search: `?${createSearchParams(searchParams)}`,
    })
  }

  return (
    <TrainSearchPanel
      key={params.toString()}
      initialPrefill={prefill}
      onDeepLink={handleDeepLink}
    />
  )
}

export default function App() {
  return (
    <div className="flex min-h-dvh flex-col bg-paper-100 font-body text-rail-950">
      <Navbar />

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-12 pt-6 sm:px-8 sm:pt-8">
        <Routes>
          <Route path="/train-search" element={<TrainSearchRoute />} />
          <Route path="/seat-finder" element={<SeatFinderRoute />} />
          <Route path="*" element={<Navigate to="/train-search" replace />} />
        </Routes>
      </main>

      <Footer />
    </div>
  )
}
