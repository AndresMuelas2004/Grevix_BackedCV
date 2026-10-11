import { useState, type ReactNode } from 'react'
import type { AnalysisReport, RequirementAssessment } from '../../api/types'
import { problemLineIds } from '../../lib/parseWarnings'
import CvView from '../CVView'
import KnockoutQuestions from '../facts/KnockoutQuestions'
import ParseReport from '../parse/ParseReport'
import RequirementList from '../RequirementList'
import ScorePanel from '../ScorePanel'
import VerdictCard from '../VerdictCard'
import './ReportView.css'

interface ReportViewProps {
  analysis: AnalysisReport
  onAnalysisChange: (next: AnalysisReport) => void
  // Shown under the verdict, e.g. the "Optimize my CV" button.
  actions?: ReactNode
}

// The report page. It owns the selected requirement and the lines highlighted from the parse
// report. Only one of the two is active at a time, so the CV view never shows both kinds.
export default function ReportView({ analysis, onAnalysisChange, actions }: ReportViewProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [highlightedLineIds, setHighlightedLineIds] = useState<string[]>([])

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
            />
          )}
          {actions && <div className="report-actions">{actions}</div>}
        </div>
        {analysis.score && <ScorePanel score={analysis.score} />}
      </div>

      <div className="report-facts">
        <KnockoutQuestions analysis={analysis} onAnalysisChange={onAnalysisChange} />
        <ParseReport
          warnings={analysis.parse_warnings}
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
          contributions={analysis.score?.contributions ?? []}
          selectedId={selectedId}
          onSelect={selectRequirement}
          inputs={{
            analysisId: analysis.analysis_id,
            excludedIds: analysis.excluded_ids,
            includedFlaggedIds: analysis.included_flagged_ids,
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
    </div>
  )
}
