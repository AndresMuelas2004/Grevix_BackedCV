// Word-level diff between two versions of a CV line, used to show what a suggestion changed.

export interface Piece {
  text: string
  changed: boolean
}

export interface WordDiff {
  before: Piece[] // the old text, with the words that were removed marked
  after: Piece[] // the new text, with the words that were added marked
}

// Above this many word pairs the table gets too big, so the whole text counts as changed.
const MAX_CELLS = 250_000

// Splits text into words and runs of spaces, so joining the tokens gives the text back.
function tokenize(text: string): string[] {
  return text.match(/\s+|\S+/g) ?? []
}

// Adds a token to the pieces, merging it into the last piece when the mark is the same.
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

  // table[i * width + j] is the length of the longest common sequence of a[i..] and b[j..].
  const n = a.length
  const m = b.length
  const width = m + 1
  const table = new Uint32Array((n + 1) * width)
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      table[i * width + j] =
        a[i] === b[j]
          ? table[(i + 1) * width + j + 1] + 1
          : Math.max(table[(i + 1) * width + j], table[i * width + j + 1])
    }
  }

  const beforePieces: Piece[] = []
  const afterPieces: Piece[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) {
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
