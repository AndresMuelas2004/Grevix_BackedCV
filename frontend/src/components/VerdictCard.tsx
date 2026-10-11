import type { JobPosting, RequirementAssessment, Verdict, VerdictLabel } from '../api/types'
import { BADGE_LABELS } from '../lib/labels'
import './VerdictCard.css'

interface VerdictCardProps {
  verdict: Verdict
  job: JobPosting | null
  assessments: Record<string, RequirementAssessment>
  // Set to false when the questions are answered in another block (KnockoutQuestions).
  showQuestions?: boolean
  // Turns the requirement IDs in the reasons into buttons that select the requirement.
  onSelectRequirement?: (requirementId: string) => void
}

const TONE: Record<VerdictLabel, 'good' | 'warn' | 'bad' | 'neutral'> = {
  apply: 'good',
  stretch: 'warn',
  answer_questions: 'warn',
  likely_screened_out: 'bad',
  long_shot: 'neutral',
}

const BADGE_CHIP: Record<keyof typeof BADGE_LABELS, string> = {
  tailor_first: 'chip-neutral',
  screening_risk: 'chip-missing',
  posting_red_flags: 'chip-partial',
}

export default function VerdictCard({
  verdict,
  job,
  assessments,
  showQuestions = true,
  onSelectRequirement,
}: VerdictCardProps) {
  const labelFor = (requirementId: string): string =>
    job?.requirements.find((req) => req.id === requirementId)?.label ?? requirementId

  // Knockout questions come from unknown requirements. The backend also repeats
  // each question as a verdict reason, so those reasons are hidden here.
  const questions = Object.values(assessments).flatMap((assessment) => {
    if (assessment.status !== 'unknown' || !assessment.question) return []
    return [
      {
        id: assessment.requirement_id,
        label: labelFor(assessment.requirement_id),
        question: assessment.question,
      },
    ]
  })
  const questionTexts = new Set(questions.map((item) => item.question))
  const reasons = verdict.reasons.filter((reason) => !questionTexts.has(reason.text))

  return (
    <section className="verdict card" data-tone={TONE[verdict.label]} aria-labelledby="verdict-title">
      <p className="eyebrow">Verdict</p>
      <h2 id="verdict-title" tabIndex={-1} data-screen-heading>
        {verdict.title}
      </h2>

      {reasons.length > 0 && (
        <ul className="reasons" aria-label="Why this verdict">
          {reasons.map((reason, index) => (
            <li key={`${index}-${reason.text}`}>
              {reason.text}
              {reason.requirement_ids.map((requirementId) => (
                <RequirementChip
                  key={requirementId}
                  requirementId={requirementId}
                  label={labelFor(requirementId)}
                  onSelect={onSelectRequirement}
                />
              ))}
            </li>
          ))}
        </ul>
      )}

      {verdict.badges.length > 0 && (
        <ul className="badges" aria-label="Flags for this job">
          {verdict.badges.map((badge) => (
            <li key={badge} className={`chip ${BADGE_CHIP[badge]}`}>
              {BADGE_LABELS[badge]}
            </li>
          ))}
        </ul>
      )}

      {verdict.provisional && (
        <p className="notice notice-info">
          Provisional. Answering the questions below could change this verdict.
        </p>
      )}

      {showQuestions && questions.length > 0 && (
        <div className="questions">
          <h3>Questions an employer may ask</h3>
          <ul>
            {questions.map((item) => (
              <li key={item.id}>
                <span className="req-tag">{item.label}:</span> {item.question}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

interface RequirementChipProps {
  requirementId: string
  label: string
  onSelect?: (requirementId: string) => void
}

// A requirement ID as a small chip. With a handler, the chip is a button that selects the requirement.
function RequirementChip({ requirementId, label, onSelect }: RequirementChipProps) {
  const name = (
    <>
      {requirementId}
      {label !== requirementId && <span className="visually-hidden">: {label}</span>}
    </>
  )
  if (!onSelect) return <span className="req-chip">{name}</span>
  return (
    <button
      type="button"
      className="req-chip req-chip-action"
      onClick={() => onSelect(requirementId)}
    >
      {name}
    </button>
  )
}
