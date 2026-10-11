import { useState } from 'react'
import { updateInputs } from '../../api/client'
import type { AnalysisReport, HiddenRisk, RiskLevel } from '../../api/types'
import { describeError } from '../../lib/errors'
import { BARRIER_KIND_LABELS, RISK_LEVEL_LABELS } from '../../lib/labels'
import type { Saving } from '../../lib/saving'
import './HiddenRisks.css'

interface HiddenRisksProps {
  analysis: AnalysisReport
  saving: Saving // the report screen's shared state: every answer is sent through it
  onAnalysisChange: (next: AnalysisReport) => void
}

const LEVEL_CHIP: Record<RiskLevel, string> = {
  high: 'chip-missing',
  medium: 'chip-partial',
  low: 'chip-neutral',
}

const LEVEL_ORDER: Record<RiskLevel, number> = { high: 0, medium: 1, low: 2 }

// The barriers in the posting that can get the candidate screened out without a word. A risk with
// a question is answered the same way as the knockout questions: through facts.answers.
export default function HiddenRisks({ analysis, saving, onAnalysisChange }: HiddenRisksProps) {
  const [error, setError] = useState<string | null>(null)
  const risks = orderRisks(analysis.hidden_risks ?? [])
  if (risks.length === 0) return null

  // The server accepts answers only while the report is waiting for "optimize".
  const editable = analysis.stage === 'report_ready'
  const disabled = saving.busy || !editable

  // The answers map is replaced as a whole, so every answer is sent, not only the new one.
  async function answer(risk: HiddenRisk, value: boolean) {
    setError(null)
    const answers = { ...(analysis.facts.answers ?? {}), [risk.id]: value }
    try {
      const next = await saving.track(() =>
        updateInputs(analysis.analysis_id, { facts: { ...analysis.facts, answers } }),
      )
      onAnalysisChange(next)
    } catch (failure) {
      setError(`Your answer was not saved. ${describeError(failure)}`)
    }
  }

  return (
    <section className="card hidden-risks" aria-labelledby="hidden-risks-title">
      <h2 id="hidden-risks-title">Hidden screening risks</h2>
      <p className="hidden-risks-intro">
        Parts of this posting that may get you screened out without a word. Where there is a
        question, your answer updates the verdict.
      </p>

      {!editable && (
        <p className="notice notice-info">Answers are locked now that the CV has been optimized.</p>
      )}
      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
      {saving.busy && (
        <p className="hidden-risks-saving" role="status">
          Saving your answer...
        </p>
      )}

      <ul className="risk-list">
        {risks.map((risk) => (
          <li key={risk.id}>
            <RiskCard
              risk={risk}
              disabled={disabled}
              onAnswer={(value) => void answer(risk, value)}
            />
          </li>
        ))}
      </ul>
    </section>
  )
}

// Composite risks first, then the open risks, then the answered ones. Each group runs high to low.
function orderRisks(risks: HiddenRisk[]): HiddenRisk[] {
  return [...risks].sort((a, b) => rank(a) - rank(b))
}

function rank(risk: HiddenRisk): number {
  const group = risk.kind === 'composite' ? 0 : risk.resolved ? 2 : 1
  return group * 3 + LEVEL_ORDER[risk.risk]
}

interface RiskCardProps {
  risk: HiddenRisk
  disabled: boolean
  onAnswer: (value: boolean) => void
}

function RiskCard({ risk, disabled, onAnswer }: RiskCardProps) {
  const titleId = `risk-${risk.id}-title`
  const note = risk.question === null ? followNote(risk) : null
  return (
    <article
      className={risk.resolved ? 'risk is-resolved' : 'risk'}
      data-level={risk.risk}
      aria-labelledby={titleId}
    >
      <div className="risk-head">
        <h3 id={titleId}>{BARRIER_KIND_LABELS[risk.kind]}</h3>
        <span className={`chip ${LEVEL_CHIP[risk.risk]}`}>{RISK_LEVEL_LABELS[risk.risk]}</span>
      </div>

      {risk.quote !== '' && (
        <div className="risk-quote">
          <p className="risk-label">From the posting</p>
          <blockquote>{risk.quote}</blockquote>
        </div>
      )}

      <p>
        <strong>Why it can screen you out.</strong> {risk.explanation}
      </p>
      {risk.action !== '' && (
        <p>
          <strong>What to do.</strong> {risk.action}
        </p>
      )}

      {risk.question !== null && (
        <RiskQuestion
          question={risk.question}
          answer={savedAnswer(risk)}
          disabled={disabled}
          onAnswer={onAnswer}
        />
      )}
      {note !== null && <p className="risk-note">{note}</p>}
    </article>
  )
}

// The candidate's saved answer to a risk's question: yes, no, or null while unanswered.
function savedAnswer(risk: HiddenRisk): boolean | null {
  if (risk.resolved) return true
  if (risk.confirmed) return false
  return null
}

// A risk without a question follows the requirement it is tied to, so say whether that one is met.
function followNote(risk: HiddenRisk): string | null {
  if (risk.resolved) return 'Resolved: the matching requirement is met.'
  if (risk.confirmed) return 'Confirmed: the matching requirement is missing.'
  return null
}

interface RiskQuestionProps {
  question: string
  answer: boolean | null
  disabled: boolean
  onAnswer: (value: boolean) => void
}

// Yes and No. Nothing is pressed until the candidate answers; then the saved answer stays pressed.
function RiskQuestion({ question, answer, disabled, onAnswer }: RiskQuestionProps) {
  // The buttons are aria-disabled rather than disabled, so they keep the keyboard focus while busy.
  const whenEnabled = (action: () => void) => () => {
    if (!disabled) action()
  }

  return (
    <fieldset className="risk-question">
      <legend>{question}</legend>
      <div className="knockout-actions">
        <button
          type="button"
          className={choiceClass(answer === true)}
          aria-pressed={answer === true}
          aria-disabled={disabled}
          onClick={whenEnabled(() => onAnswer(true))}
        >
          Yes
        </button>
        <button
          type="button"
          className={choiceClass(answer === false)}
          aria-pressed={answer === false}
          aria-disabled={disabled}
          onClick={whenEnabled(() => onAnswer(false))}
        >
          No
        </button>
      </div>
      {answer !== null && <p className="risk-answered">Answered: {answer ? 'yes' : 'no'}</p>}
    </fieldset>
  )
}

// The saved answer is the primary button; the other choice stays neutral.
function choiceClass(selected: boolean): string {
  return selected ? 'btn btn-primary' : 'btn btn-secondary'
}
