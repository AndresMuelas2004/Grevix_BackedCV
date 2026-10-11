// Plain text for the report: no raw IDs (R17, H02, L014, F01) and sentences joined with proper
// spacing and punctuation.

const ID_PATTERN = String.raw`(?:R\d{2,3}|HC\d+|H\d{2,3}|L\d{3}|F\d{2}|S\d{2}|E\d{2})`

// "(R17)", "(R17, R18)", "(L014 and L015)": a list of IDs in brackets, dropped whole.
const ID_LIST = new RegExp(String.raw`\s*\(\s*${ID_PATTERN}(?:\s*(?:,|;|/|and)\s*${ID_PATTERN})*\s*\)`, 'g')
// A line ID with an optional "line" before it, so "line L012" becomes "line 12".
const LINE_ID = /\b(?:[Ll]ine\s+)?L0*(\d{1,3})\b/g
const FACT_ID = /\bF\d{2}\b/g
const OTHER_ID = new RegExp(String.raw`\b${ID_PATTERN}\b`, 'g')

// The text without raw IDs. Requirement IDs become their label when one is given.
export function plainText(text: string, labels?: ReadonlyMap<string, string>): string {
  let out = text.replace(ID_LIST, '')
  out = out.replace(LINE_ID, (_match, number: string) => `line ${Number(number)}`)
  out = out.replace(FACT_ID, 'your dates')
  out = out.replace(OTHER_ID, (id) => labels?.get(id) ?? '')
  // Sentences glued together: "application.US work" becomes "application. US work".
  out = out.replace(/([a-z]{2,}[.!?])([A-Z])/g, '$1 $2')
  // Tidy what removed IDs leave behind.
  out = out
    .replace(/\(\s*\)/g, '')
    .replace(/\s+([,.;:!?])/g, '$1')
    .replace(/,\s*([.!?])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim()
  return out
}

const RULE_ID_PATTERN = String.raw`(?:R\d{2,3}|HC\d+|H\d{2,3}|S\d{2}|E\d{2})`
const RULE_ID_LIST = new RegExp(
  String.raw`\s*\(\s*${RULE_ID_PATTERN}(?:\s*(?:,|;|/|and)\s*${RULE_ID_PATTERN})*\s*\)`,
  'g',
)
const RULE_ID = new RegExp(String.raw`\b${RULE_ID_PATTERN}\b`, 'g')

// The text without requirement, risk and suggestion IDs, keeping line and fact IDs (L012, F01)
// for the citation tags. Sentences glued together get their space back.
export function dropRuleIds(text: string): string {
  return text
    .replace(RULE_ID_LIST, '')
    .replace(RULE_ID, '')
    .replace(/([a-z]{2,}[.!?])([A-Z])/g, '$1 $2')
    .replace(/\s+([,.;:!?])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

export function firstSentence(text: string): string {
  const clean = text.trim()
  if (clean === '') return ''
  const match = /^(.+?[.!?])(?:\s+(?=["'(A-Z0-9])|$)/.exec(clean)
  return ensurePeriod(match ? match[1] : clean)
}

export function ensurePeriod(text: string): string {
  const clean = text.trim()
  if (clean === '') return ''
  return /[.!?:]$/.test(clean) ? clean : `${clean}.`
}

export function joinSentences(...parts: (string | null | undefined)[]): string {
  return parts
    .map((part) => (part ? ensurePeriod(part) : ''))
    .filter((part) => part !== '')
    .join(' ')
}

// A question's text reduced to letters and digits, to spot the same question asked twice.
export function normalizeQuestion(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

// "1 thing", "2 things".
export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}
