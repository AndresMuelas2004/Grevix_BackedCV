import { useState } from 'react'
import type { AnalysisReport, RequirementAssessment } from '../../api/types'
import { formatPoints, formatScore } from '../../lib/format'
import { FLAG_LABELS, IMPORTANCE_LABELS, STATUS_LABELS } from '../../lib/labels'
import { problemLineIds } from '../../lib/parseWarnings'
import { plainText } from '../../lib/plainText'
import { buildPriorities } from '../../lib/priorities'
import { reportQuestions, unansweredCount } from '../../lib/questions'
import { useSaving } from '../../lib/saving'
import { buildTimeline } from '../../lib/timeline'
import { blockReasonOf, mustHaveCount, strengths, verdictView } from '../../lib/verdictView'
import CvView from '../CVView'
import HowComputed from '../HowComputed'
import ParseReport from '../parse/ParseReport'
import RequirementList from '../RequirementList'
import FixList from './FixList'
import VerdictHero, { type ActionState } from './VerdictHero'
import './ReportView.css'

interface ReportViewProps {
  analysis: AnalysisReport
  onAnalysisChange: (next: AnalysisReport) => void
  onImprove: () => void // starts "optimize": suggested edits backed by the CV
  onAnotherPosting: () => void // back to the form with the CV kept
}

// The report page, simple to complex: the verdict and the one number, the questions to answer,
// the main action, what to fix in order, what already works, how the dates were read, and the
// details for whoever wants them.
export default function ReportView({
  analysis,
  onAnalysisChange,
  onImprove,
  onAnotherPosting,
}: ReportViewProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [highlightedLineIds, setHighlightedLineIds] = useState<string[]>([])
  // The answers and the toggles of this screen share one saving state: one request at a time.
  const saving = useSaving()

  const questions = reportQuestions(analysis)
  const pending = unansweredCount(questions)
  const priorities = buildPriorities(analysis)
  const answeredNo = questions.some((question) => question.answer === false)
  // Why the role is out of reach: the first firm rule answered No, else the first thing that could
  // rule the candidate out, else the verdict's own reason.
  const ruleOut = priorities.filter((item) => item.tier === 'rule_out')
  const blocker = ruleOut.find((item) => item.answeredNo) ?? ruleOut[0]
  const blockReason =
    analysis.verdict?.label !== 'likely_screened_out'
      ? null
      : (blocker?.why ??
        blockReasonOf(
          analysis,
          questions.map((question) => question.text),
        ))
  const view = verdictView(analysis, pending, answeredNo, blockReason)
  const action = actionState(analysis, pending, blockReason, saving.busy)

  const selected: RequirementAssessment | undefined =
    selectedId === null ? undefined : analysis.assessments[selectedId]
  const evidenceIds = selected ? selected.evidence.map((item) => item.ref) : []

  function selectRequirement(requirementId: string | null) {
    setSelectedId(requirementId)
    setHighlightedLineIds([])
  }

  function highlightLines(lineIds: string[]) {
    setHighlightedLineIds(lineIds)
    setSelectedId(null)
  }

  return (
    <div className="rp">
      {analysis.errors.length > 0 && (
        <p className="notice notice-warn" role="status">
          Some steps did not finish, so parts of this report may be incomplete.
        </p>
      )}

      <VerdictHero
        analysis={analysis}
        view={view}
        mustHaves={mustHaveCount(analysis)}
        questions={questions}
        action={action}
        saving={saving}
        onAnalysisChange={onAnalysisChange}
        onImprove={onImprove}
        onAnotherPosting={onAnotherPosting}
      />

      <FixList items={priorities} />

      <Strengths analysis={analysis} />

      <Dates analysis={analysis} />

      <section className="rp-details" aria-labelledby="details-title">
        <h2 id="details-title" className="rp-h2-sm">
          Details, if you want them
        </h2>

        <details className="rp-fold">
          <summary>
            <span>All {analysis.job?.requirements.length ?? 0} requirements, one by one</span>
            <span className="rp-fold-hint">Show</span>
          </summary>
          <div className="rp-fold-body">
            <RequirementList
              job={analysis.job}
              assessments={analysis.assessments}
              banners={analysis.banners}
              flags={analysis.flags}
              screeningFlags={analysis.screening_flags ?? []}
              recency={analysis.recency ?? {}}
              contributions={analysis.score?.contributions ?? []}
              selectedId={selectedId}
              onSelect={selectRequirement}
              inputs={{
                analysisId: analysis.analysis_id,
                excludedIds: analysis.excluded_ids,
                includedFlaggedIds: analysis.included_flagged_ids,
                saving,
                onChange: onAnalysisChange,
              }}
            />
          </div>
        </details>

        <details className="rp-fold">
          <summary>
            <span>
              Exact-word match:{' '}
              {analysis.score?.coverage === null || analysis.score?.coverage === undefined
                ? 'not scorable'
                : `${formatScore(analysis.score.coverage)}%`}
            </span>
            <span className="rp-fold-hint">What is this?</span>
          </summary>
          <div className="rp-fold-body">
            <p>
              How many of the posting's exact skill words appear in your CV
              {analysis.score && analysis.score.coverage_denominator > 0
                ? ` (${analysis.score.coverage_numerator} of ${analysis.score.coverage_denominator})`
                : ''}
              . Some screening software searches for exact words, so a low number means you describe
              the right things with different words. It is not your skills match.
            </p>
          </div>
        </details>

        <details className="rp-fold">
          <summary>
            <span>How the skills match is worked out</span>
            <span className="rp-fold-hint">Show</span>
          </summary>
          <div className="rp-fold-body">
            <ScoreWorking analysis={analysis} />
            <HowComputed usage={analysis.usage} />
          </div>
        </details>

        <details className="rp-fold">
          <summary>
            <span>Your CV as screening software reads it</span>
            <span className="rp-fold-hint">Show</span>
          </summary>
          <div className="rp-fold-body rp-cv-grid">
            <ParseReport
              warnings={analysis.parse_warnings}
              lines={analysis.cv?.lines ?? []}
              highlightedLineIds={highlightedLineIds}
              onHighlight={highlightLines}
            />
            <CvView
              cv={analysis.cv}
              meta={analysis.cv_meta}
              selectedId={selectedId}
              highlightIds={evidenceIds}
              noteIds={highlightedLineIds}
              warnedIds={problemLineIds(analysis.parse_warnings)}
            />
          </div>
        </details>

        <PostingNotes analysis={analysis} />
      </section>

      <ClosingBand
        action={action}
        pending={pending}
        onImprove={onImprove}
        onAnotherPosting={onAnotherPosting}
      />
    </div>
  )
}

