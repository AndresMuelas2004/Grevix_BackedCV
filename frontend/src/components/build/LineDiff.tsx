import type { DiffLine, DiffStatus } from '../../api/types'
import ChangeDiff from '../review/ChangeDiff'
import './LineDiff.css'

interface LineDiffProps {
  lines: DiffLine[]
  titles: ReadonlyMap<string, string> // section ID to the heading shown above its lines
}

type Item = { kind: 'change'; line: DiffLine } | { kind: 'unchanged'; lines: DiffLine[] }

interface Section {
  id: string
  title: string
  items: Item[]
}

const STATUS_CHIPS: Record<DiffStatus, { label: string; chip: string }> = {
  unchanged: { label: 'Unchanged', chip: 'chip-unknown' },
  changed: { label: 'Changed', chip: 'chip-partial' },
  added: { label: 'Added', chip: 'chip-met' },
  removed: { label: 'Removed', chip: 'chip-missing' },
}

// The line diff of the new CV. Unchanged lines are folded away; changes are shown in full.
export default function LineDiff({ lines, titles }: LineDiffProps) {
  const sections = groupBySection(lines, titles)
  return (
    <div className="line-diff">
      {sections.map((section, sectionIndex) => (
        <section
          key={sectionIndex}
          className="line-diff-section"
          aria-labelledby={`line-diff-${sectionIndex}`}
        >
          <h4 id={`line-diff-${sectionIndex}`}>{section.title}</h4>
          <ul className="line-diff-items">
            {section.items.map((item, index) =>
              item.kind === 'unchanged' ? (
                <li key={index} className="line-diff-folded">
                  <details>
                    <summary>
                      {item.lines.length} unchanged {item.lines.length === 1 ? 'line' : 'lines'}
                    </summary>
                    <ul className="line-plain">
                      {item.lines.map((line, lineIndex) => (
                        <li key={lineIndex}>{line.after ?? line.before}</li>
                      ))}
                    </ul>
                  </details>
                </li>
              ) : (
                <li key={index} className={`line-diff-item is-${item.line.status}`}>
                  <span className={`chip ${STATUS_CHIPS[item.line.status].chip}`}>
                    {STATUS_CHIPS[item.line.status].label}
                  </span>
                  {item.line.status === 'changed' ? (
                    <ChangeDiff before={item.line.before} after={item.line.after ?? ''} />
                  ) : (
                    <p className="line-text">
                      {item.line.status === 'added' ? item.line.after : item.line.before}
                    </p>
                  )}
                </li>
              ),
            )}
          </ul>
        </section>
      ))}
    </div>
  )
}

// Groups consecutive lines of the same section, and folds consecutive unchanged lines together.
function groupBySection(lines: DiffLine[], titles: ReadonlyMap<string, string>): Section[] {
  const sections: Section[] = []
  for (const line of lines) {
    const last = sections.at(-1)
    const section: Section =
      last && last.id === line.section_id
        ? last
        : { id: line.section_id, title: sectionTitle(line.section_id, titles), items: [] }
    if (section !== last) sections.push(section)

    if (line.status === 'unchanged') {
      const lastItem = section.items.at(-1)
      if (lastItem?.kind === 'unchanged') lastItem.lines.push(line)
      else section.items.push({ kind: 'unchanged', lines: [line] })
    } else {
      section.items.push({ kind: 'change', line })
    }
  }
  return sections
}

// The heading of a section: the CV's own heading when it has one, else the section name with a
// capital letter (e.g. "contact" becomes "Contact").
function sectionTitle(sectionId: string, titles: ReadonlyMap<string, string>): string {
  const heading = titles.get(sectionId)
  if (heading) return heading
  const name = sectionId.replace(/[-_]+/g, ' ').trim()
  return name.charAt(0).toUpperCase() + name.slice(1)
}
