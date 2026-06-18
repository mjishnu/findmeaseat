import type { BookingQuota, SwitchAlternative, TravelClass } from '../api/client'
import { QUOTAS } from '../api/client'
import { StatusBadge } from './StatusBadge'

interface SwitchSuggestionBannerProps {
  alternatives: SwitchAlternative[]
  searchedClass: TravelClass
  searchedQuota: BookingQuota
  onSwitch: (travelClass: TravelClass, quota: BookingQuota) => void
}

function formatDelta(delta: number | null): string {
  if (delta == null) return ''
  if (delta === 0) return 'same fare'
  return delta > 0 ? `+₹${delta}` : `−₹${Math.abs(delta)}`
}

function quotaLabel(quota: BookingQuota): string {
  return QUOTAS.find((q) => q.value === quota)?.label ?? quota
}

export function SwitchSuggestionBanner({
  alternatives,
  searchedClass,
  searchedQuota,
  onSwitch,
}: SwitchSuggestionBannerProps) {
  if (alternatives.length === 0) return null
  return (
    <div className="mt-6 rounded-xl border border-signal-green/40 bg-signal-green/10 p-4 sm:p-5">
      <p className="font-ticket text-[11px] font-semibold uppercase tracking-[0.18em] text-signal-green-deep">
        Better odds in another class
      </p>
      <p className="mt-1 text-sm text-rail-700">
        You searched <span className="font-semibold">{quotaLabel(searchedQuota)}</span> ·{' '}
        <span className="font-semibold">{searchedClass}</span>. These classes are more likely to
        confirm in the same quota — tap to switch.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {alternatives.map((alt, index) => {
          const delta = formatDelta(alt.fare_delta)
          return (
            <button
              key={alt.travel_class}
              type="button"
              onClick={() => onSwitch(alt.travel_class, alt.quota)}
              className="group flex items-center gap-2 rounded-lg border border-rail-200 bg-paper-50 px-3 py-2 text-sm shadow-sm transition-colors hover:border-signal-green hover:bg-signal-green/10 focus:outline-none focus:ring-2 focus:ring-signal-green/40"
              aria-label={`Switch to ${alt.travel_class} — ${alt.availability.raw}${delta ? `, ${delta}` : ''}`}
            >
              <span className="font-ticket font-bold tracking-wide text-rail-950">
                {alt.travel_class}
              </span>
              <StatusBadge availability={alt.availability} />
              {delta && <span className="text-xs text-rail-700">{delta}</span>}
              {/* Arrow connects to the next chip — omitted on the last (nothing follows). */}
              {index < alternatives.length - 1 && (
                <span
                  aria-hidden
                  className="text-rail-500 transition-transform group-hover:translate-x-0.5"
                >
                  →
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
