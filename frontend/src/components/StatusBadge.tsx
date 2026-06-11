import type { ParsedAvailability } from '../api/client'

// -deep text tokens pass AA on the cream cards; -bright ones on rail-950.
const LIGHT_STYLES: Record<ParsedAvailability['status'], string> = {
  AVAILABLE: 'border-signal-green/50 bg-signal-green/15 text-signal-green-deep',
  RAC: 'border-signal-amber/60 bg-signal-amber/20 text-signal-amber-deep',
  WAITLIST: 'border-signal-amber/60 bg-signal-amber/20 text-signal-amber-deep',
  NOT_BOOKABLE: 'border-signal-red/40 bg-signal-red/10 text-signal-red',
  UNKNOWN: 'border-rail-200 bg-rail-200/40 text-rail-700',
}

const DARK_STYLES: Record<ParsedAvailability['status'], string> = {
  AVAILABLE: 'border-signal-green/40 bg-signal-green/25 text-signal-green-bright',
  RAC: 'border-signal-amber/50 bg-signal-amber/25 text-signal-amber-bright',
  WAITLIST: 'border-signal-amber/50 bg-signal-amber/25 text-signal-amber-bright',
  NOT_BOOKABLE: 'border-signal-red/50 bg-signal-red/25 text-signal-red-bright',
  UNKNOWN: 'border-paper-50/30 bg-paper-50/10 text-paper-50/90',
}

interface StatusBadgeProps {
  availability: ParsedAvailability
  tone?: 'light' | 'dark' // match the surface the badge sits on
}

export function StatusBadge({ availability, tone = 'light' }: StatusBadgeProps) {
  const styles = tone === 'dark' ? DARK_STYLES : LIGHT_STYLES
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-1 font-ticket text-xs font-semibold tracking-wide ${styles[availability.status]}`}
    >
      {availability.raw}
    </span>
  )
}
