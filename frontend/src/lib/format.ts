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
