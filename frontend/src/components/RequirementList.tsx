import type {
  Contribution,
  JobPosting,
  PostingBanner,
  Requirement,
  RequirementAssessment,
  RequirementFlag,
  Status,
} from '../api/types'
import {
  CATEGORY_LABELS,
  FLAG_LABELS,
  IMPORTANCE_LABELS,
  KNOCKOUT_LABELS,
  MATCH_LABELS,
  STATUS_LABELS,
} from '../lib/labels'
import './RequirementList.css'

interface RequirementListProps {
  job: JobPosting | null
  assessments: Record<string, RequirementAssessment>
  banners: PostingBanner[]
  flags: RequirementFlag[]
  contributions: Contribution[]
  selectedId: string | null
  onSelect: (requirementId: string | null) => void
}

export default function RequirementList({
  job,
  assessments,
  banners,
  flags,
  contributions,
  selectedId,
  onSelect,
}: RequirementListProps) {
  const contributionById = new Map(contributions.map((item) => [item.requirement_id, item]))

  return (
    <section className="requirements" aria-labelledby="requirements-title">
      <h2 id="requirements-title">Requirements</h2>

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
          {job.requirements.map((req) => (
            <RequirementRow
              key={req.id}
              requirement={req}
              assessment={assessments[req.id] as RequirementAssessment | undefined}
              flags={flags.filter((flag) => flag.requirement_ids.includes(req.id))}
              contribution={contributionById.get(req.id)}
              selected={selectedId === req.id}
              onSelect={() => onSelect(selectedId === req.id ? null : req.id)}
            />
          ))}
        </ol>
      )}
    </section>
  )
}

interface RequirementRowProps {
  requirement: Requirement
  assessment: RequirementAssessment | undefined
  flags: RequirementFlag[]
  contribution: Contribution | undefined
  selected: boolean
  onSelect: () => void
}

function RequirementRow({
  requirement,
  assessment,
  flags,
  contribution,
  selected,
  onSelect,
}: RequirementRowProps) {
  const status: Status = assessment?.status ?? 'unknown'
  const evidence = assessment?.evidence ?? []
  const notCounted = contribution !== undefined && contribution.excluded_reason !== null

  return (
    <li className={selected ? 'req-row is-selected' : 'req-row'}>
      <button
        type="button"
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

        {notCounted && <p className="req-note">Not counted in Fit.</p>}

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
