import { useRef, useState } from 'react'
import {
  ApiError,
  searchTrainsBetween,
  type BookingQuota,
  type TrainBetween,
  type TrainsBetweenResponse,
} from '../api/client'
import { ErrorBanner } from './ErrorBanner'
import { SkeletonResults } from './SkeletonResults'
import { TrainSearchForm } from './TrainSearchForm'
import { TrainSearchResults } from './TrainSearchResults'

export interface DeepLinkPayload {
  trainNumber: string
  source: string
  destination: string
  date: string
}

type State =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: TrainsBetweenResponse }

interface TrainSearchPanelProps {
  onDeepLink: (payload: DeepLinkPayload) => void
}

export function TrainSearchPanel({ onDeepLink }: TrainSearchPanelProps) {
  const [state, setState] = useState<State>({ status: 'idle' })
  const [quota, setQuota] = useState<BookingQuota>('GN')
  const abortRef = useRef<AbortController | null>(null)

  async function handleSearch(q: { source: string; destination: string; date: string }) {
    abortRef.current?.abort() // resubmits cancel the stale request
    const controller = new AbortController()
    abortRef.current = controller
    setState({ status: 'loading' })
    try {
      const data = await searchTrainsBetween(q.source, q.destination, q.date, controller.signal)
      setState({ status: 'success', data })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const message =
        err instanceof ApiError
          ? err.message
          : 'Could not reach the server — is the backend running?'
      setState({ status: 'error', message })
    }
  }

  function handleFindSeat(train: TrainBetween) {
    if (state.status !== 'success') return
    // Carry THIS train's own boarding/alighting stations (what the card shows),
    // not the user's searched From/To. With confirmtkt's enableNearby, a train
    // may serve a nearby station — e.g. a NDLS→MMCT search surfaces Punjab Mail
    // running NDLS→CSMT. The seat-finder's selects are populated from this
    // train's route, so the searched code (MMCT) wouldn't be an option and the
    // dropdown would render blank; the train's own codes always are on its route.
    onDeepLink({
      trainNumber: train.train_number,
      source: train.from_code,
      destination: train.to_code,
      date: state.data.journey_date,
    })
  }

  return (
    <>
      <section className="max-w-2xl">
        <h1 className="font-display text-4xl font-black leading-[1.05] sm:text-5xl lg:text-6xl">
          Which train? <span className="italic text-rail-700">Find them all.</span>
        </h1>
        <p className="mt-4 text-base leading-relaxed text-rail-700 sm:text-lg">
          Search every train running your route, with live fares and seat availability per class
          in both General and Tatkal quotas — then jump straight to the berth finder.
        </p>
      </section>

      <TrainSearchForm
        onSearch={handleSearch}
        searching={state.status === 'loading'}
        quota={quota}
        onQuotaChange={setQuota}
      />

      <p aria-live="polite" className="sr-only">
        {state.status === 'loading'
          ? 'Searching trains…'
          : state.status === 'success'
            ? `${state.data.trains.length} trains found`
            : ''}
      </p>

      {state.status === 'loading' && <SkeletonResults />}
      {state.status === 'error' && <ErrorBanner message={state.message} />}
      {state.status === 'success' && (
        <TrainSearchResults data={state.data} quota={quota} onFindSeat={handleFindSeat} />
      )}
    </>
  )
}
