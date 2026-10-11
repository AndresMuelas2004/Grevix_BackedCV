import type { Refusal, Suggestion } from '../../api/types'
import { GATE_LABELS, SUGGESTION_KIND_LABELS } from '../../lib/labels'
import CitationTag, { CitedText } from '../CitationTag'
import ChangeDiff from './ChangeDiff'
import './RefusedGroup.css'
import './SuggestionCard.css' // the card and cited-line classes are shared with SuggestionCard

// A refused suggestion, with the section it would change (the title the review groups use).
interface RefusedItem {
  suggestion: Suggestion
  sectionTitle: string
}

interface RefusedGroupProps {
  refusals: Refusal[] // refusals of requirements: no suggestion was made for them
  items: RefusedItem[] // refused suggestions, in CV order
  requirementLabels: ReadonlyMap<string, string>
  citations: ReadonlyMap<string, string> // CV line and fact IDs to their text
}

// Edits the CV backs but that are not viable for this posting: they cannot be accepted.
export default function RefusedGroup({
  refusals,
  items,
  requirementLabels,
  citations,
}: RefusedGroupProps) {
  return (
    <section className="review-group" aria-labelledby="refused-title">
      <h3 id="refused-title">Refused as not viable</h3>
      <p className="screen-note">These cannot be accepted. Each reason says why.</p>
      <ul className="refused-list">
        {refusals.map((refusal, index) => (
          <li key={`${refusal.requirement_id}-${index}`}>
            <RefusalCard
              headingId={`refusal-${index}-title`}
              label={requirementLabels.get(refusal.requirement_id) ?? refusal.requirement_id}
              refusal={refusal}
              citations={citations}
            />
          </li>
        ))}
        {items.map((item) => (
          <li key={item.suggestion.id}>
            <RefusedSuggestion item={item} />
          </li>
        ))}
      </ul>
    </section>
  )
}

interface RefusalCardProps {
  headingId: string
  label: string
  refusal: Refusal
  citations: ReadonlyMap<string, string>
}

// A requirement refused before any suggestion was made for it.
function RefusalCard({ headingId, label, refusal, citations }: RefusalCardProps) {
  return (
    <article className="suggestion card refused-card" aria-labelledby={headingId}>
      <h4 id={headingId}>{label}</h4>
      <p>
        <CitedText text={refusal.reason} />
      </p>
      {refusal.refs.length > 0 && (
        <div className="cited">
          <p className="suggestion-label">Evidence in your CV</p>
          <ul className="cited-list">
            {refusal.refs.map((ref) => (
              <li key={ref}>
                <CitationTag id={ref} />
                <span>{citations.get(ref) ?? 'Not found in your CV.'}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  )
}

// A generated suggestion that a gate pass refused.
function RefusedSuggestion({ item }: { item: RefusedItem }) {
  const { suggestion, sectionTitle } = item
  const titleId = `refused-${suggestion.id}-title`
  const reason = suggestion.verification.reason ?? 'The check did not pass.'
  const failed = (suggestion.verification.passes ?? []).filter((pass) => !pass.ok)
  return (
    <article className="suggestion card refused-card" data-status="refused" aria-labelledby={titleId}>
      <div className="suggestion-head">
        <h4 id={titleId}>{SUGGESTION_KIND_LABELS[suggestion.kind]}</h4>
        <span className="chip chip-missing">Refused</span>
      </div>

      <ChangeDiff before={suggestion.before} after={suggestion.after} sectionTitle={sectionTitle} />

      <div className="reason-box">
        <p>
          <strong>Not viable.</strong> <CitedText text={reason} />
        </p>
        {failed.map((pass) => (
          <p key={pass.name}>Failed check: {GATE_LABELS[pass.name]}.</p>
        ))}
      </div>
    </article>
  )
}
