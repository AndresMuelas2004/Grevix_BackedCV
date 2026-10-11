import { Fragment } from 'react'
import { citationLabel, splitCitations } from '../lib/citations'
import './CitationTag.css'

interface CitationTagProps {
  id: string // a CV line ID (L039) or a computed fact ID (F01)
}

export default function CitationTag({ id }: CitationTagProps) {
  return <span className="cite-tag">{citationLabel(id)}</span>
}

interface CitedTextProps {
  text: string
}

// A sentence with IDs inside it (e.g. "line L012 does not show it"), shown with the same labels.
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
