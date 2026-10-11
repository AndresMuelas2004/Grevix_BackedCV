import { useEffect } from 'react'
import type { CvLine, CvMeta, CvSection, ParsedCv } from '../api/types'
import { SECTION_LABELS } from '../lib/labels'
import './CVView.css'

interface CvViewProps {
  cv: ParsedCv | null
  meta: CvMeta | null
  selectedId: string | null
  // Line or fact IDs (L… or F…) cited as evidence by the selected requirement.
  highlightIds: string[]
}

interface LineGroup {
  key: string
  label: string
  lines: CvLine[]
}

export default function CvView({ cv, meta, selectedId, highlightIds }: CvViewProps) {
  const highlighted = new Set(highlightIds)
  const groups = cv ? groupLines(cv) : []
  const readingOrder = cv ? [...cv.lines.map((line) => line.id), ...cv.facts.map((fact) => fact.id)] : []
  const firstHighlighted = readingOrder.find((id) => highlighted.has(id)) ?? null
  const highlightKey = highlightIds.join('|')

  // Bring the first evidence line into view whenever the selection changes.
  useEffect(() => {
    if (!firstHighlighted) return
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    document
      .getElementById(`cv-${firstHighlighted}`)
      ?.scrollIntoView({ block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' })
  }, [firstHighlighted, highlightKey])

  let hint: string | null = null
  if (selectedId === null) {
    hint = 'Select a requirement to see its evidence highlighted here.'
  } else if (firstHighlighted === null) {
    hint = 'This requirement has no evidence in your CV.'
  }

  return (
    <section className="cv-view card" aria-labelledby="cv-view-title">
      <h2 id="cv-view-title">How screening software reads your CV</h2>
      <p className="cv-source">{sourceText(meta)}</p>
      {hint && <p className="cv-hint">{hint}</p>}

      {cv === null ? (
        <p className="notice notice-info">The CV could not be read.</p>
      ) : (
        <div className="cv-scroll" role="region" aria-label="Lines read from your CV" tabIndex={0}>
          {groups.map((group) => (
            <div key={`${group.key}-${group.lines[0].id}`} className="cv-group">
              <h3 className="cv-group-title">{group.label}</h3>
              <ul className="cv-lines">
                {group.lines.map((line) => (
                  <LineItem
                    key={line.id}
                    id={line.id}
                    text={line.text}
                    highlighted={highlighted.has(line.id)}
                  />
                ))}
              </ul>
            </div>
          ))}

          {cv.facts.length > 0 && (
            <div className="cv-group">
              <h3 className="cv-group-title">Computed facts</h3>
              <ul className="cv-lines">
                {cv.facts.map((fact) => (
                  <LineItem
                    key={fact.id}
                    id={fact.id}
                    text={fact.text}
                    highlighted={highlighted.has(fact.id)}
                  />
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

interface LineItemProps {
  id: string
  text: string
  highlighted: boolean
}

function LineItem({ id, text, highlighted }: LineItemProps) {
  return (
    <li id={`cv-${id}`} className={highlighted ? 'cv-line is-evidence' : 'cv-line'}>
      <span className="cv-id">{id}</span>
      <span className="cv-text">{text}</span>
      {highlighted && <span className="cv-tag">Evidence</span>}
    </li>
  )
}

// Lines keep their reading order. Each run of lines in the same section forms
// one group, labelled with the section type. Lines outside any section are "Other lines".
function groupLines(cv: ParsedCv): LineGroup[] {
  const sectionByLine = new Map<string, CvSection>()
  for (const section of cv.sections) {
    for (const lineId of section.line_ids) {
      if (!sectionByLine.has(lineId)) sectionByLine.set(lineId, section)
    }
  }

  const groups: LineGroup[] = []
  for (const line of cv.lines) {
    const section = sectionByLine.get(line.id)
    const key = section ? section.id : 'other'
    const last = groups.at(-1)
    if (last && last.key === key) {
      last.lines.push(line)
    } else {
      groups.push({
        key,
        label: section ? SECTION_LABELS[section.type] : 'Other lines',
        lines: [line],
      })
    }
  }
  return groups
}

function sourceText(meta: CvMeta | null): string {
  if (!meta) return ''
  if (meta.kind === 'text') return 'Source: pasted text'
  return `Source: ${meta.filename ?? 'uploaded file'}`
}
