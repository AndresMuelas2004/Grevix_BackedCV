import { Fragment } from 'react'
import { diffWords, type Piece } from './wordDiff'
import './ChangeDiff.css'

interface ChangeDiffProps {
  before: string | null // null when the line is new
  after: string
}

// Shows a change as a Before row and an After row. Changed words are struck through in Before
// and underlined in After, so the change is visible without relying on colour.
export default function ChangeDiff({ before, after }: ChangeDiffProps) {
  if (before === null) {
    return (
      <dl className="change-diff">
        <div className="change-row">
          <dt>Before</dt>
          <dd className="change-none">New line</dd>
        </div>
        <div className="change-row">
          <dt>After</dt>
          <dd>{after}</dd>
        </div>
      </dl>
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
