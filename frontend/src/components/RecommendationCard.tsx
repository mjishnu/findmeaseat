import type { Recommendation } from '../api/client'
import { ProbabilityMeter } from './ProbabilityMeter'
import { StatusBadge } from './StatusBadge'

interface RecommendationCardProps {
  rec: Recommendation
  highlight?: boolean
}

export function RecommendationCard({ rec, highlight = false }: RecommendationCardProps) {
  return (
    <article
      className={`overflow-hidden rounded-xl border bg-paper-50 shadow-sm transition-shadow hover:shadow-md ${
        highlight ? 'border-signal-amber ring-1 ring-signal-amber/40' : 'border-rail-200'
      }`}
    >
      {/* Stub: perforated edge with punched holes */}
      <div className="relative border-b-2 border-dashed border-rail-200 px-5 pb-4 pt-5">
        <span
          aria-hidden
          className="absolute -bottom-3 -left-3 size-6 rounded-full border border-rail-200 bg-paper-100"
        />
        <span
          aria-hidden
          className="absolute -bottom-3 -right-3 size-6 rounded-full border border-rail-200 bg-paper-100"
        />

        <div className="flex items-center justify-between gap-2">
          <span
            className={`rounded-sm px-2 py-0.5 font-ticket text-[11px] font-bold uppercase tracking-[0.2em] ${
              highlight ? 'bg-signal-amber text-rail-950' : 'bg-rail-200/60 text-rail-700'
            }`}
          >
            {highlight ? '#1 · Best bet' : `#${rec.rank}`}
          </span>
          <StatusBadge availability={rec.availability} />
        </div>

        <p className="mt-3 font-ticket text-3xl font-semibold tracking-tight text-rail-950">
          {rec.book_from}
          <span className="mx-2 text-rail-500">➝</span>
          {rec.book_to}
        </p>
        <p className="mt-1 text-xs text-rail-700">
          board at <span className="font-semibold">{rec.board_at}</span> · alight at{' '}
          <span className="font-semibold">{rec.alight_at}</span>
        </p>
      </div>

      <div className="space-y-4 px-5 pb-5 pt-4">
        <p className="text-sm leading-relaxed text-rail-950">{rec.action}</p>

        <div>
          <p className="mb-1 font-ticket text-[11px] uppercase tracking-[0.18em] text-rail-700">
            Confirmation chance
          </p>
          <ProbabilityMeter probability={rec.probability} />
        </div>

        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div>
            <dt className="sr-only">Fare</dt>
            <dd className="font-ticket font-semibold text-rail-950">₹{rec.fare}</dd>
          </div>
          {rec.extra_fare > 0 && (
            <div>
              <dt className="sr-only">Extra fare</dt>
              <dd className="text-signal-amber-deep">+₹{rec.extra_fare} vs direct</dd>
            </div>
          )}
          {rec.extra_km > 0 && (
            <div>
              <dt className="sr-only">Extra distance</dt>
              <dd className="text-rail-700">+{rec.extra_km} km booked</dd>
            </div>
          )}
        </dl>

        {rec.notes.length > 0 && (
          <ul className="space-y-1.5 border-t border-rail-200/70 pt-3">
            {rec.notes.map((note) => (
              <li key={note} className="flex gap-2 text-xs leading-relaxed text-rail-700">
                <span aria-hidden className="text-signal-amber-deep">
                  ⚠
                </span>
                {note}
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  )
}
