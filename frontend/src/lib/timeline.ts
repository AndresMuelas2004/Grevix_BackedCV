import type { CvEntry, ParsedCv } from '../api/types'

// How the CV's dates were read: one row per job, project and degree, and the total.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export interface TimelineRow {
  id: string
  title: string
  organization: string | null
  dates: string
  counted: string
  countedMuted: boolean // not counted (education, projects, undated jobs)
}

export interface Timeline {
  rows: TimelineRow[]
  total: string | null // "about 9 years 10 months", or "at least ..." when dates are missing
  note: string | null
}

interface YearMonth {
  year: number
  month: number | null // 1 to 12; null when the CV gives only the year
}

function parseDate(value: string | null): YearMonth | 'present' | null {
  if (value === null) return null
  const text = value.trim().toLowerCase()
  if (text === 'present' || text === 'current' || text === 'now') return 'present'
  const full = /^(\d{4})-(\d{1,2})/.exec(text)
  if (full) return { year: Number(full[1]), month: Number(full[2]) }
  const year = /^(\d{4})$/.exec(text)
  if (year) return { year: Number(year[1]), month: null }
  return null
}

function formatDate(value: string | null): string {
  const parsed = parseDate(value)
  if (parsed === null) return value ?? 'no date'
  if (parsed === 'present') return 'today'
  if (parsed.month === null || parsed.month < 1 || parsed.month > 12) {
    return `${parsed.year} (month unknown)`
  }
  return `${MONTHS[parsed.month - 1]} ${parsed.year}`
}

// "Mar 2019 to today", "2015 (month unknown) to Dec 2017", "Jun 2015".
export function formatRange(entry: CvEntry): string {
  if (entry.start === null && entry.end === null) return 'No dates found'
  if (entry.start === null) return formatDate(entry.end)
  if (entry.end === null) return formatDate(entry.start)
  return `${formatDate(entry.start)} to ${formatDate(entry.end)}`
}

// "7 years 7 months", "1 year", "5 months".
export function formatDuration(months: number): string {
  const whole = Math.max(0, Math.round(months))
  if (whole === 0) return 'Less than a month'
  const years = Math.floor(whole / 12)
  const rest = whole % 12
  const parts: string[] = []
  if (years > 0) parts.push(`${years} ${years === 1 ? 'year' : 'years'}`)
  if (rest > 0) parts.push(`${rest} ${rest === 1 ? 'month' : 'months'}`)
  return parts.join(' ')
}

// Months between two dates, counted inclusively like the backend. A date with only the year counts
// at the shortest (January to December would overcount, so the start month is taken as December
// and the end month as January). Null when the dates cannot be read.
function monthsBetween(entry: CvEntry, today: Date): number | null {
  const start = parseDate(entry.start)
  const end = parseDate(entry.end)
  if (start === null || start === 'present' || end === null) return null
  const startIndex = start.year * 12 + (start.month ?? 12) - 1
  const endIndex =
    end === 'present'
      ? today.getFullYear() * 12 + today.getMonth()
      : end.year * 12 + (end.month ?? 1) - 1
  const months = endIndex - startIndex + 1
  return months > 0 ? months : null
}

export function buildTimeline(cv: ParsedCv | null, today: Date = new Date()): Timeline | null {
  if (!cv) return null
  const entries = cv.entries.filter((entry) => entry.kind !== 'project' || entry.start !== null)
  if (entries.length === 0) return null
  const hasBackendCounts = cv.entries.some((entry) => entry.months_counted !== undefined)

  let fallbackTotal = 0
  const rows: TimelineRow[] = entries.map((entry) => {
    const title = entry.title?.trim() || entry.organization?.trim() || 'Untitled entry'
    const organization = entry.title?.trim() ? (entry.organization?.trim() ?? null) : null
    const dates = formatRange(entry)
    if (entry.kind === 'education') {
      return { id: entry.id, title, organization, dates, counted: 'Education, not counted', countedMuted: true }
    }
    if (entry.kind === 'project') {
      return { id: entry.id, title, organization, dates, counted: 'Project, not counted', countedMuted: true }
    }
    const months = hasBackendCounts ? (entry.months_counted ?? null) : monthsBetween(entry, today)
    if (months === null) {
      return { id: entry.id, title, organization, dates, counted: 'Not counted: no clear dates', countedMuted: true }
    }
    fallbackTotal += months
    return { id: entry.id, title, organization, dates, counted: formatDuration(months), countedMuted: false }
  })

  let totalMonths: number | null = null
  if (typeof cv.total_months === 'number') totalMonths = cv.total_months
  else if (cv.total_years !== null) totalMonths = Math.round(cv.total_years * 12)
  else if (fallbackTotal > 0) totalMonths = fallbackTotal

  const total =
    totalMonths === null
      ? null
      : `${cv.total_is_minimum ? 'at least' : 'about'} ${formatDuration(totalMonths)}`
  return { rows, total, note: cv.dates_note ?? null }
}
