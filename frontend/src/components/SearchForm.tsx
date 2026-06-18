import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ApiError,
  getTrainRoute,
  QUOTAS,
  TRAVEL_CLASSES,
  type BookingQuota,
  type SearchQuery,
  type TrainRoute,
  type TravelClass,
} from '../api/client'
import { FIELD, LABEL } from './formStyles'
import { MAX_DATE, MIN_DATE } from '../lib/bookingDates'

export interface SearchPrefill {
  trainNumber?: string
  source?: string
  destination?: string
  date?: string
}

interface SearchFormProps {
  onSearch: (query: SearchQuery) => void
  searching: boolean
  travelClass: TravelClass
  onTravelClassChange: (travelClass: TravelClass) => void
  quota: BookingQuota
  onQuotaChange: (quota: BookingQuota) => void
  // Seed values from a Train Search deep-link. The parent remounts this form
  // (via key) when a new prefill arrives, so seeding at useState suffices.
  initial?: SearchPrefill
}

export function SearchForm({
  onSearch,
  searching,
  travelClass,
  onTravelClassChange,
  quota,
  onQuotaChange,
  initial,
}: SearchFormProps) {
  const [trainNumber, setTrainNumber] = useState(initial?.trainNumber ?? '')
  const [source, setSource] = useState(initial?.source ?? '')
  const [destination, setDestination] = useState(initial?.destination ?? '')
  const [date, setDate] = useState(initial?.date ?? '')
  const [route, setRoute] = useState<TrainRoute | null>(null)
  const [routeError, setRouteError] = useState<string | null>(null)
  const [retryToken, setRetryToken] = useState(0)
  // A Train Search deep-link arrives with a full prefill; once the route loads
  // (the From/To selects need its stations) we fire the search automatically.
  const autoSearchPending = useRef(
    Boolean(initial?.trainNumber && initial?.source && initial?.destination && initial?.date),
  )

  function handleTrainNumberChange(value: string) {
    setTrainNumber(value.trim())
    setSource('') // a stale route/selection must never outlive an edited number
    setDestination('')
    setRoute(null)
    setRouteError(null)
  }

  // Effect (not the change handler) owns the fetch so cleanup aborts the
  // stale request even when the value becomes invalid mid-flight.
  useEffect(() => {
    if (!/^\d{5}$/.test(trainNumber)) return
    const controller = new AbortController()
    getTrainRoute(trainNumber, controller.signal)
      .then(setRoute)
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        setRouteError(
          err instanceof ApiError
            ? err.message
            : 'Could not reach the server — is the backend running?',
        )
      })
    return () => controller.abort()
  }, [trainNumber, retryToken])

  // Auto-run the deep-linked search once, after the route (and thus the seeded
  // From/To options) is in place. The ref guard keeps it to a single fire.
  useEffect(() => {
    if (!autoSearchPending.current) return
    if (searching || !route || !source || !destination || !date) return
    autoSearchPending.current = false
    onSearch({ trainNumber, source, destination, date, travelClass, quota })
  }, [route, source, destination, date, searching, trainNumber, travelClass, quota, onSearch])

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (searching || !route) return // button is aria-disabled, not disabled
    onSearch({
      trainNumber,
      source,
      destination,
      date,
      travelClass, // controlled — stays in sync when the switch banner changes it
      quota, // controlled — likewise kept in sync with the banner
    })
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-10 rounded-xl border border-rail-200 bg-paper-50 p-5 shadow-sm sm:p-6"
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-6">
        <div>
          <label htmlFor="trainNumber" className={LABEL}>
            Train number
          </label>
          <input
            id="trainNumber"
            name="trainNumber"
            type="text"
            inputMode="numeric"
            placeholder="12345"
            required
            pattern="\d{5}"
            maxLength={5}
            value={trainNumber}
            onChange={(e) => handleTrainNumberChange(e.target.value)}
            className={`${FIELD} tracking-[0.3em]`}
          />
          {/* Persistent live region so screen readers hear lookup results */}
          <div aria-live="polite" className="mt-1.5 min-h-4">
            {route && (
              <p className="text-xs text-signal-green-deep">
                {route.train_name} · {route.stations.length} stops
              </p>
            )}
            {routeError && (
              <p role="alert" className="text-xs text-signal-red">
                {routeError}{' '}
                <button
                  type="button"
                  onClick={() => {
                    setRouteError(null)
                    setRetryToken((t) => t + 1)
                  }}
                  className="font-semibold underline underline-offset-2 hover:text-rail-950"
                >
                  Retry
                </button>
              </p>
            )}
          </div>
        </div>

        <div>
          <label htmlFor="source" className={LABEL}>
            From
          </label>
          <select
            id="source"
            name="source"
            required
            disabled={!route}
            className={FIELD}
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            <option value="" disabled>
              {route ? 'Select station' : 'Enter train first'}
            </option>
            {route?.stations.map((s) => (
              <option key={s.code} value={s.code}>
                {s.code} — {s.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="destination" className={LABEL}>
            To
          </label>
          <select
            id="destination"
            name="destination"
            required
            disabled={!route}
            className={FIELD}
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
          >
            <option value="" disabled>
              {route ? 'Select station' : 'Enter train first'}
            </option>
            {route?.stations.map((s) => (
              <option key={s.code} value={s.code}>
                {s.code} — {s.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="date" className={LABEL}>
            Journey date
          </label>
          <input
            id="date"
            name="date"
            type="date"
            required
            min={MIN_DATE}
            max={MAX_DATE}
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className={FIELD}
          />
        </div>

        <div>
          <label htmlFor="travelClass" className={LABEL}>
            Class
          </label>
          <select
            id="travelClass"
            name="travelClass"
            className={FIELD}
            value={travelClass}
            onChange={(e) => onTravelClassChange(e.target.value as TravelClass)}
          >
            {TRAVEL_CLASSES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="quota" className={LABEL}>
            Quota
          </label>
          <select
            id="quota"
            name="quota"
            className={FIELD}
            value={quota}
            onChange={(e) => onQuotaChange(e.target.value as BookingQuota)}
          >
            {QUOTAS.map((q) => (
              <option key={q.value} value={q.value}>
                {q.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* aria-disabled (not disabled) keeps keyboard focus on the button
          through the search; handleSubmit guards the actual submit. */}
      <button
        type="submit"
        aria-disabled={searching || !route}
        className="mt-5 w-full rounded-md bg-rail-900 px-6 py-3 font-ticket text-sm font-semibold uppercase tracking-[0.2em] text-paper-50 transition-colors hover:bg-rail-700 focus:outline-none focus:ring-2 focus:ring-rail-500 focus:ring-offset-2 focus:ring-offset-paper-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 sm:w-auto"
      >
        {searching ? 'Checking combinations…' : 'Find me a seat'}
      </button>
    </form>
  )
}
