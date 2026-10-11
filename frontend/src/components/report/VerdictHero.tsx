import { useState } from 'react'
import { updateInputs } from '../../api/client'
import type { AnalysisReport } from '../../api/types'
import { describeError } from '../../lib/errors'
import { formatScore } from '../../lib/format'
import type { ReportQuestion } from '../../lib/questions'
import type { Saving } from '../../lib/saving'
import type { VerdictView } from '../../lib/verdictView'

export interface ActionState {
  blocked: boolean // likely screened out: improving the CV is not offered
  disabled: boolean
  hint: string
  blockReason: string | null
}

interface VerdictHeroProps {
  analysis: AnalysisReport
  view: VerdictView | null
  mustHaves: { met: number; total: number }
  questions: ReportQuestion[]
  action: ActionState
  saving: Saving
  onAnalysisChange: (next: AnalysisReport) => void
  onImprove: () => void
  onAnotherPosting: () => void
}

export default function VerdictHero({
  analysis,
  view,
  mustHaves,
  questions,
  action,
  saving,
  onAnalysisChange,
  onImprove,
  onAnotherPosting,
}: VerdictHeroProps) {
  const fit = analysis.score?.fit ?? null
  const percent = fit === null ? 0 : Math.min(100, Math.max(0, fit))

  return (
    <section className="rp-card rp-hero" aria-labelledby="verdict-title">
      <div className="rp-hero-top">
        <div className="rp-hero-main">
          {view && (
            <p className={`rp-verdict-chip tone-${view.tone}`} aria-live="polite">
              <AlertIcon />
              <span>{view.chip}</span>
            </p>
          )}
          <h1 id="verdict-title" className="rp-verdict-title" tabIndex={-1} data-screen-heading>
            {view ? view.title : 'Your report'}
          </h1>
          {view && <p className="rp-verdict-sub">{view.sub}</p>}
        </div>

        <div className="rp-score" role="group" aria-labelledby="score-label">
          <p className="rp-score-label" id="score-label">
            Skills match
          </p>
          <p className="rp-score-value">
            {fit === null ? (
              <span className="rp-score-none">Not scorable</span>
            ) : (
              <>
                <span className="rp-score-number">{formatScore(fit)}</span>
                <span className="rp-score-of">/ 100</span>
              </>
            )}
          </p>
          <div
            className="rp-bar"
            role="meter"
            aria-label="Skills match"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={fit === null ? undefined : Math.round(percent)}
            aria-valuetext={fit === null ? 'Not scorable' : `${formatScore(percent)} out of 100`}
          >
            <div className="rp-bar-fill" style={{ width: `${percent}%` }} />
          </div>
          {mustHaves.total > 0 && (
            <p className="rp-score-line">
              Your CV clearly shows{' '}
              <strong>
                {mustHaves.met} of {mustHaves.total} must-haves
              </strong>
              .
            </p>
          )}
          <p className="rp-score-note">
            Visa and office questions don't change this number. They decide the verdict.
          </p>
        </div>
      </div>

      {questions.length > 0 && (
        <Questions
          analysis={analysis}
          questions={questions}
          saving={saving}
          onAnalysisChange={onAnalysisChange}
        />
      )}

      <div className="rp-action">
        {action.blocked ? (
          <>
            <button type="button" className="rp-btn rp-btn-primary" onClick={onAnotherPosting}>
              Analyze another posting
            </button>
            <p className="rp-action-hint">{action.hint}</p>
          </>
        ) : (
          <>
            <button
              type="button"
              className="rp-btn rp-btn-primary"
              disabled={action.disabled}
              onClick={onImprove}
            >
              Improve my CV
            </button>
            <p className="rp-action-hint">{action.hint}</p>
          </>
        )}
      </div>
    </section>
  )
}

interface QuestionsProps {
  analysis: AnalysisReport
  questions: ReportQuestion[]
  saving: Saving
  onAnalysisChange: (next: AnalysisReport) => void
}

// Each answer is saved on the server, which recomputes the report and sends it back.
function Questions({ analysis, questions, saving, onAnalysisChange }: QuestionsProps) {
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // The server accepts answers only while the report is waiting for "optimize".
  const editable = analysis.stage === 'report_ready'
  const disabled = saving.busy || !editable

  async function answer(question: ReportQuestion, value: boolean) {
    setSavingKey(question.key)
    setError(null)
    // The answers map is replaced as a whole, so every answer is sent, not only the new one.
    const answers: Record<string, boolean> = { ...(analysis.facts.answers ?? {}) }
    for (const id of question.answerIds) answers[id] = value
    try {
      const next = await saving.track(() =>
        updateInputs(analysis.analysis_id, { facts: { ...analysis.facts, answers } }),
      )
      onAnalysisChange(next)
    } catch (failure) {
      setError(`Your answer was not saved. ${describeError(failure)}`)
    } finally {
      setSavingKey(null)
    }
  }

  // The buttons are aria-disabled rather than disabled, so they keep the keyboard focus while busy.
  const whenEnabled = (run: () => void) => () => {
    if (!disabled) run()
  }

  return (
    <div className="rp-questions">
      <div className="rp-questions-head">
        <h2 id="questions-title" className="rp-h3">
          Answer these first
        </h2>
        <p className="rp-muted">
          The verdict updates as soon as you answer. You can change an answer at any time.
        </p>
      </div>
      {!editable && (
        <p className="notice notice-info">Answers are locked now that the CV has been optimized.</p>
      )}
      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
      <p className="visually-hidden" role="status">
        {savingKey !== null ? 'Saving your answer...' : ''}
      </p>
      <ul className="rp-question-list" aria-labelledby="questions-title">
        {questions.map((question) => (
          <li key={question.key} className="rp-question">
            <fieldset className="rp-question-set">
              <legend className="rp-question-text">{question.text}</legend>
              <div className="rp-yesno">
                <button
                  type="button"
                  className={question.answer === true ? 'rp-choice is-on' : 'rp-choice'}
                  aria-pressed={question.answer === true}
                  aria-disabled={disabled}
                  onClick={whenEnabled(() => void answer(question, true))}
                >
                  Yes
                </button>
                <button
                  type="button"
                  className={question.answer === false ? 'rp-choice is-on' : 'rp-choice'}
                  aria-pressed={question.answer === false}
                  aria-disabled={disabled}
                  onClick={whenEnabled(() => void answer(question, false))}
                >
                  No
                </button>
              </div>
              {savingKey === question.key && (
                <span className="rp-saving" aria-hidden="true">
                  Saving...
                </span>
              )}
            </fieldset>
          </li>
        ))}
      </ul>
    </div>
  )
}

function AlertIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v6" />
      <path d="M12 17h.01" />
    </svg>
  )
}
