import type { CvLine, ParseWarning } from '../../api/types'
import { SEVERITY_LABELS } from '../../lib/labels'
import { splitParseWarnings } from '../../lib/parseWarnings'
import CitationTag, { CitedText } from '../CitationTag'
import './ParseReport.css'

interface ParseReportProps {
  warnings: ParseWarning[]
  lines: CvLine[]
  // Line IDs highlighted in the CV view. Pressing an item with lines sets them.
  highlightedLineIds: string[]
  onHighlight: (lineIds: string[]) => void
}

const SEVERITY_CHIP: Record<ParseWarning['severity'], string> = {
  error: 'chip-missing',
  warning: 'chip-partial',
  info: 'chip-neutral',
}

export default function ParseReport({
  warnings,
  lines,
  highlightedLineIds,
  onHighlight,
}: ParseReportProps) {
  const { problems, tips } = splitParseWarnings(warnings)
  const empty = problems.length === 0 && tips.length === 0
  const lineTexts = new Map<string, string>(lines.map((line): [string, string] => [line.id, line.text]))

  return (
    <section className="parse-report card" aria-labelledby="parse-title">
      <h2 id="parse-title">How your CV reads</h2>

      {empty ? (
        <p className="notice notice-info">No problems found in how your CV reads.</p>
      ) : (
        <>
          {problems.length > 0 && (
            <div className="parse-group">
              <h3>Problems found</h3>
              <ul className="parse-list">
                {problems.map((item, index) => (
                  <ParseItem
                    key={`problem-${item.code}-${index}`}
                    item={item}
                    label={SEVERITY_LABELS[item.severity]}
                    chipClass={SEVERITY_CHIP[item.severity]}
                    lineTexts={lineTexts}
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
                    lineTexts={lineTexts}
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
  lineTexts: ReadonlyMap<string, string> // CV line ID to its text
  highlighted: boolean
  onHighlight: (lineIds: string[]) => void
}

function ParseItem({ item, label, chipClass, lineTexts, highlighted, onHighlight }: ParseItemProps) {
  const hasLines = item.line_ids.length > 0

  return (
    <li className="parse-item">
      <span className={`chip ${chipClass}`}>{label}</span>
      <p className="parse-message">
        <CitedText text={item.message} />
      </p>

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
          <ul className="parse-cited">
            {item.line_ids.map((id) => (
              <li key={id}>
                <CitationTag id={id} />
                <span>{lineTexts.get(id) ?? 'Not found in your CV.'}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  )
}

// Same set of line IDs, in any order.
function sameIds(a: string[], b: string[]): boolean {
  return a.length > 0 && a.length === b.length && a.every((id) => b.includes(id))
}
