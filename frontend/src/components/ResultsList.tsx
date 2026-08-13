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
          {leg.source} ➝ {leg.destination} · {leg.distance_km} km
          {leg.fare > 0 ? ` · ₹${leg.fare}` : ''}
          <span className="text-paper-50/60"> · {data.travel_class}</span>
        </p>
        <div className="flex items-center gap-3">
          {leg.availability && <StatusBadge availability={leg.availability} tone="dark" />}
          <p className="font-ticket text-[11px] uppercase tracking-[0.18em] text-paper-50/60">
            {data.pairs_evaluated} combos checked
            {data.pairs_skipped > 0 && ` · ${data.pairs_skipped} unavailable`}
          </p>
        </div>
      </div>

      {data.partial && (
        <p className="mt-2 rounded-md bg-signal-amber/10 px-4 py-2 text-xs text-signal-amber-deep">
          Partial coverage enabled — showing options covering ≥{' '}
          {Math.round(data.min_coverage_pct * 100)}% of your journey. Higher coverage results are
          prioritised.
        </p>
      )}

      {recommendations.length === 0 ? (
        <p className="mt-8 rounded-lg border border-dashed border-rail-200 p-8 text-center text-sm text-rail-700">
          {data.quota === 'TQ'
            ? 'No bookable options in Tatkal for this date — Tatkal opens ~1 day before travel. Switch to General quota or pick a nearer date.'
            : 'No bookable combination right now — every covering pair came back REGRET or unparseable. Try another date.'}
        </p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-2">
          {recommendations.map((rec) => (
            <div
              key={`${rec.book_from}-${rec.book_to}`}
              className={`flex flex-col ${rec.rank === 1 ? 'md:col-span-2' : ''}`}
            >
              <RecommendationCard
                rec={rec}
                quota={data.quota}
                highlight={rec.rank === 1}
                partial={data.partial}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
