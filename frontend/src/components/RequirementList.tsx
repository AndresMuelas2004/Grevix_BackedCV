import { useState } from 'react'
import { updateInputs } from '../api/client'
import type {
  AnalysisReport,
  Contribution,
  InputsUpdate,
  JobPosting,
  PostingBanner,
  Requirement,
  RequirementAssessment,
  RequirementFlag,
  Status,
} from '../api/types'
import { describeError } from '../lib/errors'
import { formatPoints } from '../lib/format'
import {
  CATEGORY_LABELS,
  describeExclusion,
  FLAG_LABELS,
  IMPORTANCE_LABELS,
  KNOCKOUT_LABELS,
  MATCH_LABELS,
  STATUS_LABELS,
} from '../lib/labels'
import './RequirementList.css'

// What the row toggles need: the report's current lists, and where the saved report goes.
interface RequirementInputs {
  analysisId: string
  excludedIds: string[]
  includedFlaggedIds: string[]
  onChange: (next: AnalysisReport) => void
}

interface RequirementListProps {
  job: JobPosting | null
  assessments: Record<string, RequirementAssessment>
  banners: PostingBanner[]
  flags: RequirementFlag[]
  contributions: Contribution[]
  selectedId: string | null
  onSelect: (requirementId: string | null) => void
  // Turns on the "Not relevant to me" and "Count it anyway" toggles. Without it the list is read-only.
  inputs?: RequirementInputs
}

export default function RequirementList({
  job,
  assessments,
  banners,
  flags,
  contributions,
  selectedId,
  onSelect,
  inputs,
}: RequirementListProps) {
  const contributionById = new Map(contributions.map((item) => [item.requirement_id, item]))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Saves one list. Fields left out keep their value on the server, so only the changed list is sent.
  async function save(body: InputsUpdate) {
    if (!inputs) return
    setBusy(true)
    setError(null)
    try {
      inputs.onChange(await updateInputs(inputs.analysisId, body))
    } catch (failure) {
      setError(`Your change was not saved. ${describeError(failure)}`)
    } finally {
      setBusy(false)
    }
  }

  // While a save is running, a toggle is ignored (not disabled), so keyboard focus stays on it.
  function toggleExcluded(requirementId: string) {
    if (!inputs || busy) return
    const current = inputs.excludedIds
    const next = current.includes(requirementId)
      ? current.filter((id) => id !== requirementId)
      : [...current, requirementId]
    void save({ excluded_ids: next })
  }

  function toggleIncluded(requirementId: string) {
    if (!inputs || busy) return
    const current = inputs.includedFlaggedIds
    const next = current.includes(requirementId)
      ? current.filter((id) => id !== requirementId)
      : [...current, requirementId]
    void save({ included_flagged_ids: next })
  }

  return (
    <section className="requirements" aria-labelledby="requirements-title">
      <h2 id="requirements-title">Requirements</h2>

      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
      {busy && (
        <p className="req-saving" role="status">
          Saving...
        </p>
      )}

      {banners.length > 0 && (
        <ul className="banners" aria-label="Posting warnings">
          {banners.map((banner) => (
            <li key={`${banner.rule_id}-${banner.explanation}`} className="notice notice-warn">
              <strong>Posting warning.</strong> {banner.explanation}
            </li>
          ))}
        </ul>
      )}

      {job === null || job.requirements.length === 0 ? (
        <p className="notice notice-info">No requirements were found in this posting.</p>
      ) : (
        <ol className="req-list">
          {job.requirements.map((req) => {
            const rowFlags = flags.filter((flag) => flag.requirement_ids.includes(req.id))
            const toggles: RowToggles | undefined = inputs
              ? {
                  notRelevant: inputs.excludedIds.includes(req.id),
                  countAnyway:
                    rowFlags.length > 0 ? inputs.includedFlaggedIds.includes(req.id) : null,
                  busy,
                  onNotRelevant: () => toggleExcluded(req.id),
                  onCountAnyway: () => toggleIncluded(req.id),
                }
              : undefined
            return (
              <RequirementRow
                key={req.id}
                requirement={req}
                assessment={assessments[req.id] as RequirementAssessment | undefined}
                flags={rowFlags}
                contribution={contributionById.get(req.id)}
                selected={selectedId === req.id}
                onSelect={() => onSelect(selectedId === req.id ? null : req.id)}
                toggles={toggles}
              />
            )
          })}
        </ol>
      )}
    </section>
  )
}

