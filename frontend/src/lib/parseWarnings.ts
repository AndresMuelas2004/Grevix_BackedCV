import type { ParseWarning } from '../api/types'

// Recruiter tips are the parse warnings whose codes start with "tip_". Everything else is a parse problem.
export function isTip(warning: ParseWarning): boolean {
  return warning.code.startsWith('tip_')
}

export interface ParseReading {
  // Parse problems: errors and warnings first, then info. The backend order is kept inside each group.
  problems: ParseWarning[]
  tips: ParseWarning[]
}

const SEVERITY_RANK: Record<ParseWarning['severity'], number> = { error: 0, warning: 1, info: 2 }

export function splitParseWarnings(warnings: ParseWarning[]): ParseReading {
  const problems = warnings
    .filter((warning) => !isTip(warning))
    .sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])
  return { problems, tips: warnings.filter(isTip) }
}

// Line IDs that a parse problem points at (tips excluded). The CV view marks these lines.
export function problemLineIds(warnings: ParseWarning[]): string[] {
  const ids = warnings.filter((warning) => !isTip(warning)).flatMap((warning) => warning.line_ids)
  return [...new Set(ids)]
}
