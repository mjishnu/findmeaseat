// IRCTC booking-window bounds for <input type="date"> (min/max), shared by the
// seat-finder and train-search forms. The railway's booking day is IST; the
// backend re-validates, so these need only be right at module-load time.
const BOOKING_TZ = 'Asia/Kolkata'
export const ARP_DAYS = 60 // IRCTC advance reservation period

// en-CA renders YYYY-MM-DD, the format <input type="date"> min/max expects.
export const istToday = () =>
  new Intl.DateTimeFormat('en-CA', { timeZone: BOOKING_TZ }).format(new Date())

const addDays = (ymd: string, days: number) => {
  const d = new Date(`${ymd}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export const MIN_DATE = istToday()
export const MAX_DATE = addDays(MIN_DATE, ARP_DAYS)

export function getWeekdayIndex(ymd: string): number {
  const [y, m, d] = ymd.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  return (date.getDay() + 6) % 7 // 0 = Mon, ..., 6 = Sun
}

export function isDayRunning(ymd: string, runningDays?: string): boolean {
  if (!runningDays || runningDays.length !== 7) return true
  const dayIdx = getWeekdayIndex(ymd)
  return runningDays[dayIdx] === '1'
}

export function findNextRunningDate(
  ymd: string,
  runningDays?: string,
  minDate: string = MIN_DATE,
  maxDate: string = MAX_DATE,
): string | null {
  if (!runningDays || runningDays.length !== 7) return null
  const [y, m, d] = ymd.split('-').map(Number)
  const current = new Date(y, m - 1, d)

  for (let i = 1; i <= 60; i++) {
    const next = new Date(current)
    next.setDate(next.getDate() + i)
    const nextYmd = next.toISOString().slice(0, 10)
    if (nextYmd > maxDate) break
    if (nextYmd >= minDate && isDayRunning(nextYmd, runningDays)) {
      return nextYmd
    }
  }
  return null
}

/**
 * Shifts the 7-day runningDays bitmask (Mon=0, ..., Sun=6) by the station's day offset
 * relative to the origin station (e.g. dayOffset = day - 1).
 */
export function shiftRunningDays(runningDays?: string, dayOffset: number = 0): string | undefined {
  if (!runningDays || runningDays.length !== 7 || dayOffset === 0) return runningDays
  const res = new Array(7).fill('0')
  for (let i = 0; i < 7; i++) {
    if (runningDays[i] === '1') {
      const shiftedIdx = (i + dayOffset) % 7
      const normalizedIdx = shiftedIdx < 0 ? shiftedIdx + 7 : shiftedIdx
      res[normalizedIdx] = '1'
    }
  }
  return res.join('')
}
