import { useEffect, useRef, useState, type SubmitEvent } from 'react'
import { QUOTAS, type BookingQuota, type Station } from '../api'
import { MAX_DATE, MIN_DATE } from '../lib/bookingDates'
import { FIELD, LABEL } from './formStyles'
import { JourneyDatePicker } from './JourneyDatePicker'
import { StationAutocomplete } from './StationAutocomplete'
import type { TrainSearchPrefill } from './TrainSearchPanel'

const formatStation = (s: Station) =>
  s.name && s.name !== s.code ? `${s.name} (${s.code})` : s.code

interface TrainSearchFormProps {
  onSearch: (q: {
    source: string
    sourceName?: string
    destination: string
    destinationName?: string
    date: string
  }) => void
  searching: boolean
  quota: BookingQuota
  onQuotaChange: (quota: BookingQuota) => void
  initial?: TrainSearchPrefill
}

export function TrainSearchForm({
  onSearch,
  searching,
  quota,
  onQuotaChange,
  initial,
}: TrainSearchFormProps) {
  const initialFrom = initial?.source
    ? { code: initial.source, name: initial.sourceName ?? initial.source, city: '' }
    : null
  const initialTo = initial?.destination
    ? { code: initial.destination, name: initial.destinationName ?? initial.destination, city: '' }
    : null

  const [fromStation, setFromStation] = useState<Station | null>(initialFrom)
  const [fromText, setFromText] = useState(initialFrom ? formatStation(initialFrom) : '')
  const [toStation, setToStation] = useState<Station | null>(initialTo)
  const [toText, setToText] = useState(initialTo ? formatStation(initialTo) : '')
  const [date, setDate] = useState(initial?.date ?? MIN_DATE)

  const autoSearchPending = useRef(
    Boolean(initial?.source && initial?.destination && (initial?.date ?? MIN_DATE)),
  )

  useEffect(() => {
    if (!autoSearchPending.current) return
    if (searching || !fromStation || !toStation || !date) return
    autoSearchPending.current = false
    onSearch({
      source: fromStation.code,
      sourceName: fromStation.name && fromStation.name !== fromStation.code ? fromStation.name : undefined,
      destination: toStation.code,
      destinationName: toStation.name && toStation.name !== toStation.code ? toStation.name : undefined,
      date,
    })
  }, [fromStation, toStation, date, searching, onSearch])

  const ready = Boolean(fromStation && toStation && date)

  function swap() {
    setFromText(toText)
    setToText(fromText)
    setFromStation(toStation)
    setToStation(fromStation)
  }

  function handleSubmit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    if (searching || !fromStation || !toStation) return
    onSearch({
      source: fromStation.code,
      sourceName: fromStation.name && fromStation.name !== fromStation.code ? fromStation.name : undefined,
      destination: toStation.code,
      destinationName: toStation.name && toStation.name !== toStation.code ? toStation.name : undefined,
      date,
    })
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-8 rounded-xl border border-rail-200 bg-paper-50 p-5 shadow-sm sm:p-6"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <StationAutocomplete
            label="From"
            placeholder="New Delhi"
            text={fromText}
            onTextChange={setFromText}
            station={fromStation}
            onStationChange={setFromStation}
          />
        </div>
        <button
          type="button"
          onClick={swap}
          aria-label="Swap From and To"
          className="mx-auto flex size-10 shrink-0 items-center justify-center rounded-full border border-rail-200 bg-paper-100 text-rail-700 transition-colors hover:border-rail-500 hover:text-rail-950 focus:outline-none focus:ring-2 focus:ring-rail-500/30 sm:mb-1 cursor-pointer"
        >
          <span aria-hidden className="text-lg">
            ⇄
          </span>
        </button>
        <div className="flex-1">
          <StationAutocomplete
            label="To"
            placeholder="Mumbai Central"
            text={toText}
            onTextChange={setToText}
            station={toStation}
            onStationChange={setToStation}
          />
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-end">
        <div className="w-full sm:w-56">
          <label htmlFor="ts-date" className={LABEL}>
            Journey date
          </label>
          <JourneyDatePicker
            id="ts-date"
            value={date}
            onChange={setDate}
            min={MIN_DATE}
            max={MAX_DATE}
          />
        </div>

        <div className="w-full sm:w-44">
          <label htmlFor="ts-quota" className={LABEL}>
            Quota
          </label>
          <select
            id="ts-quota"
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

        <button
          type="submit"
          aria-disabled={searching || !ready}
          className="rounded-md bg-rail-900 px-6 py-3 font-ticket text-sm font-semibold uppercase tracking-widest text-paper-50 transition-colors hover:bg-rail-700 focus:outline-none focus:ring-2 focus:ring-rail-500 focus:ring-offset-2 focus:ring-offset-paper-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 sm:ml-auto cursor-pointer"
        >
          {searching ? 'Searching…' : 'Search trains'}
        </button>
      </div>
    </form>
  )
}
