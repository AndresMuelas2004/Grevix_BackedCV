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
import { formatScore } from '../../lib/format'
import { SECTION_LABELS } from '../../lib/labels'
import HowComputed from '../HowComputed'
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
  // Until something is accepted, the preview asks about every verified suggestion: it shows what
  // accepting them would gain. Once something is accepted, it covers only the accepted ones.
  const coverage = useCoveragePreview(
    analysis,
    accepted.length > 0 ? accepted.map((s) => s.id) : verified.map((s) => s.id),
  )
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
        <h2 id="review-title" tabIndex={-1} data-screen-heading>
          Choose the changes for your new CV
        </h2>
        <p>Only verified changes can be accepted. Nothing reaches your new CV unless you accept it.</p>

        <ul className="counts" aria-label="Suggestion counts">
          <li className="chip chip-met">{verified.length} verified</li>
          <li className="chip chip-missing">{unsupported.length} unsupported</li>
          <li className="chip chip-neutral">{accepted.length} accepted</li>
          <li className="chip chip-neutral">{rejected.length} rejected</li>
        </ul>

        {/* A failed preview shows nothing: the estimate is optional, so the error stays quiet. */}
        {coverage.status !== 'failed' && coverage.status !== 'idle' && (
          <section className="review-coverage" aria-live="polite">
            {coverage.status === 'loading' ? (
              <p className="screen-note">Checking keyword coverage...</p>
            ) : accepted.length > 0 ? (
              <SelectionCoverage preview={coverage.preview} labels={requirementLabels} />
            ) : (
              <PotentialCoverage preview={coverage.preview} labels={requirementLabels} />
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

      <HowComputed usage={analysis.usage} />
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
  | { status: 'idle' } // no suggestion to ask about
  | { status: 'loading' }
  | { status: 'ready'; preview: CoveragePreview }
  | { status: 'failed' }

interface CoverageAnswer {
  report: AnalysisReport
  key: string
  state: CoverageState
}

// The keyword coverage for a set of suggestions, from the backend. It is asked for again when the set
// or the report changes (an edited text can change the coverage), after a short pause. A reply for a
// set or a report that has changed since is dropped. A failed call gives 'failed'.
function useCoveragePreview(
  analysis: AnalysisReport,
  suggestionIds: readonly string[],
): CoverageState {
  const idKey = suggestionIds.join('|')
  const [answer, setAnswer] = useState<CoverageAnswer | null>(null)

  useEffect(() => {
    if (idKey === '') return
    const ids = idKey.split('|')
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void previewCoverage(analysis.analysis_id, ids, controller.signal)
        .then((preview) => {
          if (!controller.signal.aborted) {
            setAnswer({ report: analysis, key: idKey, state: { status: 'ready', preview } })
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setAnswer({ report: analysis, key: idKey, state: { status: 'failed' } })
          }
        })
    }, PREVIEW_DELAY_MS)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [analysis, idKey])

  if (idKey === '') return { status: 'idle' }
  return answer !== null && answer.report === analysis && answer.key === idKey
    ? answer.state
    : { status: 'loading' }
}

interface CoverageProps {
  preview: CoveragePreview
  labels: ReadonlyMap<string, string>
}

// The keyword coverage if the accepted suggestions are built.
function SelectionCoverage({ preview, labels }: CoverageProps) {
  const gained = preview.gained_requirement_ids
  return (
    <>
      <p className="coverage-line">
        Keyword coverage now{' '}
        <strong>
          <ScoreValue value={preview.coverage_now} />
        </strong>{' '}
        <span aria-hidden="true">→</span>
        <span className="visually-hidden"> to </span>{' '}
        <strong>
          <ScoreValue value={preview.coverage} />
        </strong>{' '}
        if you build with these changes.
      </p>
      <p className="screen-note">
        {gained.length === 0
          ? 'These changes cover no new requirement.'
          : `Requirements that become covered: ${requirementNames(gained, labels)}.`}
      </p>
    </>
  )
}

// Before anything is accepted: how far the verified suggestions would raise the coverage.
function PotentialCoverage({ preview, labels }: CoverageProps) {
  const { coverage, coverage_now: now } = preview
  const gained = preview.gained_requirement_ids
  if (coverage === null || now === null) return null
  return (
    <>
      {formatScore(coverage) === formatScore(now) ? (
        <p className="coverage-line">The verified suggestions do not raise keyword coverage.</p>
      ) : (
        <p className="coverage-line">
          Accept the verified suggestions to raise keyword coverage from{' '}
          <strong>
            <ScoreValue value={now} />
          </strong>{' '}
          to{' '}
          <strong>
            <ScoreValue value={coverage} />
          </strong>
          .
        </p>
      )}
      {gained.length > 0 && (
        <p className="screen-note">Requirements they would cover: {requirementNames(gained, labels)}.</p>
      )}
    </>
  )
}

// The labels of the given requirements, in the order given.
function requirementNames(ids: readonly string[], labels: ReadonlyMap<string, string>): string {
  return ids.map((id) => labels.get(id) ?? id).join(', ')
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
