import { useEffect } from 'react'
import type { CvLine, CvMeta, CvSection, ParsedCv } from '../api/types'
import { citationLabel, COMPUTED_FACT_LABEL } from '../lib/citations'
import { SECTION_LABELS } from '../lib/labels'
import './CVView.css'

interface CvViewProps {
  cv: ParsedCv | null
  meta: CvMeta | null
  selectedId: string | null
  // Line or fact IDs (L… or F…) cited as evidence by the selected requirement.
  highlightIds: string[]
  // Line IDs picked in the "How your CV reads" report. Shown with a "Noted" tag.
  noteIds?: string[]
  // Line IDs that a parse warning points at. Each gets a small warning marker.
  warnedIds?: string[]
}

interface LineGroup {
  key: string
  label: string
  lines: CvLine[]
}

export default function CvView({
  cv,
  meta,
  selectedId,
  highlightIds,
  noteIds = [],
  warnedIds = [],
}: CvViewProps) {
  const highlighted = new Set(highlightIds)
  const noted = new Set(noteIds)
  const warned = new Set(warnedIds)
  const groups = cv ? groupLines(cv) : []
  const readingOrder = cv ? [...cv.lines.map((line) => line.id), ...cv.facts.map((fact) => fact.id)] : []
  const firstEvidence = readingOrder.find((id) => highlighted.has(id)) ?? null
  const firstNote = readingOrder.find((id) => noted.has(id)) ?? null
  const scrollTarget = firstEvidence ?? firstNote
  const highlightKey = `${highlightIds.join('|')}#${noteIds.join('|')}`

  // Bring the first highlighted line into view whenever the highlight changes.
  useEffect(() => {
    if (!scrollTarget) return
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    document
      .getElementById(`cv-${scrollTarget}`)
      ?.scrollIntoView({ block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' })
  }, [scrollTarget, highlightKey])

  let hint: string | null = null
  if (noteIds.length === 0) {
    if (selectedId === null) {
      hint = 'Select a requirement to see its evidence highlighted here.'
    } else if (firstEvidence === null) {
      hint = 'This requirement has no evidence in your CV.'
    }
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
                    label={citationLabel(line.id)}
                    text={line.text}
                    evidence={highlighted.has(line.id)}
                    noted={noted.has(line.id)}
                    warned={warned.has(line.id)}
                  />
                ))}
              </ul>
            </div>
          ))}

          {cv.facts.length > 0 && (
            <div className="cv-group">
              <h3 className="cv-group-title">{COMPUTED_FACT_LABEL}</h3>
              <ul className="cv-lines">
                {cv.facts.map((fact) => (
                  <LineItem
                    key={fact.id}
                    id={fact.id}
                    label=""
                    text={fact.text}
                    evidence={highlighted.has(fact.id)}
                    noted={noted.has(fact.id)}
                    warned={warned.has(fact.id)}
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
  label: string // shown before the text: "line 39", or nothing for a computed fact
  text: string
  evidence: boolean
  noted: boolean
  warned: boolean
}

function LineItem({ id, label, text, evidence, noted, warned }: LineItemProps) {
  let className = 'cv-line'
  if (evidence) className += ' is-evidence'
  if (noted) className += ' is-noted'

  return (
    <li id={`cv-${id}`} className={className}>
      <span className="cv-id">{label}</span>
      <span className="cv-text">{text}</span>
      <span className="cv-tags">
        {warned && (
          <span className="cv-warn-mark">
            <span aria-hidden="true">!</span>
            <span className="visually-hidden">Problem reading this line</span>
          </span>
        )}
        {evidence && <span className="cv-tag">Evidence</span>}
        {noted && <span className="cv-tag cv-tag-note">Noted</span>}
      </span>
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