// The main action's state, shared by the button under the questions and the closing band.
function actionState(
  analysis: AnalysisReport,
  pending: number,
  blockReason: string | null,
  busy: boolean,
): ActionState {
  if (analysis.verdict?.label === 'likely_screened_out') {
    return {
      blocked: true,
      disabled: false,
      hint: `Not worth tailoring: this role is out of reach.${blockReason ? ` ${blockReason}` : ''}`,
      blockReason,
    }
  }
  if (pending > 0) {
    return {
      blocked: false,
      disabled: true,
      hint: `Answer the ${pending === 1 ? 'question' : `${pending} questions`} first.`,
      blockReason,
    }
  }
  return {
    blocked: false,
    disabled: analysis.stage !== 'report_ready' || busy,
    hint: 'Edits only where your CV already proves it. Each one is checked against your CV.',
    blockReason,
  }
}

function Strengths({ analysis }: { analysis: AnalysisReport }) {
  const items = strengths(analysis)
  if (items.length === 0) return null
  return (
    <section className="rp-card rp-strong" aria-labelledby="strong-title">
      <div className="rp-strong-head">
        <CheckIcon />
        <h2 id="strong-title" className="rp-h2-sm">
          Already strong: keep these
        </h2>
        <p className="rp-muted">
          {items.length} {items.length === 1 ? 'requirement' : 'requirements'} your CV clearly backs
        </p>
      </div>
      <ul className="rp-chips">
        {items.map((item) => (
          <li key={item.id} className="rp-chip-good">
            {item.label}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Dates({ analysis }: { analysis: AnalysisReport }) {
  const timeline = buildTimeline(analysis.cv)
  return (
    <section className="rp-card rp-dates" aria-labelledby="dates-title">
      <div>
        <h2 id="dates-title" className="rp-h2-sm">
          How we read your dates
        </h2>
        <p className="rp-muted">
          Years of experience and "too old" checks come from these dates. PDFs with two columns can
          mix them up, so check them.
        </p>
      </div>
      {timeline === null ? (
        <p>We found no dated jobs in your CV.</p>
      ) : (
        <>
          <div className="rp-table-wrap">
            <table className="rp-table">
              <thead>
                <tr>
                  <th scope="col">Entry</th>
                  <th scope="col">Dates as read</th>
                  <th scope="col">Counted</th>
                </tr>
              </thead>
              <tbody>
                {timeline.rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <strong>{row.title}</strong>
                      {row.organization && (
                        <>
                          <br />
                          <span className="rp-muted">{row.organization}</span>
                        </>
                      )}
                    </td>
                    <td>{row.dates}</td>
                    <td className={row.countedMuted ? 'rp-muted' : undefined}>{row.counted}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="rp-dates-foot">
            {timeline.total && (
              <p>
                <strong>Total work experience: {timeline.total}.</strong>
              </p>
            )}
            <p className="rp-muted">
              {timeline.note ? `${timeline.note} ` : ''}If a month is missing we write "month
              unknown". We never guess it.
            </p>
          </div>
        </>
      )}
    </section>
  )
}

// The points behind the skills match, one row per scored requirement.
function ScoreWorking({ analysis }: { analysis: AnalysisReport }) {
  const score = analysis.score
  if (!score) return <p>No skills match was computed for this posting.</p>
  const labels = new Map((analysis.job?.requirements ?? []).map((req) => [req.id, req.label]))
  const rows = score.contributions.filter((item) => item.excluded_reason === null)
  const pendingPoints = Math.round(score.pending_points)
  return (
    <div className="rp-working">
      <p>
        Each requirement is worth points, and must-haves weigh more than nice-to-haves. Visa and
        office questions never add points: they decide the verdict.
      </p>
      {score.summary && <p>{plainText(score.summary, labels)}</p>}
      {pendingPoints > 0 && (
        <p>
          {pendingPoints} {pendingPoints === 1 ? 'point depends' : 'points depend'} on things your
          CV doesn't confirm yet.
        </p>
      )}
      {rows.length > 0 && (
        <div className="rp-table-wrap">
          <table className="rp-table">
            <thead>
              <tr>
                <th scope="col">Requirement</th>
                <th scope="col">Status</th>
                <th scope="col">Points</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.requirement_id}>
                  <td>
                    {labels.get(item.requirement_id) ?? item.label}
                    <br />
                    <span className="rp-muted">{IMPORTANCE_LABELS[item.importance]}</span>
                  </td>
                  <td>{STATUS_LABELS[item.status]}</td>
                  <td>
                    {formatPoints(item.points_won)} of {formatPoints(item.points_won + item.points_lost)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// Notes about the posting itself (R3/R4 banners and R1/R2 flags), when there are any.
function PostingNotes({ analysis }: { analysis: AnalysisReport }) {
  const labels = new Map((analysis.job?.requirements ?? []).map((req) => [req.id, req.label]))
  const notes = [
    ...analysis.banners.map((banner) => plainText(banner.explanation, labels)),
    ...analysis.flags.map((flag) => {
      const names = flag.requirement_ids
        .map((id) => labels.get(id))
        .filter((name) => name !== undefined)
        .join(', ')
      const text = plainText(flag.explanation, labels)
      return `${FLAG_LABELS[flag.rule_id]}${names ? ` (${names})` : ''}: ${text}`
    }),
  ].filter((text) => text !== '')
  if (notes.length === 0) return null
  return (
    <details className="rp-fold">
      <summary>
        <span>About this posting</span>
        <span className="rp-fold-hint">
          {notes.length} {notes.length === 1 ? 'note' : 'notes'}
        </span>
      </summary>
      <div className="rp-fold-body">
        <ul className="rp-notes">
          {notes.map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      </div>
    </details>
  )
}

interface ClosingBandProps {
  action: ActionState
  pending: number
  onImprove: () => void
  onAnotherPosting: () => void
}

// The dark band at the foot of the page: the same action as under the questions.
function ClosingBand({ action, pending, onImprove, onAnotherPosting }: ClosingBandProps) {
  if (action.blocked) {
    return (
      <section className="rp-band" aria-labelledby="band-title">
        <div className="rp-band-text">
          <h2 id="band-title">Try a role that fits your situation</h2>
          <p>Paste another posting. Your CV stays loaded.</p>
        </div>
        <button type="button" className="rp-btn rp-btn-light" onClick={onAnotherPosting}>
          Analyze another posting
        </button>
      </section>
    )
  }
  return (
    <section className="rp-band" aria-labelledby="band-title">
      <div className="rp-band-text">
        <h2 id="band-title">Next: improve your CV for this job</h2>
        <p>
          {pending > 0
            ? action.hint
            : 'We suggest rewrites backed by your own lines, and we tell you when we refuse to stretch one.'}
        </p>
      </div>
      <button
        type="button"
        className="rp-btn rp-btn-light"
        disabled={action.disabled}
        onClick={onImprove}
      >
        Improve my CV
      </button>
    </section>
  )
}

function CheckIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="#067647"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12.5l2.5 2.5L16 9.5" />
    </svg>
  )
}
