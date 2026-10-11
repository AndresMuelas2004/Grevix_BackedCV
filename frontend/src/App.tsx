import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  ApiError,
  getAnalysis,
  runAnalysis,
  runBuild,
  runOptimize,
  type AnalysisEvent,
  type AnalysisInput,
  type BuildEvent,
  type OptimizeEvent,
} from './api/client'
import type {
  AnalysisReport,
  BuildStep,
  ErrorBody,
  OptimizeStep,
  ProgressEvent,
  ReviewDecisions,
} from './api/types'
import BuildScreen from './components/build/BuildScreen'
import InputForm from './components/InputForm'
import Progress, { type ProgressRow } from './components/Progress'
import ReportView from './components/report/ReportView'
import ReviewScreen from './components/review/ReviewScreen'
import { EMPTY_DRAFT, type AnalysisDraft } from './lib/draft'
import {
  PROGRESS_STEPS,
  applyProgress,
  initialProgress,
  type ProgressState,
  type StepState,
} from './lib/progress'

// The screens of the flow. Each stream (analysis, optimize, build) has its own progress.
type Flow =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'analyzing' }
  | { kind: 'report'; analysis: AnalysisReport }
  | { kind: 'optimizing'; analysis: AnalysisReport }
  | { kind: 'review'; analysis: AnalysisReport; decisions: ReviewDecisions | null }
  | { kind: 'building'; analysis: AnalysisReport }
  | { kind: 'built'; analysis: AnalysisReport }
  | {
      kind: 'error'
      error: ErrorBody
      analysis: AnalysisReport | null
      decisions: ReviewDecisions | null // the choices of a failed build, to restore on the review
    }

const ANALYSIS_PARAM = 'analysis'

const OPTIMIZE_STEPS: readonly { id: OptimizeStep; label: string }[] = [
  { id: 'suggest', label: 'Suggesting' },
  { id: 'verify', label: 'Verifying' },
]

const BUILD_STEPS: readonly { id: BuildStep; label: string }[] = [
  { id: 'build', label: 'Building' },
  { id: 'checks', label: 'Checking' },
]

const NOT_READY: ErrorBody = {
  code: 'not_ready',
  title: 'This analysis has no report yet.',
  detail: 'It may still be running. Start over to check the job again.',
}

