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
import { friendlyText } from '../../lib/errorMessages'
import { formatScore } from '../../lib/format'
import { SECTION_LABELS } from '../../lib/labels'
import { useSaving } from '../../lib/saving'
import HowComputed from '../HowComputed'
import RefusedGroup from './RefusedGroup'
import ScoreValue from './ScoreValue'
import SuggestionCard, { type Decision } from './SuggestionCard'
import './ReviewScreen.css'

interface ReviewScreenProps {
  analysis: AnalysisReport
  // The choices to start from: set when the user comes back here after a failed build.
  initialDecisions: ReviewDecisions | null
  onAnalysisChange: (next: AnalysisReport) => void
  onBuild: (decisions: ReviewDecisions) => void
  onRetrySuggestions: () => void // asks for the suggestions again, after the step failed
}

type Decisions = Partial<Record<string, Decision>>

// Wait this long after the last change to the accepted set before asking for a new preview.
const PREVIEW_DELAY_MS = 300

export default function ReviewScreen({
  analysis,
  initialDecisions,
  onAnalysisChange,
  onBuild,
  onRetrySuggestions,
}: ReviewScreenProps) {
  const [decisions, setDecisions] = useState<Decisions>(() => fromLists(initialDecisions))
  // Every request of this screen is counted here: while one is in flight, nothing else can be sent.
  const saving = useSaving()

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
  // Refused suggestions are not offered here: they are listed in the refused group at the end.
  const groups = groupSuggestions(
    analysis,
    suggestions.filter((suggestion) => !isRefused(suggestion)),
  )
  const refused = suggestions.filter(isRefused)
  const refusedIds = new Set(refused.map((suggestion) => suggestion.id))
  // A refusal of a suggestion is shown on that suggestion's card; the other refusals on their own.
  const refusals = (analysis.refusals ?? []).filter(
    (refusal) => refusal.suggestion_id === null || !refusedIds.has(refusal.suggestion_id),
  )
  const refusedItems = groupSuggestions(analysis, refused).flatMap((group) =>
    group.suggestions.map((suggestion) => ({ suggestion, sectionTitle: group.title })),
  )
  const hasRefused = refusals.length > 0 || refusedItems.length > 0
  // No suggestions, and the suggest step itself failed on the server: not the same as "none needed".
  const suggestFailed =
    suggestions.length === 0 && analysis.errors.some((error) => error.node === 'suggest')

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
    const next = await saving.track(() => verifySuggestion(analysis.analysis_id, id, text))
    onAnalysisChange(next)
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
        <h1 id="review-title" tabIndex={-1} data-screen-heading>
          Choose the changes for your new CV
        </h1>
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
            disabled={verified.length === 0 || saving.busy}
          >
            Accept all verified
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={build}
            disabled={saving.busy}
          >
            Build my new CV
          </button>
        </div>

        {saving.busy && (
          <p className="notice notice-info" role="status">
            Checking your edit. You can build the CV when it finishes.
          </p>
        )}
      </section>

      {groups.length === 0 && suggestFailed && (
        <section className="card" aria-labelledby="suggest-failed-title">
          <h2 id="suggest-failed-title">{friendlyText('optimize_failed').message}</h2>
          <div className="error-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={onRetrySuggestions}
              disabled={saving.busy}
            >
              Try again
            </button>
          </div>
        </section>
      )}

      {groups.length === 0 && !suggestFailed && !hasRefused && (
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
                  sectionTitle={group.title}
                  busy={saving.busy}
                  onDecide={(choice) => decide(suggestion.id, choice)}
                  onSaveEdit={(text) => checkEdit(suggestion.id, text)}
                />
              </li>
            ))}
          </ul>
        </section>
      ))}

      {hasRefused && (
        <RefusedGroup
          refusals={refusals}
          items={refusedItems}
          requirementLabels={requirementLabels}
          citations={citations}
        />
      )}

      <HowComputed usage={analysis.usage} />
    </div>
  )
}

function isVerified(suggestion: Suggestion): boolean {
  return suggestion.verification.status === 'verified'
}

// Refused by the gate: backed by the CV but not viable. Such a suggestion can never be accepted.
function isRefused(suggestion: Suggestion): boolean {
  return suggestion.verification.status === 'refused'
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

// Groups the given suggestions by the CV section they change, in CV order. Sections that the CV does
// not have yet (a new skills or summary section) come after them.
function groupSuggestions(analysis: AnalysisReport, list: Suggestion[]): SuggestionGroup[] {
  const sections = analysis.cv?.sections ?? []
  const lines = analysis.cv?.lines ?? []
  const byKey = new Map<string, Suggestion[]>()
  for (const suggestion of list) {
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
