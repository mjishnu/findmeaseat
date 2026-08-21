import {
  RECOMMENDATION_NOTE_CODE,
  type BookingQuota,
  type Recommendation,
  type RecommendationNoteCode,
} from '../api'
import { ProbabilityMeter } from './ProbabilityMeter'
import { StatusBadge } from './StatusBadge'

interface RecommendationCardProps {
  rec: Recommendation
  quota: BookingQuota
  highlight?: boolean
  partial?: boolean
}

function renderNote(note: RecommendationNoteCode, rec: Recommendation): string {
  switch (note) {
    case RECOMMENDATION_NOTE_CODE.QUOTA_TATKAL:
      return 'Book under the Tatkal quota on IRCTC — it opens ~1 day before travel and carries a higher fare than General.'
    case RECOMMENDATION_NOTE_CODE.QUOTA_LADIES:
      return 'Book under the Ladies quota on IRCTC — reserved for women travellers (and a child under 12 travelling with them).'
    case RECOMMENDATION_NOTE_CODE.QUOTA_SENIOR:
      return 'Book under the Senior Citizen quota on IRCTC — for eligible senior citizens; carry valid age proof.'
    case RECOMMENDATION_NOTE_CODE.BOARDING_CHANGE:
      return `Change the boarding point to ${rec.board_at} on IRCTC immediately after booking — without it the TTE can mark you absent and release the berth.`
    case RECOMMENDATION_NOTE_CODE.EXTRA_FARE:
      return `Costs ₹${rec.extra_fare} more than the direct ${rec.board_at}→${rec.alight_at} fare; the unused distance is not refundable.`
    case RECOMMENDATION_NOTE_CODE.ALIGHT_CHANGE:
      return `Get off at ${rec.alight_at}; the ticket runs on to ${rec.book_to} but the difference is not refunded.`
    case RECOMMENDATION_NOTE_CODE.MISSING_PREDICTION:
      return 'confirmtkt has no confirmation estimate for this leg; ranked last.'
    case RECOMMENDATION_NOTE_CODE.PARTIAL_COVERAGE:
      return `Covers ${Math.round(rec.coverage_pct * 100)}% of your journey — you travel ${rec.board_at}→${rec.alight_at} only. Arrange your own travel for the rest.`
    default:
      return note
  }
}

function buildAction(rec: Recommendation, quota: string): string {
  let action = `Book ${rec.book_from} to ${rec.book_to}, board at ${rec.board_at}`
  if (rec.book_to !== rec.alight_at) {
    action += `, alight at ${rec.alight_at}`
  }
  if (quota === 'TQ') {
    action += ' in Tatkal quota'
  } else if (quota === 'LD') {
    action += ' in Ladies quota'
  } else if (quota === 'SS') {
    action += ' in Senior Citizen quota'
  }
  action += `. Status: ${rec.availability.raw}`
  return action
}

export function RecommendationCard({
  rec,
  quota,
  highlight = false,
  partial = false,
}: RecommendationCardProps) {
  const showCoverage = partial || rec.coverage_pct < 1.0

  return (
    <article
      className={`flex h-full flex-col justify-between overflow-hidden rounded-xl border bg-paper-50 shadow-sm transition-shadow hover:shadow-md ${highlight ? 'border-signal-amber ring-1 ring-signal-amber/40' : 'border-rail-200'
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
            className={`rounded-sm px-2 py-0.5 font-ticket text-xs font-bold uppercase tracking-widest ${highlight ? 'bg-signal-amber text-rail-950' : 'bg-rail-200/60 text-rail-700'
              }`}
          >
            {highlight ? '#1 · Best bet' : `#${rec.rank}`}
          </span>
          <StatusBadge availability={rec.availability} />
        </div>

        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="font-ticket text-3xl font-semibold tracking-tight text-rail-950">
            {rec.book_from}
            <span className="mx-2 text-rail-500">➝</span>
            {rec.book_to}
          </p>
          {showCoverage && (
            <span
              className={`shrink-0 rounded px-2 py-1 font-ticket text-xs font-semibold uppercase tracking-wider ${rec.coverage_pct >= 1.0
                  ? 'border border-signal-green/40 bg-signal-green/15 text-signal-green-deep'
                  : 'border border-signal-amber/40 bg-signal-amber/15 text-signal-amber-deep'
                }`}
            >
              {Math.round(rec.coverage_pct * 100)}% coverage
            </span>
          )}
        </div>
        <p className="mt-1 text-xs text-rail-700">
          board at <span className="font-semibold">{rec.board_at}</span> · alight at{' '}
          <span className="font-semibold">{rec.alight_at}</span>
        </p>
      </div>

      <div className="flex flex-1 flex-col justify-start space-y-4 px-5 pb-5 pt-4">
        <p className="text-sm leading-relaxed text-rail-950">{buildAction(rec, quota)}</p>

        <div>
          <p className="mb-1 font-ticket text-xs uppercase tracking-widest text-rail-700">
            Confirmation chance
          </p>
          <ProbabilityMeter probability={rec.probability} />
        </div>

        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div>
            <dt className="sr-only">Fare</dt>
            <dd className="font-ticket font-semibold text-rail-950">
              {rec.fare > 0 ? `₹${rec.fare}` : 'Fare n/a'}
            </dd>
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
            {rec.notes.map((note, index) => (
              <li key={`${note}-${index}`} className="flex gap-2 text-xs leading-relaxed text-rail-700">
                <span aria-hidden className="text-signal-amber-deep">
                  ⚠
                </span>
                {renderNote(note, rec)}
              </li>
            ))}
          </ul>
        )}
        <div className="flex-1" />
      </div>
    </article>
  )
}
