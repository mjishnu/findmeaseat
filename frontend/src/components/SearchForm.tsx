import { useEffect, useState, type FormEvent } from 'react'
import { ApiError, getTrainRoute, type SearchQuery, type TrainRoute } from '../api/client'

interface SearchFormProps {
  onSearch: (query: SearchQuery) => void
  searching: boolean
}

const ARP_DAYS = 60 // IRCTC advance reservation period
const BOOKING_TZ = 'Asia/Kolkata' // the railway's booking day is IST, matching the backend
// en-CA renders YYYY-MM-DD, the format <input type="date"> min/max expects.
const istToday = () =>
  new Intl.DateTimeFormat('en-CA', { timeZone: BOOKING_TZ }).format(new Date())
const addDays = (ymd: string, days: number) => {
  const d = new Date(`${ymd}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}
// Computed once at module load (render must stay pure); stale only if the tab
// survives past IST midnight, and the backend re-validates anyway.
const MIN_DATE = istToday()
const MAX_DATE = addDays(MIN_DATE, ARP_DAYS)

const LABEL = 'block font-ticket text-[11px] font-medium uppercase tracking-[0.18em] text-rail-700'
const FIELD =
  'mt-1.5 w-full rounded-md border border-rail-200 bg-white px-3 py-2.5 font-ticket text-sm text-rail-950 ' +
  'placeholder:text-rail-700/80 focus:border-rail-500 focus:outline-none focus:ring-2 focus:ring-rail-500/30 ' +
  'disabled:cursor-not-allowed disabled:bg-paper-200/60 disabled:text-rail-700/50'

export function SearchForm({ onSearch, searching }: SearchFormProps) {
  const [trainNumber, setTrainNumber] = useState('')
  const [route, setRoute] = useState<TrainRoute | null>(null)
  const [routeError, setRouteError] = useState<string | null>(null)
  const [retryToken, setRetryToken] = useState(0)

  function handleTrainNumberChange(value: string) {
    setTrainNumber(value.trim())
    setRoute(null) // a stale route must never outlive an edited number
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

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (searching || !route) return // button is aria-disabled, not disabled
    const data = new FormData(e.currentTarget)
    onSearch({
      trainNumber,
      source: String(data.get('source') ?? ''),
      destination: String(data.get('destination') ?? ''),
      date: String(data.get('date') ?? ''),
    })
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-10 rounded-xl border border-rail-200 bg-paper-50 p-5 shadow-sm sm:p-6"
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
          <select id="source" name="source" required disabled={!route} className={FIELD} defaultValue="">
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
            defaultValue=""
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
            className={FIELD}
          />
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
