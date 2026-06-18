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
