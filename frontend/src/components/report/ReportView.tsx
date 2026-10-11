import { useState, type ReactNode } from 'react'
import type { AnalysisReport, RequirementAssessment } from '../../api/types'
import { problemLineIds } from '../../lib/parseWarnings'
import { useSaving } from '../../lib/saving'
import CvView from '../CVView'
import KnockoutQuestions from '../facts/KnockoutQuestions'
import HowComputed from '../HowComputed'
import ParseReport from '../parse/ParseReport'
import RequirementList from '../RequirementList'
import ScorePanel from '../ScorePanel'
import VerdictCard from '../VerdictCard'
import HiddenRisks from './HiddenRisks'
import './ReportView.css'

interface ReportViewProps {
  analysis: AnalysisReport
  onAnalysisChange: (next: AnalysisReport) => void
  // Shown under the verdict, e.g. the "Optimize my CV" button. Told whether a request is in flight,
  // so the controls that send one can be disabled.
  actions?: (busy: boolean) => ReactNode
}

// The report page. It owns the selected requirement and the lines highlighted from the parse
// report. Only one of the two is active at a time, so the CV view never shows both kinds.
export default function ReportView({ analysis, onAnalysisChange, actions }: ReportViewProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [highlightedLineIds, setHighlightedLineIds] = useState<string[]>([])
  // The answers and the toggles of this screen share one saving state: one request at a time.
  const saving = useSaving()

  const selected: RequirementAssessment | undefined =
    selectedId === null ? undefined : analysis.assessments[selectedId]
  const evidenceIds = selected ? selected.evidence.map((item) => item.ref) : []

  function selectRequirement(requirementId: string | null) {
    setSelectedId(requirementId)
    setHighlightedLineIds([])
  }

  function highlightLines(lineIds: string[]) {
    setHighlightedLineIds(lineIds)
    setSelectedId(null)
  }

  // Selects a requirement picked in the verdict, then moves the focus to its row (which scrolls it into view).
  function revealRequirement(requirementId: string) {
    selectRequirement(requirementId)
    window.requestAnimationFrame(() => {
      document.getElementById(`req-${requirementId}`)?.focus()
    })
  }

  return (
    <div className="report">
      {analysis.errors.length > 0 && (
        <p className="notice notice-warn" role="status">
          Some steps did not finish, so parts of this report may be incomplete.
        </p>
      )}

      <div className="report-top">
        <div className="report-verdict">
          {analysis.verdict && (
            <VerdictCard
              verdict={analysis.verdict}
              job={analysis.job}
              assessments={analysis.assessments}
              showQuestions={false}
              onSelectRequirement={revealRequirement}
            />
          )}
          {actions && <div className="report-actions">{actions(saving.busy)}</div>}
        </div>
        {analysis.score && <ScorePanel score={analysis.score} />}
      </div>

      <HiddenRisks analysis={analysis} saving={saving} onAnalysisChange={onAnalysisChange} />

      <div className="report-facts">
        <KnockoutQuestions
          analysis={analysis}
          saving={saving}
          onAnalysisChange={onAnalysisChange}
        />
        <ParseReport
          warnings={analysis.parse_warnings}
          lines={analysis.cv?.lines ?? []}
          highlightedLineIds={highlightedLineIds}
          onHighlight={highlightLines}
        />
      </div>

      <div className="report-grid">
        <RequirementList
          job={analysis.job}
          assessments={analysis.assessments}
          banners={analysis.banners}
          flags={analysis.flags}
          screeningFlags={analysis.screening_flags ?? []}
          recency={analysis.recency ?? {}}
          contributions={analysis.score?.contributions ?? []}
          selectedId={selectedId}
          onSelect={selectRequirement}
          inputs={{
            analysisId: analysis.analysis_id,
            excludedIds: analysis.excluded_ids,
            includedFlaggedIds: analysis.included_flagged_ids,
            saving,
            onChange: onAnalysisChange,
          }}
        />
        <CvView
          cv={analysis.cv}
          meta={analysis.cv_meta}
          selectedId={selectedId}
          highlightIds={evidenceIds}
          noteIds={highlightedLineIds}
          warnedIds={problemLineIds(analysis.parse_warnings)}
        />
      </div>

      <HowComputed usage={analysis.usage} />
    </div>
  )
}
