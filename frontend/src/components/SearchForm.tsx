import { useEffect, useRef, useState, type SubmitEvent } from 'react'
import {
  ApiError,
  getTrainRoute,
  QUOTAS,
  TRAVEL_CLASSES,
  type BookingQuota,
  type SearchQuery,
  type TrainRoute,
  type TravelClass,
} from '../api'
import { FIELD, LABEL } from './formStyles'
import { MAX_DATE, MIN_DATE } from '../lib/bookingDates'

export interface SearchPrefill {
  trainNumber?: string
  source?: string
  sourceName?: string
  destination?: string
  destinationName?: string
  date?: string
  travelClass?: TravelClass
  quota?: BookingQuota
}

interface SearchFormProps {
  onSearch: (query: SearchQuery) => void
  searching: boolean
  travelClass: TravelClass
  onTravelClassChange: (travelClass: TravelClass) => void
  quota: BookingQuota
  onQuotaChange: (quota: BookingQuota) => void
  partial: boolean
  onPartialChange: (v: boolean) => void
  minCoveragePct: number
  onMinCoveragePctChange: (v: number) => void
  requireConnect: boolean
  onRequireConnectChange: (v: boolean) => void
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
  partial,
  onPartialChange,
  minCoveragePct,
  onMinCoveragePctChange,
  requireConnect,
  onRequireConnectChange,
  initial,
}: SearchFormProps) {
  const [trainNumber, setTrainNumber] = useState(initial?.trainNumber ?? '')
  const [source, setSource] = useState(initial?.source ?? '')
  const [destination, setDestination] = useState(initial?.destination ?? '')
  const [date, setDate] = useState(initial?.date ?? '')
  const [route, setRoute] = useState<TrainRoute | null>(null)
  const [routeError, setRouteError] = useState<string | null>(null)
  const [retryToken, setRetryToken] = useState(0)
  // A Train Search deep-link arrives with a full prefill; fire the search
  // immediately without waiting for route stops to finish downloading.
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

  // Auto-run the deep-linked search once immediately when inputs are present.
  // The ref guard keeps it to a single fire.
  useEffect(() => {
    if (!autoSearchPending.current) return
    if (searching || !source || !destination || !date || !trainNumber) return
    autoSearchPending.current = false
    onSearch({ trainNumber, source, destination, date, travelClass, quota, partial, minCoveragePct, requireConnect })
  }, [source, destination, date, searching, trainNumber, travelClass, quota, partial, minCoveragePct, requireConnect, onSearch])

  function handleSubmit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    if (searching || !route) return
    onSearch({
      trainNumber,
      source,
      destination,
      date,
      travelClass, // controlled — stays in sync when the switch banner changes it
      quota, // controlled — likewise kept in sync with the banner
      partial,
      minCoveragePct,
      requireConnect,
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
            disabled={!route && !source}
            className={FIELD}
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            {!route && source ? (
              <option value={source}>
                {initial?.sourceName ? `${source} — ${initial.sourceName}` : source}
              </option>
            ) : (
              <>
                <option value="" disabled>
                  {route ? 'Select station' : 'Enter train first'}
                </option>
                {route?.stations.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.code} — {s.name}
                  </option>
                ))}
              </>
            )}
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
            disabled={!route && !destination}
            className={FIELD}
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
          >
            {!route && destination ? (
              <option value={destination}>
                {initial?.destinationName ? `${destination} — ${initial.destinationName}` : destination}
              </option>
            ) : (
              <>
                <option value="" disabled>
                  {route ? 'Select station' : 'Enter train first'}
                </option>
                {route?.stations.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.code} — {s.name}
                  </option>
                ))}
              </>
            )}
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

      {/* --- Partial coverage controls --- */}
      <div className="mt-5 overflow-hidden rounded-lg border border-rail-200 bg-paper-100/60">
        {/* Toggle header */}
        <label className="group flex cursor-pointer items-center gap-3 px-4 py-3 transition-colors hover:bg-paper-200/40">
          <span className="relative inline-flex h-[22px] w-[40px] shrink-0 items-center">
            <input
              id="partialToggle"
              type="checkbox"
              checked={partial}
              onChange={(e) => onPartialChange(e.target.checked)}
              className="peer sr-only"
            />
            <span className="block h-[22px] w-[40px] rounded-full bg-rail-200 shadow-inner transition-colors duration-200 peer-checked:bg-rail-900 peer-focus-visible:ring-2 peer-focus-visible:ring-rail-500 peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-paper-50" />
            <span className="absolute left-[3px] top-[3px] h-4 w-4 rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.2)] transition-transform duration-200 peer-checked:translate-x-[18px]" />
          </span>
          <div className="flex flex-col">
            <span className="font-ticket text-xs font-semibold uppercase tracking-[0.15em] text-rail-700">
              Allow Partial Route Seats
            </span>
            <span className="mt-0.5 text-[11px] leading-tight text-rail-500">
              Find confirmed seats covering part of your trip when full route is not available
            </span>
          </div>
        </label>

        {/* Expandable sub-controls */}
        <div
          className="grid transition-[grid-template-rows] duration-300 ease-in-out"
          style={{ gridTemplateRows: partial ? '1fr' : '0fr' }}
        >
          <div className="overflow-hidden">
            <div className="border-t border-rail-200/50 px-4 pb-4 pt-3">
              {/* Coverage slider */}
              <div>
                <div className="flex items-baseline justify-between">
                  <label htmlFor="minCoverage" className={LABEL}>
                    Minimum Journey Covered
                  </label>
                  <span className="font-ticket text-sm font-semibold tabular-nums text-rail-950">
                    {Math.round(minCoveragePct * 100)}%
                  </span>
                </div>
                <div className="group/slider relative mt-2.5">
                  <input
                    id="minCoverage"
                    type="range"
                    min={10}
                    max={100}
                    step={5}
                    value={Math.round(minCoveragePct * 100)}
                    onChange={(e) => onMinCoveragePctChange(Number(e.target.value) / 100)}
                    className="coverage-slider h-2 w-full cursor-pointer appearance-none rounded-full bg-rail-200/80"
                    style={{ '--fill': `${((Math.round(minCoveragePct * 100) - 10) / 90) * 100}%` } as React.CSSProperties}
                  />
                </div>
                <p className="mt-2 text-[11px] leading-relaxed text-rail-500">
                  Only show tickets covering at least this percentage of your total route
                </p>
              </div>

              {/* Separator */}
              <div className="my-4 border-t border-dashed border-rail-200/60" />

              {/* Require connect toggle */}
              <label className="group flex cursor-pointer items-center gap-3.5">
                <span className="relative inline-flex h-[22px] w-[40px] shrink-0 items-center">
                  <input
                    id="requireConnect"
                    type="checkbox"
                    checked={requireConnect}
                    onChange={(e) => onRequireConnectChange(e.target.checked)}
                    className="peer sr-only"
                  />
                  <span className="block h-[22px] w-[40px] rounded-full bg-rail-200 shadow-inner transition-colors duration-200 peer-checked:bg-rail-900 peer-focus-visible:ring-2 peer-focus-visible:ring-rail-500 peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-paper-50" />
                  <span className="absolute left-[3px] top-[3px] h-4 w-4 rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.2)] transition-transform duration-200 peer-checked:translate-x-[18px]" />
                </span>
                <div className="flex flex-col">
                  <span className="font-ticket text-[11px] font-semibold uppercase tracking-[0.15em] text-rail-700">
                    Connect at Origin or Destination
                  </span>
                  <span className="mt-0.5 text-[11px] leading-tight text-rail-500">
                    Only show tickets starting at your boarding station or ending at your destination station
                  </span>
                </div>
              </label>
            </div>
          </div>
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
