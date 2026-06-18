import { useState, type FormEvent } from 'react'
import { QUOTAS, type BookingQuota, type Station } from '../api/client'
import { MAX_DATE, MIN_DATE } from '../lib/bookingDates'
import { FIELD, LABEL } from './formStyles'
import { StationAutocomplete } from './StationAutocomplete'

interface TrainSearchFormProps {
  onSearch: (q: { source: string; destination: string; date: string }) => void
  searching: boolean
  quota: BookingQuota
  onQuotaChange: (quota: BookingQuota) => void
}

export function TrainSearchForm({
  onSearch,
  searching,
  quota,
  onQuotaChange,
}: TrainSearchFormProps) {
  const [fromText, setFromText] = useState('')
  const [fromStation, setFromStation] = useState<Station | null>(null)
  const [toText, setToText] = useState('')
  const [toStation, setToStation] = useState<Station | null>(null)
  const [date, setDate] = useState(MIN_DATE)

  const ready = Boolean(fromStation && toStation && date)

  function swap() {
    setFromText(toText)
    setToText(fromText)
    setFromStation(toStation)
    setToStation(fromStation)
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (searching || !fromStation || !toStation) return
    onSearch({ source: fromStation.code, destination: toStation.code, date })
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-10 rounded-xl border border-rail-200 bg-paper-50 p-5 shadow-sm sm:p-6"
    >
      <div className="grid items-end gap-3 sm:grid-cols-[1fr_auto_1fr]">
        <StationAutocomplete
          label="From"
          placeholder="New Delhi"
          text={fromText}
          onTextChange={setFromText}
          station={fromStation}
          onStationChange={setFromStation}
        />
        <button
          type="button"
          onClick={swap}
          aria-label="Swap From and To"
          className="mx-auto flex size-10 items-center justify-center rounded-full border border-rail-200 bg-paper-100 text-rail-700 transition-colors hover:border-rail-500 hover:text-rail-950 focus:outline-none focus:ring-2 focus:ring-rail-500/30 sm:mb-1"
        >
          <span aria-hidden className="text-lg">
            ⇄
          </span>
        </button>
        <StationAutocomplete
          label="To"
          placeholder="Mumbai Central"
          text={toText}
          onTextChange={setToText}
          station={toStation}
          onStationChange={setToStation}
        />
      </div>

      <div className="mt-4 grid items-end gap-4 sm:grid-cols-[auto_auto_1fr]">
        <div>
          <label htmlFor="ts-date" className={LABEL}>
            Journey date
          </label>
          <input
            id="ts-date"
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
          className="rounded-md bg-rail-900 px-6 py-3 font-ticket text-sm font-semibold uppercase tracking-[0.2em] text-paper-50 transition-colors hover:bg-rail-700 focus:outline-none focus:ring-2 focus:ring-rail-500 focus:ring-offset-2 focus:ring-offset-paper-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 sm:justify-self-end"
        >
          {searching ? 'Searching…' : 'Search trains'}
        </button>
      </div>
    </form>
  )
}
