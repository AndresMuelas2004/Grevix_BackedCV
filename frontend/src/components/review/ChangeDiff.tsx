import { Fragment } from 'react'
import { diffWords, type Piece } from './wordDiff'
import './ChangeDiff.css'

interface ChangeDiffProps {
  before: string | null // null when the line is new
  after: string
  sectionTitle?: string // the section a new line goes into; used only when before is null
}

// Struck through in Before and underlined in After, so the change does not rely on colour alone.
export default function ChangeDiff({ before, after, sectionTitle }: ChangeDiffProps) {
  if (before === null) {
    return (
      <div className="change-diff">
        <p className="change-note">
          {sectionTitle ? `Adds a new line to ${sectionTitle}` : 'Adds a new line'}
        </p>
        <p>{after}</p>
      </div>
    )
  }

  const diff = diffWords(before, after)
  return (
    <dl className="change-diff">
      <div className="change-row">
        <dt>Before</dt>
        <dd>{renderPieces(diff.before, 'removed')}</dd>
      </div>
      <div className="change-row">
        <dt>After</dt>
        <dd>{renderPieces(diff.after, 'added')}</dd>
      </div>
    </dl>
  )
}

function renderPieces(pieces: Piece[], mark: 'removed' | 'added') {
  return pieces.map((piece, index) => {
    if (!piece.changed) return <span key={index}>{piece.text}</span>
    // The spaces at the edges stay outside the mark, so the highlight covers the words only.
    const lead = piece.text.match(/^\s*/)?.[0] ?? ''
    const core = piece.text.slice(lead.length).trimEnd()
    const trail = piece.text.slice(lead.length + core.length)
    return (
      <Fragment key={index}>
        {lead}
        {core !== '' && (mark === 'removed' ? <del>{core}</del> : <ins>{core}</ins>)}
        {trail}
      </Fragment>
    )
  })
}
