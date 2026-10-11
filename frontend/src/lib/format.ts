const numberFormat = new Intl.NumberFormat('en-US')

export function formatNumber(value: number): string {
  return numberFormat.format(value)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${formatNumber(Math.max(1, Math.round(bytes / 1024)))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Scores are shown as whole points; the backend keeps one decimal.
export function formatScore(value: number): string {
  return String(Math.round(value))
}

const pointFormat = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })

// Points for one requirement, at most one decimal (e.g. 12.5 or 25).
export function formatPoints(value: number): string {
  return pointFormat.format(value)
}
