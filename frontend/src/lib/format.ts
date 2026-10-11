const numberFormat = new Intl.NumberFormat('en-US')

export function formatNumber(value: number): string {
  return numberFormat.format(value)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${formatNumber(Math.max(1, Math.round(bytes / 1024)))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Fit and keyword coverage, as whole points. Halves round up (38.5 becomes 39): Math.round does
// exactly that for the 0 to 100 scores here. The backend keeps one decimal, so every shown score
// goes through this, and a difference between two scores is taken after rounding both.
export function formatScore(value: number): string {
  return String(Math.round(value))
}

const pointFormat = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })

// Points for one requirement, at most one decimal (e.g. 12.5 or 25).
export function formatPoints(value: number): string {
  return pointFormat.format(value)
}

const usdFormat = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
})

// Model cost in US dollars, four decimals, as the backend rounds it (e.g. "$0.0042").
export function formatUsd(value: number): string {
  return usdFormat.format(value)
}
