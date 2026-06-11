import { useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { getTrainRoute, type SearchQuery, type TrainRoute } from '../api/client'

interface SearchFormProps {
  onSearch: (query: SearchQuery) => void
  searching: boolean
}

const DAY_MS = 86_400_000
const ARP_DAYS = 60 // IRCTC advance reservation period
const toInputDate = (d: Date) => d.toISOString().slice(0, 10)
// Computed once at module load (render must stay pure); stale only if the
// tab survives past midnight, and the backend re-validates anyway.
const MIN_DATE = toInputDate(new Date())
const MAX_DATE = toInputDate(new Date(Date.now() + ARP_DAYS * DAY_MS))

const LABEL = 'block font-ticket text-[11px] font-medium uppercase tracking-[0.18em] text-rail-700'
const FIELD =
  'mt-1.5 w-full rounded-md border border-rail-200 bg-white px-3 py-2.5 font-ticket text-sm text-rail-950 ' +
  'placeholder:text-rail-500/50 focus:border-rail-500 focus:outline-none focus:ring-2 focus:ring-rail-500/30 ' +
  'disabled:cursor-not-allowed disabled:bg-paper-200/60 disabled:text-rail-700/50'

export function SearchForm({ onSearch, searching }: SearchFormProps) {
  const [route, setRoute] = useState<TrainRoute | null>(null)
  const [routeError, setRouteError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  async function handleTrainNumberChange(e: ChangeEvent<HTMLInputElement>) {
    const value = e.target.value.trim()
    setRoute(null)
    setRouteError(null)
    if (!/^\d{5}$/.test(value)) return
    abortRef.current?.abort() // a newer keystroke supersedes any in-flight lookup
    const controller = new AbortController()
    abortRef.current = controller
    try {
      setRoute(await getTrainRoute(value, controller.signal))
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setRouteError(err instanceof Error ? err.message : 'Could not load this train')
    }
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const data = new FormData(e.currentTarget)
    onSearch({
      trainNumber: String(data.get('trainNumber') ?? ''),
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
            onChange={handleTrainNumberChange}
            className={`${FIELD} tracking-[0.3em]`}
          />
          {route && (
            <p className="mt-1.5 text-xs text-signal-green-deep">
              {route.train_name} · {route.stations.length} stops
            </p>
          )}
          {routeError && <p className="mt-1.5 text-xs text-signal-red">{routeError}</p>}
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

      <button
        type="submit"
        disabled={searching || !route}
        className="mt-5 w-full rounded-md bg-rail-900 px-6 py-3 font-ticket text-sm font-semibold uppercase tracking-[0.2em] text-paper-50 transition-colors hover:bg-rail-700 focus:outline-none focus:ring-2 focus:ring-rail-500 focus:ring-offset-2 focus:ring-offset-paper-50 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
      >
        {searching ? 'Checking combinations…' : 'Find me a seat'}
      </button>
    </form>
  )
}
