import { QUOTAS, type TrainBetween, type TrainsBetweenResponse } from '../api/client'
import type { BookingQuota } from '../api/client'
import { TrainBetweenCard } from './TrainBetweenCard'

interface TrainSearchResultsProps {
  data: TrainsBetweenResponse
  quota: BookingQuota
  onFindSeat: (train: TrainBetween) => void
}

function prettyDate(ymd: string): string {
  const [y, m, d] = ymd.split('-').map(Number)
  if (!y || !m || !d) return ymd
  // Construct a local date (no UTC shift) just for display.
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
}

export function TrainSearchResults({ data, quota, onFindSeat }: TrainSearchResultsProps) {
  const { source, destination, journey_date, trains } = data

  return (
    <section className="mt-10" aria-label="Trains between stations">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-rail-950 px-4 py-3 text-paper-50">
        <p className="font-ticket text-sm">
          <span className="text-paper-50/60">ROUTE · </span>
          {source} ➝ {destination}
          <span className="text-paper-50/60"> · {prettyDate(journey_date)}</span>
        </p>
        <p className="font-ticket text-[11px] uppercase tracking-[0.18em] text-paper-50/60">
          {trains.length} {trains.length === 1 ? 'train' : 'trains'} ·{' '}
          {QUOTAS.find((q) => q.value === quota)?.label ?? quota}
        </p>
      </div>

      {trains.length === 0 ? (
        <p className="mt-8 rounded-lg border border-dashed border-rail-200 p-8 text-center text-sm text-rail-700">
          No direct trains found between {source} and {destination} on this date. Try a
          nearby station or another day.
        </p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-2">
          {trains.map((t) => (
            <TrainBetweenCard
              key={`${t.train_number}-${t.from_code}-${t.departure_time}`}
              train={t}
              quota={quota}
              onFindSeat={onFindSeat}
            />
          ))}
        </div>
      )}
    </section>
  )
}
