import { useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import type { Suggestion, SuggestionKind, VerificationStatus } from '../../api/types'
import ChangeDiff from './ChangeDiff'
import './SuggestionCard.css'

export type Decision = 'accepted' | 'rejected'

interface SuggestionCardProps {
  suggestion: Suggestion
  // The choice that counts for the build. Undefined when not decided, or when the
  // suggestion is no longer verified (its acceptance is dropped).
  decision: Decision | undefined
  requirementLabels: ReadonlyMap<string, string>
  citations: ReadonlyMap<string, string> // CV line and fact IDs to their text
  onDecide: (decision: Decision) => void
  onSaveEdit: (text: string) => Promise<void>
}

const KIND_LABELS: Record<SuggestionKind, string> = {
  align_wording: 'Align wording',
  add_skill: 'Add skill',
  tailor_summary: 'Tailor summary',
}

const STATUS_CHIPS: Record<VerificationStatus, { label: string; chip: string }> = {
  verified: { label: 'Verified', chip: 'chip-met' },
  unsupported: { label: 'Unsupported', chip: 'chip-missing' },
  pending: { label: 'Not checked', chip: 'chip-unknown' },
}

export default function SuggestionCard({
  suggestion,
  decision,
  requirementLabels,
  citations,
  onDecide,
  onSaveEdit,
}: SuggestionCardProps) {
  const { id, verification } = suggestion
  const status = verification.status
  const acceptable = status === 'verified'
  const titleId = `suggestion-${id}-title`
  const editId = `suggestion-${id}-edit`
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(suggestion.after)
  const [saving, setSaving] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const editButton = useRef<HTMLButtonElement>(null)

  const covers = suggestion.covers_requirement_ids.map((req) => requirementLabels.get(req) ?? req)
  const failedClaims = verification.claims.filter((claim) => !claim.ok)
  const chip = STATUS_CHIPS[status]

  function startEdit() {
    setText(suggestion.after)
    setEditError(null)
    setEditing(true)
  }

  function cancelEdit() {
    setEditing(false)
    setEditError(null)
    editButton.current?.focus()
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = text.trim()
    if (next === '') {
      setEditError('Write the new text first.')
      return
    }
    setSaving(true)
    setEditError(null)
    try {
      await onSaveEdit(next)
      setEditing(false)
      editButton.current?.focus()
    } catch (error) {
      setEditError(describeError(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <article className="suggestion card" data-status={status} aria-labelledby={titleId}>
      <div className="suggestion-head">
        <h4 id={titleId}>{KIND_LABELS[suggestion.kind]}</h4>
        <span role="status">
          <span className={`chip ${chip.chip}`}>{chip.label}</span>
        </span>
        {decision && (
          <span className={`chip ${decision === 'accepted' ? 'chip-met' : 'chip-neutral'}`}>
            {decision === 'accepted' ? 'Accepted' : 'Rejected'}
          </span>
        )}
        {suggestion.edited_by_user && <span className="chip chip-neutral">Edited by you</span>}
      </div>

      <ChangeDiff before={suggestion.before} after={suggestion.after} />

      <p className="suggestion-meta">
        <span className="suggestion-label">Covers:</span>{' '}
        {covers.length > 0 ? covers.join(', ') : 'none'}
      </p>

      {suggestion.cited_refs.length > 0 && (
        <div className="cited">
          <p className="suggestion-label">Based on your CV</p>
          <ul className="cited-list">
            {suggestion.cited_refs.map((ref) => (
              <li key={ref}>
                <code className="cite-id">{ref}</code>
                <span>{citations.get(ref) ?? 'Not found in your CV.'}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!acceptable && (
        <div className="reason-box">
          <p>
            <strong>{status === 'pending' ? 'Not checked yet.' : 'Not supported by your CV.'}</strong>
            {status !== 'pending' && ` ${verification.reason ?? 'The check did not pass.'}`}
          </p>
          {failedClaims.length > 0 && (
            <ul>
              {failedClaims.map((claim, index) => (
                <li key={index}>
                  {claim.text}
                  {claim.reason && `: ${claim.reason}`}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!acceptable && <p className="suggestion-note">Cannot be accepted until your CV supports it.</p>}

      <div className="suggestion-actions">
        {acceptable && (
          <button
            type="button"
            className="btn btn-secondary decision decision-accept"
            aria-pressed={decision === 'accepted'}
            onClick={() => onDecide('accepted')}
          >
            Accept
          </button>
        )}
        <button
          type="button"
          className="btn btn-secondary decision decision-reject"
          aria-pressed={decision === 'rejected'}
          onClick={() => onDecide('rejected')}
        >
          Reject
        </button>
        <button ref={editButton} type="button" className="btn btn-secondary" onClick={startEdit}>
          Edit
        </button>
      </div>

      {editing && (
        <form className="edit-form" onSubmit={save} noValidate aria-label="Edit this suggestion">
          <label htmlFor={editId} className="field-label">
            New text
          </label>
          <textarea
            id={editId}
            rows={3}
            value={text}
            autoFocus
            onChange={(event) => setText(event.target.value)}
            aria-invalid={editError !== null}
            aria-describedby={editError ? `${editId}-error` : undefined}
          />
          {editError && (
            <p id={`${editId}-error`} className="field-error" role="alert">
              {editError}
            </p>
          )}
          <div className="suggestion-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Checking...' : 'Save and check'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={cancelEdit} disabled={saving}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </article>
  )
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail ? `${error.title} ${error.detail}` : error.title
  }
  return 'The text could not be checked.'
}
