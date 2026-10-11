import { useState } from 'react'
import { updateInputs } from '../api/client'
import type {
  AnalysisReport,
  Contribution,
  InputsUpdate,
  JobPosting,
  PostingBanner,
  RecencyCheck,
  Requirement,
  RequirementAssessment,
  RequirementFlag,
  ScreeningFlag,
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
import { plainText as cleanText, dropRuleIds } from '../lib/plainText'
import type { Saving } from '../lib/saving'
import CitationTag, { CitedText } from './CitationTag'
import './RequirementList.css'

// What the row toggles need: the report's current lists, where the saved report goes, and the
// report screen's shared state that every save goes through.
interface RequirementInputs {
  analysisId: string
  excludedIds: string[]
  includedFlaggedIds: string[]
  saving: Saving
  onChange: (next: AnalysisReport) => void
}

interface RequirementListProps {
  job: JobPosting | null
  assessments: Record<string, RequirementAssessment>
  banners: PostingBanner[]
  flags: RequirementFlag[]
  // Card 1: requirements that look met but may still be rejected, and when the CV last used them.
  screeningFlags: ScreeningFlag[]
  recency: Record<string, RecencyCheck>
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
  screeningFlags,
  recency,
  contributions,
  selectedId,
  onSelect,
  inputs,
}: RequirementListProps) {
  const contributionById = new Map(contributions.map((item) => [item.requirement_id, item]))
  const [error, setError] = useState<string | null>(null)
  const busy = inputs?.saving.busy === true

  // Saves one list. Fields left out keep their value on the server, so only the changed list is sent.
  async function save(body: InputsUpdate) {
    if (!inputs) return
    setError(null)
    try {
      const next = await inputs.saving.track(() => updateInputs(inputs.analysisId, body))
      inputs.onChange(next)
    } catch (failure) {
      setError(`Your change was not saved. ${describeError(failure)}`)
    }
  }

  // While any request of the report is running, a toggle is ignored (not disabled), so keyboard
  // focus stays on it.
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
              <strong>Posting warning.</strong> {cleanText(banner.explanation)}
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
            const screening = screeningFlags.find((flag) => flag.requirement_id === req.id)
            const recencyCheck = recency[req.id] as RecencyCheck | undefined
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
                screening={screening}
                recency={recencyCheck}
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
  screening: ScreeningFlag | undefined
  recency: RecencyCheck | undefined
  contribution: Contribution | undefined
  selected: boolean
  onSelect: () => void
  toggles: RowToggles | undefined
}

function RequirementRow({
  requirement,
  assessment,
  flags,
  screening,
  recency,
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
        {screening && <span className="chip chip-screening">Looks met, but...</span>}
      </button>

      <div className="req-details">
        <div className="req-tags">
          <span className="chip chip-neutral">{IMPORTANCE_LABELS[requirement.importance]}</span>
          <span className="chip chip-neutral">{CATEGORY_LABELS[requirement.category]}</span>
          {requirement.knockout_type && (
            <span className="chip chip-knockout">
              Deal-breaker: {KNOCKOUT_LABELS[requirement.knockout_type]}
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
              {FLAG_LABELS[flag.rule_id]}
            </p>
            <p>{cleanText(flag.explanation)}</p>
          </div>
        ))}

        {screening && screening.reasons.length > 0 && (
          <div className="req-flag">
            <p className="req-flag-title">Why it may still be screened out</p>
            <ul className="req-flag-list">
              {screening.reasons.map((reason, index) => (
                <li key={`${index}-${reason}`}>{cleanText(reason)}</li>
              ))}
            </ul>
          </div>
        )}

        {recency && <RecencyNote check={recency} />}

        {assessment?.rationale && !repeatsNote(assessment.rationale, screening, recency) && (
          <p className="req-rationale">
            <CitedText text={dropRuleIds(assessment.rationale)} />
          </p>
        )}

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
                  <CitationTag id={item.ref} /> <q>{item.quote}</q>{' '}
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

// "Last used 2017 (stale)". A requirement the posting's window downgraded also names that window.
function RecencyNote({ check }: { check: RecencyCheck }) {
  const year = check.last_used?.slice(0, 4)
  const warn = check.effect !== 'none'
  const windowYears = check.effect === 'downgraded' ? check.rule?.window_years : undefined
  return (
    <div className="req-recency">
      <p className={warn ? 'req-recency-line is-warn' : 'req-recency-line'}>
        {year ? `Last used ${year} (${check.band})` : `No dated entry shows it (${check.band})`}
      </p>
      {windowYears !== undefined && (
        <p className="req-recency-line is-warn">{`Outside the posting's ${windowYears}-year window.`}</p>
      )}
    </div>
  )
}

// True when the rationale repeats a reason in the screening box, or the recency explanation.
function repeatsNote(
  rationale: string,
  screening: ScreeningFlag | undefined,
  recency: RecencyCheck | undefined,
): boolean {
  const text = plainText(rationale)
  if (screening?.reasons.some((reason) => plainText(reason) === text)) return true
  return recency !== undefined && plainText(recency.explanation) === text
}

// The text with its spaces tidied, so the same sentence compares equal wherever it came from.
function plainText(text: string): string {
  return text.trim().replace(/\s+/g, ' ')
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
