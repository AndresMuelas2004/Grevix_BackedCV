// How CV lines and computed facts are named for the reader. The backend IDs (L039, F01) stay in
// the code; the screen shows "line 39" or "Computed from your dates" instead.

export const COMPUTED_FACT_LABEL = 'Computed from your dates'

export function isFactId(id: string): boolean {
  return /^F\d+$/.test(id)
}

// The number of a CV line ID: 39 for "L039". Null for anything else.
export function lineNumber(id: string): number | null {
  const match = /^L(\d+)$/.exec(id)
  return match ? Number(match[1]) : null
}

export function citationLabel(id: string): string {
  if (isFactId(id)) return COMPUTED_FACT_LABEL
  const number = lineNumber(id)
  return number === null ? 'Cited line' : `line ${number}`
}

export type TextPart = { kind: 'text'; text: string } | { kind: 'cite'; id: string }

// A line ID written inside a sentence, with an optional "line " word before it, so "Line L012"
// becomes one label, not "Line line 12".
const CITATION = /(?:\b[Ll]ine\s+)?\b(L\d{3}|F\d{2})\b/g

export function splitCitations(text: string): TextPart[] {
  const parts: TextPart[] = []
  let last = 0
  for (const match of text.matchAll(CITATION)) {
    const start = match.index
    if (start > last) parts.push({ kind: 'text', text: text.slice(last, start) })
    parts.push({ kind: 'cite', id: match[1] })
    last = start + match[0].length
  }
  if (last < text.length) parts.push({ kind: 'text', text: text.slice(last) })
  return parts
}
