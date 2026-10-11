import { Fragment } from 'react'
import { citationLabel, splitCitations } from '../lib/citations'
import './CitationTag.css'

interface CitationTagProps {
  id: string // a CV line ID (L039) or a computed fact ID (F01)
}

// A small label that stands in for a cited CV line or computed fact.
export default function CitationTag({ id }: CitationTagProps) {
  return <span className="cite-tag">{citationLabel(id)}</span>
}

interface CitedTextProps {
  text: string
}

// A sentence with the IDs written inside it (for example "line L012 does not show it") shown with
// the same small labels.
export function CitedText({ text }: CitedTextProps) {
  return (
    <>
      {splitCitations(text).map((part, index) =>
        part.kind === 'text' ? (
          <Fragment key={index}>{part.text}</Fragment>
        ) : (
          <CitationTag key={index} id={part.id} />
        ),
      )}
    </>
  )
}
