import type { RecommendationResponse } from '../api/client'
import { RecommendationCard } from './RecommendationCard'
import { StatusBadge } from './StatusBadge'

interface ResultsListProps {
  data: RecommendationResponse
}

export function ResultsList({ data }: ResultsListProps) {
  const { user_leg: leg, recommendations } = data
  return (
    <section className="mt-10" aria-label="Recommendations">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-rail-950 px-4 py-3 text-paper-50">
        <p className="font-ticket text-sm">
          <span className="text-paper-50/60">YOUR LEG · </span>
          {leg.source} ➝ {leg.destination} · {leg.distance_km} km · ₹{leg.fare}
        </p>
        <div className="flex items-center gap-3">
          {leg.availability && <StatusBadge availability={leg.availability} />}
          <p className="font-ticket text-[11px] uppercase tracking-[0.18em] text-paper-50/60">
            {data.pairs_evaluated} combos checked
          </p>
        </div>
      </div>

      {recommendations.length === 0 ? (
        <p className="mt-8 rounded-lg border border-dashed border-rail-200 p-8 text-center text-sm text-rail-700">
          No bookable combination right now — every covering pair came back REGRET or
          unparseable. Try another date.
        </p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-2">
          {recommendations.map((rec) => (
            <div
              key={`${rec.book_from}-${rec.book_to}`}
              className={rec.rank === 1 ? 'md:col-span-2' : ''}
            >
              <RecommendationCard rec={rec} highlight={rec.rank === 1} />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
