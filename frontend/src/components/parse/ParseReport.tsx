import type { ParseWarning } from '../../api/types'
import { SEVERITY_LABELS } from '../../lib/labels'
import { splitParseWarnings } from '../../lib/parseWarnings'
import './ParseReport.css'

interface ParseReportProps {
  warnings: ParseWarning[]
  // Line IDs highlighted in the CV view. Pressing an item with lines sets them.
  highlightedLineIds: string[]
  onHighlight: (lineIds: string[]) => void
}

const SEVERITY_CHIP: Record<ParseWarning['severity'], string> = {
  error: 'chip-missing',
  warning: 'chip-partial',
  info: 'chip-neutral',
}

export default function ParseReport({ warnings, highlightedLineIds, onHighlight }: ParseReportProps) {
  const { problems, tips } = splitParseWarnings(warnings)
  const empty = problems.length === 0 && tips.length === 0

  return (
    <section className="parse-report card" aria-labelledby="parse-title">
      <h2 id="parse-title">How your CV reads</h2>

      {empty ? (
        <p className="notice notice-info">No problems found in how your CV reads.</p>
      ) : (
        <>
          {problems.length > 0 && (
            <div className="parse-group">
              <h3>Parse warnings</h3>
              <ul className="parse-list">
                {problems.map((item, index) => (
                  <ParseItem
                    key={`problem-${item.code}-${index}`}
                    item={item}
                    label={SEVERITY_LABELS[item.severity]}
                    chipClass={SEVERITY_CHIP[item.severity]}
                    highlighted={sameIds(item.line_ids, highlightedLineIds)}
                    onHighlight={onHighlight}
                  />
                ))}
              </ul>
            </div>
          )}

          {tips.length > 0 && (
            <div className="parse-group">
              <h3>Recruiter tips</h3>
              <ul className="parse-list">
                {tips.map((item, index) => (
                  <ParseItem
                    key={`tip-${item.code}-${index}`}
                    item={item}
                    label="Tip"
                    chipClass="chip-neutral"
                    highlighted={sameIds(item.line_ids, highlightedLineIds)}
                    onHighlight={onHighlight}
                  />
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  )
}

interface ParseItemProps {
  item: ParseWarning
  label: string
  chipClass: string
  highlighted: boolean
  onHighlight: (lineIds: string[]) => void
}

function ParseItem({ item, label, chipClass, highlighted, onHighlight }: ParseItemProps) {
  const hasLines = item.line_ids.length > 0

  return (
    <li className="parse-item">
      <span className={`chip ${chipClass}`}>{label}</span>
      <p className="parse-message">{item.message}</p>

      {hasLines && (
        <div className="parse-lines">
          <button
            type="button"
            className="parse-toggle"
            aria-pressed={highlighted}
            onClick={() => onHighlight(highlighted ? [] : item.line_ids)}
          >
            Show in CV
          </button>
          <span className="parse-ids">
            Lines:{' '}
            {item.line_ids.map((id) => (
              <code key={id} className="parse-id">
                {id}
              </code>
            ))}
          </span>
        </div>
      )}
    </li>
  )
}

// Same set of line IDs, in any order.
function sameIds(a: string[], b: string[]): boolean {
  return a.length > 0 && a.length === b.length && a.every((id) => b.includes(id))
}
