import { useState } from 'react'
import {
  AvailabilityStatus,
  QUOTAS,
  type BookingQuota,
  type ClassAvailability,
  type TrainBetween,
  type TravelClass,
} from '../api'
import { ErrorBanner } from './ErrorBanner'
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
            className={`grid size-5 place-items-center rounded-sm font-ticket text-xs font-bold ${runs ? 'bg-signal-green/20 text-signal-green-deep' : 'bg-rail-200/50 text-rail-700/40'
              }`}
          >
            {d}
          </span>
        )
      })}
    </div>
  )
}

const STATUS_CHIP_STYLES: Record<
  AvailabilityStatus,
  {
    selected: string
    hover: string
    focusVisible: string
    dotBg: string
  }
> = {
  [AvailabilityStatus.AVAILABLE]: {
    selected: 'bg-signal-green/12 border-signal-green/30 shadow-xs ring-2 ring-signal-green/30 text-rail-950 -translate-y-0.5',
    hover: 'hover:bg-signal-green/6 hover:border-signal-green/30',
    focusVisible: 'focus-visible:ring-signal-green/60',
    dotBg: 'bg-signal-green-deep',
  },
  [AvailabilityStatus.RAC]: {
    selected: 'bg-signal-green/12 border-signal-green/30 shadow-xs ring-2 ring-signal-green/30 text-rail-950 -translate-y-0.5',
    hover: 'hover:bg-signal-green/6 hover:border-signal-green/30',
    focusVisible: 'focus-visible:ring-signal-green/60',
    dotBg: 'bg-signal-green-deep',
  },
  [AvailabilityStatus.WAITLIST]: {
    selected: 'bg-signal-amber/14 border-signal-amber/30 shadow-xs ring-2 ring-signal-amber/30 text-rail-950 -translate-y-0.5',
    hover: 'hover:bg-signal-amber/7 hover:border-signal-amber/30',
    focusVisible: 'focus-visible:ring-signal-amber/60',
    dotBg: 'bg-signal-amber-deep',
  },
  [AvailabilityStatus.NOT_BOOKABLE]: {
    selected: 'bg-signal-red/8 border-signal-red/20 shadow-xs ring-2 ring-signal-red/20 text-rail-950 -translate-y-0.5',
    hover: 'hover:bg-signal-red/5 hover:border-signal-red/20',
    focusVisible: 'focus-visible:ring-signal-red/40',
    dotBg: 'bg-signal-red-deep',
  },
  [AvailabilityStatus.UNKNOWN]: {
    selected: 'bg-rail-200/50 border-rail-300 shadow-xs ring-2 ring-rail-500/30 text-rail-950 -translate-y-0.5',
    hover: 'hover:bg-rail-200/25 hover:border-rail-300',
    focusVisible: 'focus-visible:ring-rail-500/50',
    dotBg: 'bg-rail-700',
  },
}

function ClassChip({
  cls,
  isSelected,
  onSelect,
}: {
  cls: ClassAvailability
  isSelected: boolean
  onSelect: () => void
}) {
  const status = cls.availability?.status ?? AvailabilityStatus.NOT_BOOKABLE
  const style = STATUS_CHIP_STYLES[status] ?? STATUS_CHIP_STYLES[AvailabilityStatus.UNKNOWN]

  return (
    <button
      type="button"
      role="radio"
      aria-checked={isSelected}
      onClick={onSelect}
      className={`min-w-24 rounded-lg px-3 py-2 text-left transition-all duration-150 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ${style.focusVisible} ${isSelected
        ? `${style.selected} border`
        : `bg-white border border-rail-200 text-rail-900 ${style.hover} shadow-2xs`
        }`}
      title={`Select ${cls.travel_class}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          {isSelected && (
            <span
              aria-hidden
              className={`size-2 shrink-0 rounded-full ${style.dotBg}`}
            />
          )}
          <span
            className={`font-ticket text-sm font-bold tracking-wide ${isSelected ? 'text-rail-950' : 'text-rail-900'
              }`}
          >
            {cls.travel_class}
          </span>
        </div>
        <span
          className={`font-ticket text-xs ${isSelected ? 'font-semibold text-rail-900' : 'text-rail-700'
            }`}
        >
          {cls.fare > 0 ? `₹${cls.fare}` : '—'}
        </span>
      </div>
      <div className="mt-1.5">
        <StatusBadge availability={cls.availability} />
      </div>
    </button>
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
  onFindSeat: (train: TrainBetween, travelClass?: TravelClass) => void
}

export function TrainBetweenCard({ train, quota, classes, onFindSeat }: TrainBetweenCardProps) {
  const [selectedClass, setSelectedClass] = useState<TravelClass | undefined>(() => classes[0]?.travel_class)
  const effectiveClass = (selectedClass && classes.some((c) => c.travel_class === selectedClass))
    ? selectedClass
    : classes[0]?.travel_class

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
            <span className="shrink-0 rounded-sm bg-rail-200/60 px-2 py-0.5 font-ticket text-xs uppercase tracking-widest text-rail-700">
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
            <p className="font-ticket text-xs tracking-wide text-rail-700">{train.from_code}</p>
          </div>
          <div className="flex flex-1 flex-col items-center px-1">
            <span className="font-ticket text-xs text-rail-700">
              {formatDuration(train.duration_min)}
            </span>
            <span aria-hidden className="my-0.5 h-px w-full bg-gradient-to-r from-transparent via-rail-200 to-transparent" />
            <span aria-hidden className="text-rail-500">→</span>
          </div>
          <div className="text-right">
            <p className="font-ticket text-2xl font-semibold tracking-tight text-rail-950">
              {train.arrival_time}
            </p>
            <p className="font-ticket text-xs tracking-wide text-rail-700">{train.to_code}</p>
          </div>
        </div>

        <RunningDays days={train.running_days} />

        {/* flex-1 lets this slot absorb the card's slack so the action row below
            sits at the bottom, keeping side-by-side cards' buttons aligned.
            content-start keeps wrapped chip rows packed at the top. */}
        {classes.length > 0 ? (
          <div
            role="radiogroup"
            aria-label="Select travel class"
            className="flex flex-1 flex-wrap content-start gap-2"
          >
            {classes.map((c) => (
              <ClassChip
                key={c.travel_class}
                cls={c}
                isSelected={c.travel_class === effectiveClass}
                onSelect={() => setSelectedClass(c.travel_class)}
              />
            ))}
          </div>
        ) : (
          <ErrorBanner>
            {emptyHint(quota, train.allowed_quotas)}
          </ErrorBanner>
        )}

        <div className="flex min-h-14 items-center justify-between gap-3 border-t border-rail-200/70 pt-3">
          <span className="flex-1 font-ticket text-xs uppercase tracking-widest text-rail-700">
            {train.from_name} → {train.to_name}
          </span>
          <button
            type="button"
            onClick={() => onFindSeat(train, effectiveClass)}
            className="group inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md bg-rail-900 px-4 py-2.5 font-ticket text-xs font-semibold uppercase tracking-widest text-paper-50 transition-colors hover:bg-rail-700 focus:outline-none focus:ring-2 focus:ring-rail-500 focus:ring-offset-2 focus:ring-offset-paper-50 cursor-pointer"
          >
            Find me a seat
          </button>
        </div>
      </div>
    </article>
  )
}