export default function App() {
  const [flow, setFlow] = useState<Flow>(initialFlow)
  const [draft, setDraft] = useState<AnalysisDraft>(EMPTY_DRAFT)
  const [analysisProgress, setAnalysisProgress] = useState<ProgressState>(initialProgress)
  const [optimizeEvent, setOptimizeEvent] = useState<ProgressEvent<OptimizeStep> | null>(null)
  const [buildEvent, setBuildEvent] = useState<ProgressEvent<BuildStep> | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const mainRef = useRef<HTMLElement>(null)

  // A reload (or a link with ?analysis=) opens the analysis at the stage it is in.
  useEffect(() => {
    const id = readAnalysisId()
    if (!id) return
    // Dropped when the user has left this analysis (Start over, or another run) while it loaded.
    const stillWanted = () => readAnalysisId() === id
    getAnalysis(id)
      .then((analysis) => {
        if (stillWanted()) setFlow(flowFor(analysis, analysis.decisions))
      })
      .catch((error: unknown) => {
        if (stillWanted()) {
          setFlow({ kind: 'error', error: toErrorBody(error), analysis: null, decisions: null })
        }
      })
  }, [])

  // Moves the focus to each new screen, so keyboard and screen reader users start there.
  useEffect(() => {
    mainRef.current?.focus()
  }, [flow.kind])

  // Starts a run and cancels the one before it. Events of a cancelled run are ignored.
  function beginRun(): AbortSignal {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    return controller.signal
  }

  // Cancels the run in progress, if any, and forgets the analysis in the address bar.
  function stopRun() {
    controllerRef.current?.abort()
    controllerRef.current = null
    forgetAnalysis()
  }

  async function startAnalysis(input: AnalysisInput) {
    const signal = beginRun()
    setAnalysisProgress(initialProgress())
    setFlow({ kind: 'analyzing' })

    const onEvent = (event: AnalysisEvent) => {
      if (signal.aborted) return
      switch (event.type) {
        case 'created':
          rememberAnalysis(event.analysisId)
          break
        case 'progress': {
          const progress = event.progress
          setAnalysisProgress((previous) => applyProgress(previous, progress))
          break
        }
        case 'report':
          setFlow({ kind: 'report', analysis: event.report })
          break
        case 'error':
          setFlow({ kind: 'error', error: event.error, analysis: null, decisions: null })
          break
      }
    }

    try {
      await runAnalysis(input, onEvent, signal)
    } catch (error) {
      if (!signal.aborted) {
        setFlow({ kind: 'error', error: toErrorBody(error), analysis: null, decisions: null })
      }
    }
  }

  async function startOptimize(analysis: AnalysisReport) {
    const signal = beginRun()
    setOptimizeEvent(null)
    setFlow({ kind: 'optimizing', analysis })

    const onEvent = (event: OptimizeEvent) => {
      if (signal.aborted) return
      switch (event.type) {
        case 'progress':
          setOptimizeEvent(event.progress)
          break
        case 'suggestions':
          setFlow({ kind: 'review', analysis: event.report, decisions: null })
          break
        case 'error':
          setFlow({ kind: 'error', error: event.error, analysis, decisions: null })
          break
      }
    }

    try {
      await runOptimize(analysis.analysis_id, onEvent, signal)
    } catch (error) {
      if (!signal.aborted) {
        setFlow({ kind: 'error', error: toErrorBody(error), analysis, decisions: null })
      }
    }
  }

  async function startBuild(analysis: AnalysisReport, decisions: ReviewDecisions) {
    const signal = beginRun()
    setBuildEvent(null)
    setFlow({ kind: 'building', analysis })

    const onEvent = (event: BuildEvent) => {
      if (signal.aborted) return
      switch (event.type) {
        case 'progress':
          setBuildEvent(event.progress)
          break
        case 'built':
          setFlow({ kind: 'built', analysis: event.report })
          break
        case 'error':
          setFlow({ kind: 'error', error: event.error, analysis, decisions })
          break
      }
    }

    try {
      await runBuild(analysis.analysis_id, decisions, onEvent, signal)
    } catch (error) {
      if (!signal.aborted) {
        setFlow({ kind: 'error', error: toErrorBody(error), analysis, decisions })
      }
    }
  }

  function startOver() {
    stopRun()
    setDraft(EMPTY_DRAFT)
    setFlow({ kind: 'idle' })
  }

  // Returns to the form with its values kept, so the user can fix and resubmit.
  function editAndTryAgain() {
    stopRun()
    setFlow({ kind: 'idle' })
  }

  // The report and the review can change while their screen is open (answers, verified edits).
  // Only the screen that is open takes the newest version.
  function updateReport(next: AnalysisReport) {
    setFlow((previous) => (previous.kind === 'report' ? { ...previous, analysis: next } : previous))
  }

  function updateReview(next: AnalysisReport) {
    setFlow((previous) => (previous.kind === 'review' ? { ...previous, analysis: next } : previous))
  }

  function renderScreen(): ReactNode {
    switch (flow.kind) {
      case 'idle':
        return <InputForm draft={draft} onChange={setDraft} onSubmit={startAnalysis} />

      case 'loading':
        return (
          <section className="card loading-card" aria-live="polite">
            <h2>Opening your analysis</h2>
          </section>
        )

      case 'analyzing':
        return (
          <>
            <Toolbar onStartOver={startOver} />
            <Progress
              title="Checking your CV against the posting"
              rows={analysisRows(analysisProgress)}
            />
          </>
        )

      case 'report': {
        const { analysis } = flow
        return (
          <>
            <Toolbar onStartOver={startOver} />
            <ReportView
              analysis={analysis}
              onAnalysisChange={updateReport}
              actions={
                <div className="optimize-action">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={analysis.stage !== 'report_ready'}
                    onClick={() => startOptimize(analysis)}
                  >
                    Optimize my CV
                  </button>
                  <p className="optimize-hint">
                    Suggests rewording, skills and a summary. Each one is checked against your CV.
                  </p>
                </div>
              }
            />
          </>
        )
      }

      case 'optimizing':
        return (
          <>
            <Toolbar onStartOver={startOver} />
            <Progress
              title="Suggesting changes to your CV"
              rows={stepRows(OPTIMIZE_STEPS, optimizeEvent)}
            />
          </>
        )

      case 'review': {
        const { analysis, decisions } = flow
        return (
          <>
            <Toolbar onStartOver={startOver} />
            <ReviewScreen
              analysis={analysis}
              initialDecisions={decisions}
              onAnalysisChange={updateReview}
              onBuild={(choices) => startBuild(analysis, choices)}
            />
          </>
        )
      }

      case 'building':
        return (
          <>
            <Toolbar onStartOver={startOver} />
            <Progress title="Building your new CV" rows={stepRows(BUILD_STEPS, buildEvent)} />
          </>
        )

      case 'built':
        return <BuildScreen analysis={flow.analysis} onStartOver={startOver} />

      case 'error': {
        const { error, analysis, decisions } = flow
        return (
          <section className="card error-card" role="alert" aria-labelledby="error-title">
            <h2 id="error-title">{error.title}</h2>
            {error.detail && <p className="error-detail">Details: {error.detail}</p>}
            <div className="error-actions">
              {analysis ? (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => setFlow(flowFor(analysis, decisions ?? analysis.decisions))}
                >
                  {backLabel(analysis)}
                </button>
              ) : (
                <button type="button" className="btn btn-primary" onClick={editAndTryAgain}>
                  Edit and try again
                </button>
              )}
              <button type="button" className="btn btn-secondary" onClick={startOver}>
                Start over
              </button>
            </div>
          </section>
        )
      }
    }
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

      <main className="app-main" ref={mainRef} tabIndex={-1}>
        {renderScreen()}
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

// The analysis id in the address bar (?analysis=...), or null.
function readAnalysisId(): string | null {
  return new URLSearchParams(window.location.search).get(ANALYSIS_PARAM) || null
}

// Keeps the analysis id in the address bar, so a reload opens the same analysis.
function rememberAnalysis(id: string) {
  const url = new URL(window.location.href)
  url.searchParams.set(ANALYSIS_PARAM, id)
  window.history.replaceState(null, '', url)
}

function forgetAnalysis() {
  const url = new URL(window.location.href)
  if (!url.searchParams.has(ANALYSIS_PARAM)) return
  url.searchParams.delete(ANALYSIS_PARAM)
  window.history.replaceState(null, '', url)
}

function initialFlow(): Flow {
  return readAnalysisId() ? { kind: 'loading' } : { kind: 'idle' }
}

// The screen for an analysis, from the stage it is at.
function flowFor(analysis: AnalysisReport, decisions: ReviewDecisions | null): Flow {
  switch (analysis.stage) {
    case 'review_ready':
      return { kind: 'review', analysis, decisions }
    case 'built':
      return { kind: 'built', analysis }
    case 'report_ready':
      return { kind: 'report', analysis }
    case null:
      return { kind: 'error', error: NOT_READY, analysis: null, decisions: null }
  }
}

function backLabel(analysis: AnalysisReport): string {
  switch (analysis.stage) {
    case 'review_ready':
      return 'Back to the review'
    case 'built':
      return 'Back to the new CV'
    default:
      return 'Back to the report'
  }
}

// Rows of the analysis progress. The requirement count appears once the posting is read.
function analysisRows(progress: ProgressState): ProgressRow[] {
  const count = progress.requirements
  return PROGRESS_STEPS.map((step) => ({
    label: step.label,
    state: progress.steps[step.id],
    detail:
      step.id === 'prepare_job' && progress.steps.prepare_job === 'done' && count !== null
        ? `${count} ${count === 1 ? 'requirement' : 'requirements'} found`
        : undefined,
  }))
}

// Rows of a stream whose steps run in order: every step before the latest event is done.
function stepRows<Step extends string>(
  steps: readonly { id: Step; label: string }[],
  latest: ProgressEvent<Step> | null,
): ProgressRow[] {
  const current = latest ? steps.findIndex((step) => step.id === latest.step) : -1
  return steps.map((step, index) => {
    let state: StepState = 'waiting'
    if (index < current) state = 'done'
    else if (index === current && latest) state = latest.status === 'done' ? 'done' : 'active'
    return { label: step.label, state }
  })
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