interface RowToggles {
  notRelevant: boolean
  countAnyway: boolean | null // null when the requirement has no R1 or R2 flag
  busy: boolean
  onNotRelevant: () => void
  onCountAnyway: () => void
}

interface RequirementRowProps {
  requirement: Requirement
  assessment: RequirementAssessment | undefined
  flags: RequirementFlag[]
  contribution: Contribution | undefined
  selected: boolean
  onSelect: () => void
  toggles: RowToggles | undefined
}

function RequirementRow({
  requirement,
  assessment,
  flags,
  contribution,
  selected,
  onSelect,
  toggles,
}: RequirementRowProps) {
  const status: Status = assessment?.status ?? 'unknown'
  const evidence = assessment?.evidence ?? []
  const excludedReason = contribution?.excluded_reason ?? null

  return (
    <li className={selected ? 'req-row is-selected' : 'req-row'}>
      <button
        type="button"
        id={`req-${requirement.id}`}
        className="req-select"
        aria-pressed={selected}
        onClick={onSelect}
      >
        <span className="req-label">{requirement.label}</span>
        <span className={`chip chip-${status}`}>{STATUS_LABELS[status]}</span>
      </button>

      <div className="req-details">
        <div className="req-tags">
          <span className="chip chip-neutral">{IMPORTANCE_LABELS[requirement.importance]}</span>
          <span className="chip chip-neutral">{CATEGORY_LABELS[requirement.category]}</span>
          {requirement.knockout_type && (
            <span className="chip chip-knockout">
              Knockout: {KNOCKOUT_LABELS[requirement.knockout_type]}
            </span>
          )}
        </div>

        {contribution && <PointsLine contribution={contribution} />}

        {excludedReason !== null && <p className="req-note">{describeExclusion(excludedReason)}</p>}

        {toggles && (
          <div className="req-actions">
            <button
              type="button"
              className="req-toggle"
              aria-pressed={toggles.notRelevant}
              aria-disabled={toggles.busy}
              onClick={toggles.onNotRelevant}
            >
              Not relevant to me
            </button>
            {toggles.countAnyway !== null && (
              <button
                type="button"
                className="req-toggle"
                aria-pressed={toggles.countAnyway}
                aria-disabled={toggles.busy}
                onClick={toggles.onCountAnyway}
              >
                Count it anyway
              </button>
            )}
          </div>
        )}

        {flags.map((flag) => (
          <div key={`${flag.rule_id}-${flag.explanation}`} className="req-flag">
            <p className="req-flag-title">
              {FLAG_LABELS[flag.rule_id]} ({flag.rule_id})
            </p>
            <p>{flag.explanation}</p>
          </div>
        ))}

        {assessment?.rationale && <p className="req-rationale">{assessment.rationale}</p>}

        <details className="req-quote">
          <summary>Posting quote</summary>
          <blockquote>{requirement.quote}</blockquote>
          {!requirement.quote_located && (
            <p className="req-note">This quote was not found in the posting text.</p>
          )}
        </details>

        {evidence.length > 0 ? (
          <div className="req-evidence">
            <p className="req-evidence-title">Evidence in your CV</p>
            <ul>
              {evidence.map((item) => (
                <li key={`${item.ref}|${item.quote}`}>
                  <code className="line-id">{item.ref}</code> <q>{item.quote}</q>{' '}
                  <span className="match-type">({MATCH_LABELS[item.match_type]})</span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="req-note">No matching line in your CV.</p>
        )}
      </div>
    </li>
  )
}

// The points this requirement won out of its maximum, or that it is not counted.
function PointsLine({ contribution }: { contribution: Contribution }) {
  if (contribution.excluded_reason !== null) {
    return <p className="req-points">Points: none, not counted in Fit.</p>
  }
  const maximum = contribution.points_won + contribution.points_lost
  return (
    <p className="req-points">
      Points: {formatPoints(contribution.points_won)} of {formatPoints(maximum)}
    </p>
  )
}
