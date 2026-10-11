export interface Piece {
  text: string
  changed: boolean
}

export interface WordDiff {
  before: Piece[]
  after: Piece[]
}

// Above this many word pairs the table gets too big, so the whole text counts as changed.
const MAX_CELLS = 250_000

// Punctuation at the end of a word ("Python," or "PostgreSQL.") does not make it another word.
const TRAILING_PUNCTUATION = /[.,;:!?)\]"'”’»…]+$/

// Splits text into tokens: each word with the spaces before it, and any spaces at the end.
// Joining the tokens gives the text back. Spaces are not tokens of their own, so a run of
// spaces cannot line up with a word of the other version.
function tokenize(text: string): string[] {
  return text.match(/\s*\S+|\s+/g) ?? []
}

function matchKey(token: string): string {
  const word = token.trimStart()
  if (word === '') return token
  const bare = word.replace(TRAILING_PUNCTUATION, '')
  return bare === '' ? word : bare
}

function push(pieces: Piece[], text: string, changed: boolean): void {
  const last = pieces.at(-1)
  if (last && last.changed === changed) last.text += text
  else pieces.push({ text, changed })
}

export function diffWords(before: string, after: string): WordDiff {
  const a = tokenize(before)
  const b = tokenize(after)
  if (a.length * b.length > MAX_CELLS) {
    return {
      before: [{ text: before, changed: true }],
      after: [{ text: after, changed: true }],
    }
  }
  const keysA = a.map(matchKey)
  const keysB = b.map(matchKey)

  // table[i * width + j] is the length of the longest common sequence of a[i..] and b[j..].
  const n = a.length
  const m = b.length
  const width = m + 1
  const table = new Uint32Array((n + 1) * width)
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      table[i * width + j] =
        keysA[i] === keysB[j]
          ? table[(i + 1) * width + j + 1] + 1
          : Math.max(table[(i + 1) * width + j], table[i * width + j + 1])
    }
  }

  const beforePieces: Piece[] = []
  const afterPieces: Piece[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (keysA[i] === keysB[j]) {
      push(beforePieces, a[i], false)
      push(afterPieces, b[j], false)
      i++
      j++
    } else if (table[(i + 1) * width + j] >= table[i * width + j + 1]) {
      push(beforePieces, a[i], true)
      i++
    } else {
      push(afterPieces, b[j], true)
      j++
    }
  }
  for (; i < n; i++) push(beforePieces, a[i], true)
  for (; j < m; j++) push(afterPieces, b[j], true)

  return { before: beforePieces, after: afterPieces }
}
