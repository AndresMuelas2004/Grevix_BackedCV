import { useEffect, useRef, useState } from 'react'
import { updateInputs } from '../../api/client'
import type { AnalysisReport } from '../../api/types'
import { describeError } from '../../lib/errors'
import { knockoutItems, type KnockoutItem } from '../../lib/knockouts'
import type { Saving } from '../../lib/saving'
import './KnockoutQuestions.css'

interface KnockoutQuestionsProps {
  analysis: AnalysisReport
  saving: Saving // the report screen's shared state: every answer is sent through it
  onAnalysisChange: (next: AnalysisReport) => void
}

// Yes/No answers to the screening questions the employer may ask. Each answer is saved
// on the server, which recomputes the report; the new report comes back through onAnalysisChange.
export default function KnockoutQuestions({
  analysis,
  saving,
  onAnalysisChange,
}: KnockoutQuestionsProps) {
  const [savingId, setSavingId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [answeredId, setAnsweredId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const items = knockoutItems(analysis)
  if (items.length === 0) return null

  // The server accepts answers only while the report is waiting for "optimize".
  const editable = analysis.stage === 'report_ready'

  async function answer(item: KnockoutItem, value: boolean) {
    setSavingId(item.requirementId)
    setError(null)
    // The answers map is replaced as a whole, so every answer is sent, not only the new one.
    const answers = { ...(analysis.facts.answers ?? {}), [item.requirementId]: value }
    try {
      const next = await saving.track(() =>
        updateInputs(analysis.analysis_id, { facts: { ...analysis.facts, answers } }),
      )
      setEditingId(null)
      setAnsweredId(item.requirementId)
      onAnalysisChange(next)
    } catch (failure) {
      setError(`Your answer was not saved. ${describeError(failure)}`)
    } finally {
      setSavingId(null)
    }
  }

  return (
    <section className="knockouts card" aria-labelledby="knockouts-title">
      <h2 id="knockouts-title">Questions an employer may ask</h2>
      <p className="knockouts-intro">
        Answer each one. Your answers update the verdict; deal-breakers are yes or no, so they
        never add points to the score.
      </p>

      {!editable && (
        <p className="notice notice-info">Answers are locked now that the CV has been optimized.</p>
      )}
      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
      {savingId !== null && (
        <p className="knockouts-saving" role="status">
          Saving your answer...
        </p>
      )}

      {/* After an answer, the Yes/No buttons are replaced, so focus moves to "Change answer". */}
      <ul className="knockout-list">
        {items.map((item) => (
          <KnockoutRow
            key={item.requirementId}
            item={item}
            disabled={saving.busy || !editable}
            editing={editingId === item.requirementId}
            focusChange={answeredId === item.requirementId}
            onAnswer={(value) => void answer(item, value)}
            onStartEdit={() => setEditingId(item.requirementId)}
            onCancelEdit={() => setEditingId(null)}
          />
        ))}
      </ul>
    </section>
  )
}

interface KnockoutRowProps {
  item: KnockoutItem
  disabled: boolean
  editing: boolean
  focusChange: boolean
  onAnswer: (value: boolean) => void
  onStartEdit: () => void
  onCancelEdit: () => void
}

function KnockoutRow({
  item,
  disabled,
  editing,
  focusChange,
  onAnswer,
  onStartEdit,
  onCancelEdit,
}: KnockoutRowProps) {
  const answered = item.answer !== null
  const showChoices = !answered || editing
  const yesButton = useRef<HTMLButtonElement>(null)
  const changeButton = useRef<HTMLButtonElement>(null)
  const wasEditing = useRef(editing)

  // Editing swaps the buttons. Focus follows the user: into Yes when the edit opens, back to
  // "Change answer" when it closes, so it never falls back to the top of the page.
  useEffect(() => {
    if (wasEditing.current === editing) return
    wasEditing.current = editing
    if (editing) yesButton.current?.focus()
    else changeButton.current?.focus()
  }, [editing])

  // The buttons are aria-disabled rather than disabled: a disabled button would drop the focus.
  const whenEnabled = (action: () => void) => () => {
    if (!disabled) action()
  }

  return (
    <li className="knockout-item">
      <fieldset className="knockout-fieldset">
        <legend className="knockout-question">{item.question}</legend>
        <p className="knockout-requirement">Requirement: {item.label}</p>

        {showChoices ? (
          <div className="knockout-actions">
            {/* Only the saved answer is selected: an unanswered question shows two neutral choices. */}
            <button
              ref={yesButton}
              type="button"
              className={choiceClass(item.answer === true)}
              aria-pressed={item.answer === true}
              aria-disabled={disabled}
              onClick={whenEnabled(() => onAnswer(true))}
            >
              Yes
            </button>
            <button
              type="button"
              className={choiceClass(item.answer === false)}
              aria-pressed={item.answer === false}
              aria-disabled={disabled}
              onClick={whenEnabled(() => onAnswer(false))}
            >
              No
            </button>
            {answered && (
              <button
                type="button"
                className="btn btn-secondary"
                aria-disabled={disabled}
                onClick={whenEnabled(onCancelEdit)}
              >
                Cancel
              </button>
            )}
          </div>
        ) : (
          <div className="knockout-actions">
            <p className="knockout-answer">
              Your answer: <strong>{item.answer ? 'Yes' : 'No'}</strong>
            </p>
            <button
              ref={changeButton}
              type="button"
              className="btn btn-secondary"
              aria-disabled={disabled}
              autoFocus={focusChange}
              onClick={whenEnabled(onStartEdit)}
            >
              Change answer
            </button>
          </div>
        )}
      </fieldset>
    </li>
  )
}

// The saved answer is the primary button; the other choice stays neutral.
function choiceClass(selected: boolean): string {
  return selected ? 'btn btn-primary' : 'btn btn-secondary'
}
