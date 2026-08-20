import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { searchStations, type Station } from '../api'
import { FIELD, LABEL } from './formStyles'

interface StationAutocompleteProps {
  label: string
  placeholder?: string
  text: string
  onTextChange: (text: string) => void
  station: Station | null
  onStationChange: (station: Station | null) => void
}

const formatStation = (s: Station) =>
  s.name && s.name !== s.code ? `${s.name} (${s.code})` : s.code

export function StationAutocomplete({
  label,
  placeholder,
  text,
  onTextChange,
  station,
  onStationChange,
}: StationAutocompleteProps) {
  const id = useId()
  const [suggestions, setSuggestions] = useState<Station[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const blurTimer = useRef<number | undefined>(undefined)

  // Debounced lookup. Skips when the text already equals the picked station, so
  // selecting doesn't immediately re-query. Network blips degrade to no dropdown.
  // Every state update happens inside the timer/promise (never synchronously in
  // the effect body), so the lookup can't trigger a cascading render.
  useEffect(() => {
    const q = text.trim()
    const shouldSearch =
      open && q.length >= 2 && !(station && text === formatStation(station))
    const controller = new AbortController()
    const timer = window.setTimeout(
      () => {
        if (!shouldSearch) {
          setSuggestions([])
          setActive(-1)
          return
        }
        searchStations(q, controller.signal)
          .then((rows) => {
            setSuggestions(rows)
            setActive(rows.length ? 0 : -1)
          })
          .catch((err: unknown) => {
            if (err instanceof DOMException && err.name === 'AbortError') return
            setSuggestions([])
          })
      },
      shouldSearch ? 250 : 0, // clear stale results on the next tick; debounce real queries
    )
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [text, open, station])

  useEffect(() => () => window.clearTimeout(blurTimer.current), [])

  function select(s: Station) {
    onTextChange(formatStation(s))
    onStationChange(s)
    setOpen(false)
    setSuggestions([])
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open || suggestions.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault()
      select(suggestions[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const showList = open && suggestions.length > 0

  return (
    <div className="relative">
      <label htmlFor={id} className={LABEL}>
        {label}
      </label>
      <input
        id={id}
        type="text"
        autoComplete="off"
        spellCheck={false}
        placeholder={placeholder}
        value={text}
        role="combobox"
        aria-expanded={showList}
        aria-controls={`${id}-listbox`}
        aria-activedescendant={active >= 0 ? `${id}-opt-${active}` : undefined}
        onChange={(e) => {
          onTextChange(e.target.value)
          onStationChange(null) // typing invalidates a prior pick
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          // Delay so a suggestion's mousedown registers before we close.
          blurTimer.current = window.setTimeout(() => setOpen(false), 150)
        }}
        onKeyDown={handleKeyDown}
        className={FIELD}
      />
      {showList && (
        <ul
          id={`${id}-listbox`}
          role="listbox"
          className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border border-rail-200 bg-paper-50 py-1 shadow-lg"
        >
          {suggestions.map((s, i) => (
            <li
              key={s.code}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault() // keep focus; fire before blur closes the list
                select(s)
              }}
              className={`flex cursor-pointer items-baseline justify-between gap-3 px-3 py-2 text-sm ${
                i === active ? 'bg-signal-green/15' : ''
              }`}
            >
              <span className="truncate text-rail-950">
                {s.name}
                {s.city && s.city !== s.name && (
                  <span className="text-rail-700"> · {s.city}</span>
                )}
              </span>
              <span className="font-ticket text-xs font-semibold tracking-wide text-rail-700">
                {s.code}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
