import { useState } from 'react'
import { verifySuggestion } from '../../api/client'
import type {
  AnalysisReport,
  Category,
  CvLine,
  CvSection,
  ReviewDecisions,
  Suggestion,
} from '../../api/types'
import { SECTION_LABELS } from '../../lib/labels'
import ScoreValue from './ScoreValue'
import SuggestionCard, { type Decision } from './SuggestionCard'
import './ReviewScreen.css'

interface ReviewScreenProps {
  analysis: AnalysisReport
  // The choices to start from: set when the user comes back here after a failed build.
  initialDecisions: ReviewDecisions | null
  onAnalysisChange: (next: AnalysisReport) => void
  onBuild: (decisions: ReviewDecisions) => void
}

type Decisions = Partial<Record<string, Decision>>

// Categories that count toward keyword coverage. Same list as config/scoring.toml.
const COVERAGE_CATEGORIES: ReadonlySet<Category> = new Set<Category>([
  'hard_skill',
  'job_title',
  'education',
  'certification_license',
  'language',
])

export default function ReviewScreen({
  analysis,
  initialDecisions,
  onAnalysisChange,
  onBuild,
}: ReviewScreenProps) {
  const [decisions, setDecisions] = useState<Decisions>(() => fromLists(initialDecisions))
  const [checking, setChecking] = useState(0) // edits waiting for their check

  const suggestions = analysis.suggestions
  const verified = suggestions.filter(isVerified)
  const unsupported = suggestions.filter((s) => s.verification.status === 'unsupported')
  const accepted = suggestions.filter((s) => effectiveDecision(s, decisions) === 'accepted')
  const rejected = suggestions.filter((s) => effectiveDecision(s, decisions) === 'rejected')
  const coverage = estimateCoverage(analysis, accepted)
  const groups = groupSuggestions(analysis)

  const requirementLabels = new Map<string, string>(
    (analysis.job?.requirements ?? []).map((req): [string, string] => [req.id, req.label]),
  )
  const citations = new Map<string, string>()
  for (const line of analysis.cv?.lines ?? []) citations.set(line.id, line.text)
  for (const fact of analysis.cv?.facts ?? []) citations.set(fact.id, fact.text)

  function decide(id: string, decision: Decision) {
    // Choosing the same decision again clears it.
    setDecisions((previous) => {
      const next = { ...previous }
      if (previous[id] === decision) delete next[id]
      else next[id] = decision
      return next
    })
  }

  function acceptVerified() {
    setDecisions((previous) => {
      const next = { ...previous }
      for (const suggestion of verified) next[suggestion.id] = 'accepted'
      return next
    })
  }

  // Checks an edited text again. The cards show the outcome from the new report.
  async function checkEdit(id: string, text: string) {
    setChecking((count) => count + 1)
    try {
      const next = await verifySuggestion(analysis.analysis_id, id, text)
      onAnalysisChange(next)
    } finally {
      setChecking((count) => count - 1)
    }
  }

  function build() {
    onBuild({
      accepted: accepted.map((s) => s.id),
      rejected: rejected.map((s) => s.id),
    })
  }

  return (
    <div className="review">
      <section className="card review-summary" aria-labelledby="review-title">
        <p className="eyebrow">Review</p>
        <h2 id="review-title">Choose the changes for your new CV</h2>
        <p>Only verified changes can be accepted. Nothing reaches your new CV unless you accept it.</p>

        <ul className="counts" aria-label="Suggestion counts">
          <li className="chip chip-met">{verified.length} verified</li>
          <li className="chip chip-missing">{unsupported.length} unsupported</li>
          <li className="chip chip-neutral">{accepted.length} accepted</li>
          <li className="chip chip-neutral">{rejected.length} rejected</li>
        </ul>

        <section className="review-coverage" aria-labelledby="coverage-title">
          <h3 id="coverage-title">Keyword coverage</h3>
          <div className="compare">
            <div className="compare-item">
              <span className="compare-label">Now</span>
              <span className="compare-value">
                <ScoreValue value={coverage.now} />
              </span>
            </div>
            <span className="compare-arrow" aria-hidden="true">
              →
            </span>
            <div className="compare-item">
              <span className="compare-label">If accepted</span>
              <span className="compare-value">
                <ScoreValue value={coverage.ifAccepted} />
              </span>
            </div>
          </div>
          <p className="screen-note">Estimate from the changes you accept. It updates as you choose.</p>
        </section>

        <div className="summary-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={acceptVerified}
            disabled={verified.length === 0}
          >
            Accept all verified
          </button>
          <button type="button" className="btn btn-primary" onClick={build} disabled={checking > 0}>
            Build my new CV
          </button>
        </div>

        {checking > 0 && (
          <p className="notice notice-info" role="status">
            Checking your edit. You can build the CV when it finishes.
          </p>
        )}
      </section>

      {groups.length === 0 && (
        <section className="card">
          <p>No suggestions were found for this CV and posting.</p>
        </section>
      )}

      {groups.map((group, index) => (
        <section key={group.key} className="review-group" aria-labelledby={`review-group-${index}`}>
          <h3 id={`review-group-${index}`}>{group.title}</h3>
          <ul className="suggestion-list">
            {group.suggestions.map((suggestion) => (
              <li key={suggestion.id}>
                <SuggestionCard
                  suggestion={suggestion}
                  decision={effectiveDecision(suggestion, decisions)}
                  requirementLabels={requirementLabels}
                  citations={citations}
                  onDecide={(choice) => decide(suggestion.id, choice)}
                  onSaveEdit={(text) => checkEdit(suggestion.id, text)}
                />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function isVerified(suggestion: Suggestion): boolean {
  return suggestion.verification.status === 'verified'
}

// Turns the saved lists back into one decision per suggestion.
function fromLists(saved: ReviewDecisions | null): Decisions {
  const decisions: Decisions = {}
  for (const id of saved?.accepted ?? []) decisions[id] = 'accepted'
  for (const id of saved?.rejected ?? []) decisions[id] = 'rejected'
  return decisions
}

// Only a verified suggestion can be accepted. An edit that makes it unsupported drops its acceptance.
function effectiveDecision(suggestion: Suggestion, decisions: Decisions): Decision | undefined {
  const decision = decisions[suggestion.id]
  if (decision === 'accepted' && !isVerified(suggestion)) return undefined
  return decision
}

interface CoverageEstimate {
  now: number | null
  ifAccepted: number | null
}

// Keyword coverage now, and if the accepted changes are applied. Each requirement that an
// accepted change newly covers adds its weight, as the score counts it.
function estimateCoverage(analysis: AnalysisReport, accepted: Suggestion[]): CoverageEstimate {
  const score = analysis.score
  if (!score || score.coverage === null || score.coverage_denominator <= 0) {
    return { now: null, ifAccepted: null }
  }

  const contributions = new Map(
    score.contributions.map((item) => [item.requirement_id, item] as const),
  )
  const newlyCovered = new Set<string>()
  for (const suggestion of accepted) {
    for (const requirementId of suggestion.covers_requirement_ids) {
      const item = contributions.get(requirementId)
      if (!item || item.excluded_reason !== null || !COVERAGE_CATEGORIES.has(item.category)) continue
      if (analysis.assessments[requirementId]?.keyword_present) continue
      newlyCovered.add(requirementId)
    }
  }

  let gained = 0
  for (const requirementId of newlyCovered) {
    gained += contributions.get(requirementId)?.weight ?? 0
  }
  return {
    now: score.coverage,
    ifAccepted: (100 * (score.coverage_numerator + gained)) / score.coverage_denominator,
  }
}

interface SuggestionGroup {
  key: string
  title: string
  suggestions: Suggestion[]
}

// Groups suggestions by the CV section they change, in CV order. Sections that the CV does not
// have yet (a new skills or summary section) come after them.
function groupSuggestions(analysis: AnalysisReport): SuggestionGroup[] {
  const sections = analysis.cv?.sections ?? []
  const lines = analysis.cv?.lines ?? []
  const byKey = new Map<string, Suggestion[]>()
  for (const suggestion of analysis.suggestions) {
    const key =
      sectionIdFor(suggestion, sections) ??
      (suggestion.kind === 'align_wording' ? 'other' : suggestion.target)
    byKey.set(key, [...(byKey.get(key) ?? []), suggestion])
  }

  const groups: SuggestionGroup[] = []
  for (const section of sections) {
    const items = byKey.get(section.id)
    if (items) {
      groups.push({ key: section.id, title: sectionTitle(section, lines), suggestions: items })
      byKey.delete(section.id)
    }
  }
  for (const [key, items] of byKey) {
    groups.push({ key, title: extraTitle(key), suggestions: items })
  }
  return groups
}

// The CV section a suggestion changes: the one that holds its line, or the one it names.
function sectionIdFor(suggestion: Suggestion, sections: CvSection[]): string | null {
  const found =
    suggestion.kind === 'align_wording'
      ? sections.find(
          (section) =>
            section.heading_line_id === suggestion.target ||
            section.line_ids.includes(suggestion.target),
        )
      : sections.find((section) => section.id === suggestion.target)
  return found?.id ?? null
}

function sectionTitle(section: CvSection, lines: CvLine[]): string {
  if (section.type !== 'other') return SECTION_LABELS[section.type]
  return lines.find((line) => line.id === section.heading_line_id)?.text ?? SECTION_LABELS.other
}

function extraTitle(key: string): string {
  if (key === 'new-skills') return 'Skills (new section)'
  if (key === 'new-summary') return 'Summary (new section)'
  return 'Other'
}
