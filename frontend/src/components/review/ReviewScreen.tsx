import { useEffect, useState } from 'react'
import { previewCoverage, verifySuggestion } from '../../api/client'
import type {
  AnalysisReport,
  CoveragePreview,
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

// Wait this long after the last change to the accepted set before asking for a new preview.
const PREVIEW_DELAY_MS = 300

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
  const acceptedKey = accepted.map((s) => s.id).join('|')
  const coverage = useCoveragePreview(analysis.analysis_id, acceptedKey)
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

        {/* A failed preview shows nothing: the estimate is optional, so the error stays quiet. */}
        {coverage.status !== 'failed' && (
          <section className="review-coverage" aria-live="polite">
            {coverage.status === 'loading' ? (
              <p className="screen-note">Checking keyword coverage...</p>
            ) : (
              <>
                <p className="coverage-line">
                  Keyword coverage now{' '}
                  <strong>
                    <ScoreValue value={coverage.preview.coverage_now} />
                  </strong>{' '}
                  <span aria-hidden="true">→</span>
                  <span className="visually-hidden"> to </span>{' '}
                  <strong>
                    <ScoreValue value={coverage.preview.coverage} />
                  </strong>{' '}
                  if you build with these changes.
                </p>
                <p className="screen-note">
                  {gainedSentence(coverage.preview.gained_requirement_ids, requirementLabels)}
                </p>
              </>
            )}
          </section>
        )}

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

type CoverageState =
  | { status: 'loading' }
  | { status: 'ready'; preview: CoveragePreview }
  | { status: 'failed' }

// The keyword coverage for the accepted suggestions, from the backend. It is asked for again when
// the accepted set changes, after a short pause. A reply for a set that has changed since is
// dropped. A failed call gives 'failed'.
function useCoveragePreview(analysisId: string, acceptedKey: string): CoverageState {
  const [answer, setAnswer] = useState<{ key: string; state: CoverageState } | null>(null)

  useEffect(() => {
    const ids = acceptedKey === '' ? [] : acceptedKey.split('|')
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void previewCoverage(analysisId, ids, controller.signal)
        .then((preview) => {
          if (!controller.signal.aborted) {
            setAnswer({ key: acceptedKey, state: { status: 'ready', preview } })
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setAnswer({ key: acceptedKey, state: { status: 'failed' } })
          }
        })
    }, PREVIEW_DELAY_MS)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [analysisId, acceptedKey])

  return answer !== null && answer.key === acceptedKey ? answer.state : { status: 'loading' }
}

// Names the requirements that the accepted changes newly cover.
function gainedSentence(ids: readonly string[], labels: ReadonlyMap<string, string>): string {
  if (ids.length === 0) return 'These changes cover no new requirement.'
  const names = ids.map((id) => labels.get(id) ?? id)
  return `Requirements that become covered: ${names.join(', ')}.`
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
