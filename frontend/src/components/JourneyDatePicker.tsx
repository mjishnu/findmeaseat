import { useEffect, useRef, useState } from 'react'
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react'
import { FIELD } from './formStyles'
import {
  isDayRunning,
  MAX_DATE,
  MIN_DATE,
} from '../lib/bookingDates'

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

function formatDateDisplay(ymd: string): string {
  if (!ymd) return 'Select date'
  try {
    const [y, m, d] = ymd.split('-').map(Number)
    const date = new Date(y, m - 1, d)
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return ymd
  }
}

interface JourneyDatePickerProps {
  id?: string
  value: string
  onChange: (value: string) => void
  min?: string
  max?: string
  runningDays?: string // e.g. "1111111" or "0110111"
  required?: boolean
  disabled?: boolean
}

export function JourneyDatePicker({
  id = 'journey-date',
  value,
  onChange,
  min = MIN_DATE,
  max = MAX_DATE,
  runningDays,
  disabled = false,
}: JourneyDatePickerProps) {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Calendar current viewed month/year
  const [navOffset, setNavOffset] = useState<number>(0)

  // Calculate base year and month from value or today, adjusted by navOffset
  const baseDate = value && /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? new Date(value + 'T00:00:00')
    : new Date()
  const viewDate = new Date(baseDate.getFullYear(), baseDate.getMonth() + navOffset, 1)
  const viewYear = viewDate.getFullYear()
  const viewMonth = viewDate.getMonth()

  // Close calendar on outside click or Escape
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      document.addEventListener('keydown', handleKeyDown)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  // Build grid of days for viewMonth / viewYear
  const firstDayOfMonth = new Date(viewYear, viewMonth, 1)
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
  const startingDayOffset = (firstDayOfMonth.getDay() + 6) % 7 // 0 for Mon, ..., 6 for Sun

  // Navigation handlers
  const canGoPrev = () => {
    const prevMonthDate = new Date(viewYear, viewMonth, 0)
    const prevMonthYmd = prevMonthDate.toISOString().slice(0, 7)
    return prevMonthYmd >= min.slice(0, 7)
  }

  const canGoNext = () => {
    const nextMonthDate = new Date(viewYear, viewMonth + 1, 1)
    const nextMonthYmd = nextMonthDate.toISOString().slice(0, 7)
    return nextMonthYmd <= max.slice(0, 7)
  }

  const prevMonth = () => {
    setNavOffset((o) => o - 1)
  }

  const nextMonth = () => {
    setNavOffset((o) => o + 1)
  }

  const isCurrentSelectionNonRunning = Boolean(value && runningDays && !isDayRunning(value, runningDays))

  return (
    <div ref={containerRef} className="relative">
      <button
        id={id}
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        className={`${FIELD} flex items-center justify-between gap-2 text-left cursor-pointer transition-colors`}
      >
        <span className={`truncate ${!value ? 'text-rail-700/80' : 'text-rail-950'}`}>
          {formatDateDisplay(value)}
        </span>
        <div className="flex items-center gap-1.5 shrink-0">
          {isCurrentSelectionNonRunning && (
            <AlertTriangle className="size-4 text-signal-amber-deep" aria-label="Train does not run on this day" />
          )}
          <CalendarIcon className="size-4 text-rail-700" />
        </div>
      </button>

      {isOpen && (
        <div
          role="dialog"
          aria-label="Choose journey date"
          className="absolute left-0 top-full z-50 mt-2 w-72 rounded-xl border border-rail-200 bg-paper-50 p-4 shadow-xl ring-1 ring-black/5 animate-in fade-in zoom-in-95 duration-150"
        >
          {/* Header with Month Year and Prev/Next */}
          <div className="flex items-center justify-between pb-3">
            <span className="font-ticket text-sm font-bold text-rail-950">
              {MONTH_NAMES[viewMonth]} {viewYear}
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={prevMonth}
                disabled={!canGoPrev()}
                aria-label="Previous month"
                className="grid size-7 place-items-center rounded-md text-rail-700 transition-colors hover:bg-rail-200/50 hover:text-rail-950 disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-rail-700 cursor-pointer disabled:cursor-not-allowed"
              >
                <ChevronLeft className="size-4" />
              </button>
              <button
                type="button"
                onClick={nextMonth}
                disabled={!canGoNext()}
                aria-label="Next month"
                className="grid size-7 place-items-center rounded-md text-rail-700 transition-colors hover:bg-rail-200/50 hover:text-rail-950 disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-rail-700 cursor-pointer disabled:cursor-not-allowed"
              >
                <ChevronRight className="size-4" />
              </button>
            </div>
          </div>

          {/* Weekday headers */}
          <div className="grid grid-cols-7 gap-1 border-y border-rail-200 py-1.5 text-center">
            {WEEKDAYS.map((w) => (
              <span key={w} className="font-ticket text-xs font-semibold text-rail-500">
                {w}
              </span>
            ))}
          </div>

          {/* Days Grid */}
          <div className="mt-2 grid grid-cols-7 gap-1">
            {/* Blank leading slots */}
            {Array.from({ length: startingDayOffset }).map((_, i) => (
              <div key={`empty-${i}`} className="size-8" />
            ))}

            {/* Days of month */}
            {Array.from({ length: daysInMonth }).map((_, i) => {
              const dayNum = i + 1
              const monthStr = String(viewMonth + 1).padStart(2, '0')
              const dayStr = String(dayNum).padStart(2, '0')
              const dayYmd = `${viewYear}-${monthStr}-${dayStr}`

              const isOutOfRange = dayYmd < min || dayYmd > max
              const hasRunningSchedule = Boolean(runningDays && runningDays.length === 7)
              const runs = isDayRunning(dayYmd, runningDays)
              const isSelected = dayYmd === value
              const isToday = dayYmd === MIN_DATE

              let dayClasses =
                'grid size-8 place-items-center rounded-full font-ticket text-xs transition-all cursor-pointer'

              if (isOutOfRange) {
                dayClasses += ' text-rail-300 cursor-not-allowed opacity-40 hover:bg-transparent'
              } else if (isSelected) {
                dayClasses +=
                  ' bg-rail-950 font-bold text-paper-50 shadow-sm ring-2 ring-offset-1 ring-rail-800'
              } else if (hasRunningSchedule) {
                if (runs) {
                  // Round green hue for operating days
                  dayClasses +=
                    ' bg-signal-green/15 text-signal-green-deep font-semibold border border-signal-green/30 hover:bg-signal-green/25 hover:shadow-sm'
                } else {
                  // Clean neutral tone for non-operating days
                  dayClasses += ' text-rail-600 font-medium hover:bg-rail-200/50 hover:text-rail-950'
                }
              } else {
                dayClasses += ' text-rail-900 font-medium hover:bg-rail-200/50'
                if (isToday) {
                  dayClasses += ' border border-rail-400 font-bold'
                }
              }

              return (
                <button
                  key={dayYmd}
                  type="button"
                  disabled={isOutOfRange}
                  onClick={() => {
                    onChange(dayYmd)
                    setNavOffset(0)
                    setIsOpen(false)
                  }}
                  title={
                    isOutOfRange
                      ? 'Outside booking window'
                      : hasRunningSchedule && !runs
                        ? 'Train usually does not operate on this day (Click to select anyway)'
                        : dayYmd
                  }
                  className={dayClasses}
                >
                  {dayNum}
                </button>
              )
            })}
          </div>

          {/* Legend / Running days info footer if runningDays provided */}
          {runningDays && runningDays.length === 7 && (
            <div className="mt-3 flex items-center justify-between border-t border-rail-200 pt-2 text-xs text-rail-700">
              <span className="flex items-center gap-1.5 font-medium">
                <span className="inline-block size-2 rounded-full bg-signal-green/30 border border-signal-green" />
                <span>Normal Operating Days</span>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
