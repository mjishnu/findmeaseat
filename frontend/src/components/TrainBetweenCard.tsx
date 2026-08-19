import { QUOTAS, type BookingQuota, type ClassAvailability, type TrainBetween } from '../api'
import { StatusBadge } from './StatusBadge'

const WEEKDAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']

function formatDuration(min: number): string {
  if (min < 0) return ''
  return `${Math.floor(min / 60)}h ${String(min % 60).padStart(2, '0')}m`
}

function RunningDays({ days }: { days: string }) {
  return (
    <div className="flex gap-1" aria-label={`Runs on ${days}`}>
      {WEEKDAYS.map((d, i) => {
        const runs = days[i] === '1'
        return (
          <span
            key={i}
            className={`grid size-5 place-items-center rounded-sm font-ticket text-[10px] font-bold ${
              runs ? 'bg-signal-green/20 text-signal-green-deep' : 'bg-rail-200/50 text-rail-700/40'
            }`}
          >
            {d}
          </span>
        )
      })}
    </div>
  )
}

function ClassChip({ cls }: { cls: ClassAvailability }) {
  return (
    <div className="min-w-[92px] rounded-lg border border-rail-200 bg-white px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <span className="font-ticket text-sm font-bold tracking-wide text-rail-950">
          {cls.travel_class}
        </span>
        <span className="font-ticket text-xs text-rail-700">
          {cls.fare > 0 ? `₹${cls.fare}` : '—'}
        </span>
      </div>
      <div className="mt-1.5">
        <StatusBadge availability={cls.availability} />
      </div>
    </div>
  )
}

function emptyHint(quota: BookingQuota, allowed: string[]): string {
  if (!allowed.includes(quota)) {
    const label = QUOTAS.find((q) => q.value === quota)?.label ?? quota
    return `${label} quota is not offered on this train.`
  }
  if (quota === 'TQ') return 'Tatkal availability opens ~1 day before travel.'
  return 'No availability data for this train.'
}

interface TrainBetweenCardProps {
  train: TrainBetween
  quota: BookingQuota
  classes: ClassAvailability[]
  onFindSeat: (train: TrainBetween) => void
}

export function TrainBetweenCard({ train, quota, classes, onFindSeat }: TrainBetweenCardProps) {
  return (
    <article className="flex h-full flex-col overflow-hidden rounded-xl border border-rail-200 bg-paper-50 shadow-sm transition-shadow hover:shadow-md">
      {/* Stub header: number + name, with punched-hole perforation */}
      <div className="relative border-b-2 border-dashed border-rail-200 px-5 pb-4 pt-5">
        <span
          aria-hidden
          className="absolute -bottom-3 -left-3 size-6 rounded-full border border-rail-200 bg-paper-100"
        />
        <span
          aria-hidden
          className="absolute -bottom-3 -right-3 size-6 rounded-full border border-rail-200 bg-paper-100"
        />
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-ticket text-lg font-semibold tracking-wide text-rail-950">
              {train.train_number}
            </p>
            <h3 className="mt-0.5 font-display text-base font-semibold capitalize leading-tight text-rail-900">
              {train.train_name.toLowerCase()}
            </h3>
          </div>
          {train.has_pantry && (
            <span className="shrink-0 rounded-sm bg-rail-200/60 px-2 py-0.5 font-ticket text-[10px] uppercase tracking-[0.15em] text-rail-700">
              Pantry
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-1 flex-col space-y-4 px-5 pb-5 pt-4">
        {/* Timeline: depart → duration → arrive */}
        <div className="flex items-center gap-3">
          <div>
            <p className="font-ticket text-2xl font-semibold tracking-tight text-rail-950">
              {train.departure_time}
            </p>
            <p className="font-ticket text-[11px] tracking-wide text-rail-700">{train.from_code}</p>
          </div>
          <div className="flex flex-1 flex-col items-center px-1">
            <span className="font-ticket text-[11px] text-rail-700">
              {formatDuration(train.duration_min)}
            </span>
            <span aria-hidden className="my-0.5 h-px w-full bg-gradient-to-r from-transparent via-rail-200 to-transparent" />
            <span aria-hidden className="text-rail-500">→</span>
          </div>
          <div className="text-right">
            <p className="font-ticket text-2xl font-semibold tracking-tight text-rail-950">
              {train.arrival_time}
            </p>
            <p className="font-ticket text-[11px] tracking-wide text-rail-700">{train.to_code}</p>
          </div>
        </div>

        <RunningDays days={train.running_days} />

        {/* flex-1 lets this slot absorb the card's slack so the action row below
            sits at the bottom, keeping side-by-side cards' buttons aligned.
            content-start keeps wrapped chip rows packed at the top. */}
        {classes.length > 0 ? (
          <div className="flex flex-1 flex-wrap content-start gap-2">
            {classes.map((c) => (
              <ClassChip key={c.travel_class} cls={c} />
            ))}
          </div>
        ) : (
          <p className="rounded-md border border-dashed border-rail-200 px-3 py-2 text-xs italic text-rail-700">
            {emptyHint(quota, train.allowed_quotas)}
          </p>
        )}

        <div className="flex items-center justify-between border-t border-rail-200/70 pt-3">
          <span className="font-ticket text-[11px] uppercase tracking-[0.15em] text-rail-700">
            {train.from_name} → {train.to_name}
          </span>
          <button
            type="button"
            onClick={() => onFindSeat(train)}
            className="group inline-flex items-center gap-1.5 rounded-md border border-signal-amber/60 bg-signal-amber/15 px-3 py-1.5 font-ticket text-xs font-semibold uppercase tracking-[0.12em] text-signal-amber-deep transition-colors hover:bg-signal-amber/25 focus:outline-none focus:ring-2 focus:ring-signal-amber/40"
          >
            Find me a seat
            <span aria-hidden className="transition-transform group-hover:translate-x-0.5">
              →
            </span>
          </button>
        </div>
      </div>
    </article>
  )
}
