import type { ParsedAvailability } from '../api/client'

const STATUS_STYLES: Record<ParsedAvailability['status'], string> = {
  AVAILABLE: 'border-signal-green/50 bg-signal-green/15 text-signal-green-deep',
  RAC: 'border-signal-amber/60 bg-signal-amber/20 text-signal-amber-deep',
  WAITLIST: 'border-signal-amber/60 bg-signal-amber/20 text-signal-amber-deep',
  NOT_BOOKABLE: 'border-signal-red/40 bg-signal-red/10 text-signal-red',
  UNKNOWN: 'border-rail-200 bg-rail-200/40 text-rail-700',
}

interface StatusBadgeProps {
  availability: ParsedAvailability
}

export function StatusBadge({ availability }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-1 font-ticket text-xs font-semibold tracking-wide ${STATUS_STYLES[availability.status]}`}
    >
      {availability.raw}
    </span>
  )
}
