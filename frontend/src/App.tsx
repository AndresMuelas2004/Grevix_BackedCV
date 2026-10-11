import { useRef, useState } from 'react'
import { ApiError, runAnalysis, type AnalysisEvent, type AnalysisInput } from './api/client'
import type { AnalysisReport, ErrorBody, RequirementAssessment } from './api/types'
import CvView from './components/CVView'
import InputForm from './components/InputForm'
import Progress from './components/Progress'
import RequirementList from './components/RequirementList'
import ScorePanel from './components/ScorePanel'
import VerdictCard from './components/VerdictCard'
import { EMPTY_DRAFT, type AnalysisDraft } from './lib/draft'
import { applyProgress, initialProgress, type ProgressState } from './lib/progress'

type View =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'report'; report: AnalysisReport }
  | { kind: 'error'; error: ErrorBody }

export default function App() {
  const [view, setView] = useState<View>({ kind: 'idle' })
  const [draft, setDraft] = useState<AnalysisDraft>(EMPTY_DRAFT)
  const [progress, setProgress] = useState<ProgressState>(initialProgress)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)

  async function start(input: AnalysisInput) {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setProgress(initialProgress())
    setSelectedId(null)
    setView({ kind: 'running' })

    const onEvent = (event: AnalysisEvent) => {
      if (controller.signal.aborted) return
      if (event.type === 'progress') {
        setProgress((previous) => applyProgress(previous, event.progress))
      } else if (event.type === 'report') {
        setView({ kind: 'report', report: event.report })
      } else if (event.type === 'error') {
        setView({ kind: 'error', error: event.error })
      }
    }

    try {
      await runAnalysis(input, onEvent, controller.signal)
    } catch (error) {
      if (!controller.signal.aborted) setView({ kind: 'error', error: toErrorBody(error) })
    }
  }

  // Cancels a running analysis (if any), clears the form and returns to the start.
  function startOver() {
    controllerRef.current?.abort()
    controllerRef.current = null
    setDraft(EMPTY_DRAFT)
    setSelectedId(null)
    setView({ kind: 'idle' })
  }

  // Returns to the form with its values kept, so the user can fix and resubmit.
  function editAndRetry() {
    setView({ kind: 'idle' })
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-inner brand">
          <h1 className="brand-name">BackedCV</h1>
          <p className="brand-tagline">
            Is this job worth applying to? Every point backed by your CV.
          </p>
        </div>
      </header>

      <main className="app-main">
        {view.kind === 'idle' && <InputForm draft={draft} onChange={setDraft} onSubmit={start} />}

        {view.kind === 'running' && (
          <>
            <Toolbar onStartOver={startOver} />
            <Progress state={progress} />
          </>
        )}

        {view.kind === 'error' && (
          <section className="card error-card" role="alert" aria-labelledby="error-title">
            <h2 id="error-title">{view.error.title}</h2>
            {view.error.detail && (
              <p className="error-detail">Details: {view.error.detail}</p>
            )}
            <div className="error-actions">
              <button type="button" className="btn btn-primary" onClick={editAndRetry}>
                Edit and try again
              </button>
              <button type="button" className="btn btn-secondary" onClick={startOver}>
                Start over
              </button>
            </div>
          </section>
        )}

        {view.kind === 'report' && (
          <>
            <Toolbar onStartOver={startOver} />
            <ReportView report={view.report} selectedId={selectedId} onSelect={setSelectedId} />
          </>
        )}
      </main>

      <footer className="app-footer">
        <div className="app-footer-inner">Indicative only. BackedCV never invents experience.</div>
      </footer>
    </div>
  )
}

function Toolbar({ onStartOver }: { onStartOver: () => void }) {
  return (
    <div className="toolbar">
      <button type="button" className="btn btn-secondary" onClick={onStartOver}>
        Start over
      </button>
    </div>
  )
}

interface ReportViewProps {
  report: AnalysisReport
  selectedId: string | null
  onSelect: (requirementId: string | null) => void
}

function ReportView({ report, selectedId, onSelect }: ReportViewProps) {
  const assessment: RequirementAssessment | undefined =
    selectedId !== null ? report.assessments[selectedId] : undefined
  const highlightIds = assessment ? assessment.evidence.map((item) => item.ref) : []

  return (
    <div className="report">
      {report.errors.length > 0 && (
        <p className="notice notice-warn" role="status">
          Some steps did not finish, so parts of this report may be incomplete.
        </p>
      )}

      <div className="report-top">
        {report.verdict && (
          <VerdictCard verdict={report.verdict} job={report.job} assessments={report.assessments} />
        )}
        {report.score && <ScorePanel score={report.score} />}
      </div>

      <div className="report-grid">
        <RequirementList
          job={report.job}
          assessments={report.assessments}
          banners={report.banners}
          flags={report.flags}
          contributions={report.score?.contributions ?? []}
          selectedId={selectedId}
          onSelect={onSelect}
        />
        <CvView
          cv={report.cv}
          meta={report.cv_meta}
          selectedId={selectedId}
          highlightIds={highlightIds}
        />
      </div>
    </div>
  )
}

// Errors from the request or the stream, as the error card shows them.
function toErrorBody(error: unknown): ErrorBody {
  if (error instanceof ApiError) {
    return { code: error.code, title: error.title, detail: error.detail }
  }
  return {
    code: 'unexpected',
    title: 'Something went wrong.',
    detail: error instanceof Error ? error.message : '',
  }
}
