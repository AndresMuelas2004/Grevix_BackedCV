import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
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
import RunWatch from './components/RunWatch'
import { EMPTY_DRAFT, type AnalysisDraft } from './lib/draft'
import { describeFailure, friendlyText, type KnownCode } from './lib/errorMessages'
import { isBrokenConnection, toErrorBody } from './lib/errors'
import {
  PROGRESS_STEPS,
  applyProgress,
  initialProgress,
  type ProgressState,
  type StepState,
} from './lib/progress'
import type { RunStep } from './lib/runWatch'

type Flow =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'analyzing' }
  // A run still going on the server, found on a reload or after a stream broke.
  | { kind: 'waiting'; analysisId: string; step: RunStep }
  // The wait ran out. The run may still finish on the server.
  | { kind: 'timedOut' }
  | { kind: 'report'; analysis: AnalysisReport }
  | { kind: 'optimizing'; analysis: AnalysisReport }
  | { kind: 'review'; analysis: AnalysisReport; decisions: ReviewDecisions | null }
  | { kind: 'building'; analysis: AnalysisReport }
  | { kind: 'built'; analysis: AnalysisReport }
  // A run that stopped on the server. The analysis tells which step it stopped at (see stepOf).
  | { kind: 'stalled'; analysis: AnalysisReport }
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

const STALLED_ERRORS: Record<RunStep, KnownCode> = {
  analysis: 'analysis_failed',
  optimize: 'optimize_failed',
  build: 'build_failed',
}

// What a screen reader hears when a screen opens, in addition to the heading that takes the focus.
const SCREEN_NOTICE: Record<Flow['kind'], string> = {
  idle: 'Start a new check.',
  loading: 'Opening your analysis.',
  analyzing: 'Checking your CV against the posting.',
  waiting: 'Your check is still running.',
  timedOut: 'Stopped waiting for the check.',
  report: 'Report ready.',
  optimizing: 'Suggesting changes to your CV.',
  review: 'Review ready.',
  building: 'Building your new CV.',
  built: 'Build finished.',
  stalled: 'There is a problem.',
  error: 'There is a problem.',
}

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

  // A reload (or a link with ?analysis=) opens the analysis at the stage it is in, or waits for it
  // when the server is still working on it.
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

  // Moves the focus to the heading of each new screen, so keyboard and screen reader users start
  // there. The first screen is left alone: a page load should not take the focus.
  const shownKind = useRef(flow.kind)
  useEffect(() => {
    if (shownKind.current === flow.kind) return
    shownKind.current = flow.kind
    const heading = mainRef.current?.querySelector<HTMLElement>('[data-screen-heading]')
    const target = heading ?? mainRef.current
    target?.focus()
  }, [flow.kind])

  // Starts a run and cancels the one before it. Events of a cancelled run are ignored.
  function beginRun(): AbortSignal {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    return controller.signal
  }

  function stopRun() {
    controllerRef.current?.abort()
    controllerRef.current = null
    forgetAnalysis()
  }

  async function startAnalysis(input: AnalysisInput) {
    const signal = beginRun()
    setAnalysisProgress(initialProgress())
    setFlow({ kind: 'analyzing' })
    // The id the stream reported first, so a broken stream can be checked on the server.
    const run: { analysisId: string | null } = { analysisId: null }

    const onEvent = (event: AnalysisEvent) => {
      if (signal.aborted) return
      switch (event.type) {
        case 'created':
          run.analysisId = event.analysisId
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
      await showFailure(error, run.analysisId, signal, {
        kind: 'error',
        error: toErrorBody(error),
        analysis: null,
        decisions: null,
      })
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
      await showFailure(error, analysis.analysis_id, signal, {
        kind: 'error',
        error: toErrorBody(error),
        analysis,
        decisions: null,
      })
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
      await showFailure(error, analysis.analysis_id, signal, {
        kind: 'error',
        error: toErrorBody(error),
        analysis,
        decisions,
      })
    }
  }

  // Shows what a failed run left behind. A broken connection may have left the run going on the
  // server, so the analysis is read first: it shows the wait, or the step the run stopped at.
  // Otherwise, or when the analysis cannot be read, the stream's own error is shown.
  async function showFailure(
    error: unknown,
    analysisId: string | null,
    signal: AbortSignal,
    failed: Flow,
  ) {
    if (signal.aborted) return
    const recovered =
      analysisId !== null && isBrokenConnection(error)
        ? await flowFromServer(analysisId, signal)
        : null
    if (!signal.aborted) setFlow(recovered ?? failed)
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

  function analyzeAnotherPosting() {
    stopRun()
    setDraft((previous) => ({ ...previous, jobText: '' }))
    setFlow({ kind: 'idle' })
  }

  function retryStalled(analysis: AnalysisReport) {
    if (analysis.decisions) void startBuild(analysis, analysis.decisions)
    else if (analysis.verdict) void startOptimize(analysis)
    else editAndTryAgain()
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
            <h1 tabIndex={-1} data-screen-heading>
              Opening your analysis
            </h1>
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

      case 'waiting':
        return (
          <>
            <Toolbar onStartOver={startOver} />
            <RunWatch
              analysisId={flow.analysisId}
              step={flow.step}
              onSettled={(analysis) => setFlow(flowFor(analysis, analysis.decisions))}
              onTimeout={() => setFlow({ kind: 'timedOut' })}
              onFailed={(error) => setFlow({ kind: 'error', error, analysis: null, decisions: null })}
            />
          </>
        )

      case 'timedOut': {
        const text = friendlyText('still_running')
        return (
          <section className="card error-card" aria-labelledby="error-title">
            <h1 id="error-title" tabIndex={-1} data-screen-heading>
              {text.message}
            </h1>
            <p className="error-next">{text.next}</p>
            <div className="error-actions">
              <button type="button" className="btn btn-secondary" onClick={startOver}>
                Start over
              </button>
            </div>
          </section>
        )
      }

      case 'report': {
        const { analysis } = flow
        return (
          <>
            <Toolbar
              onStartOver={startOver}
              label="New analysis"
              context={reportContext(analysis)}
            />
            <ReportView
              analysis={analysis}
              onAnalysisChange={updateReport}
              onImprove={() => void startOptimize(analysis)}
              onAnotherPosting={analyzeAnotherPosting}
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
              onRetrySuggestions={() => startOptimize(analysis)}
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

      case 'stalled': {
        const { analysis } = flow
        const step = stepOf(analysis)
        return (
          <section className="card error-card" aria-labelledby="error-title">
            <h1 id="error-title" tabIndex={-1} data-screen-heading>
              {friendlyText(STALLED_ERRORS[step]).message}
            </h1>
            <div className="error-actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => retryStalled(analysis)}
              >
                {step === 'analysis' ? 'Edit and try again' : 'Try again'}
              </button>
              <button type="button" className="btn btn-secondary" onClick={startOver}>
                Start over
              </button>
            </div>
          </section>
        )
      }

      case 'error': {
        const { error, analysis, decisions } = flow
        const failure = describeFailure(error)
        return (
          <section className="card error-card" aria-labelledby="error-title">
            <h1 id="error-title" tabIndex={-1} data-screen-heading>
              {failure.message}
            </h1>
            {failure.next && <p className="error-next">{failure.next}</p>}
            {failure.detail && <p className="error-detail">Details: {failure.detail}</p>}
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
          <p className="brand-name">
            Backed<span className="brand-accent">CV</span>
          </p>
          <p className="brand-tagline">
            Is this job worth applying to? Every point backed by your CV.
          </p>
        </div>
      </header>

      <main className="app-main" ref={mainRef} tabIndex={-1}>
        <p className="visually-hidden" role="status">
          {SCREEN_NOTICE[flow.kind]}
        </p>
        {renderScreen()}
      </main>

      <footer className="app-footer">
        <div className="app-footer-inner">Indicative only. BackedCV never invents experience.</div>
      </footer>
    </div>
  )
}

interface ToolbarProps {
  onStartOver: () => void
  label?: string
  context?: string | null // what is being checked, e.g. "Platform Engineer · Sable Creek"
}

function Toolbar({ onStartOver, label = 'Start over', context = null }: ToolbarProps) {
  return (
    <div className={context ? 'toolbar toolbar-context' : 'toolbar'}>
      {context && <p className="toolbar-text">{context}</p>}
      <button type="button" className="btn btn-secondary" onClick={onStartOver}>
        {label}
      </button>
    </div>
  )
}

function reportContext(analysis: AnalysisReport): string | null {
  const job = analysis.job
  const name = analysis.cv?.contact.name?.value ?? null
  const parts = [job?.title, job?.company, job?.location].filter(
    (part): part is string => typeof part === 'string' && part.trim() !== '',
  )
  if (name) parts.push(`CV: ${name}`)
  return parts.length > 0 ? parts.join(' · ') : null
}

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

function flowFor(analysis: AnalysisReport, decisions: ReviewDecisions | null): Flow {
  if (analysis.status === 'running') {
    return { kind: 'waiting', analysisId: analysis.analysis_id, step: stepOf(analysis) }
  }
  if (analysis.status === 'stalled') return { kind: 'stalled', analysis }
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

// The step a run is in, as the analysis shows it: the build once decisions were sent, the
// suggestions once the report has its verdict, and the analysis before that.
function stepOf(analysis: AnalysisReport): RunStep {
  if (analysis.decisions !== null) return 'build'
  return analysis.verdict === null ? 'analysis' : 'optimize'
}

async function flowFromServer(analysisId: string, signal: AbortSignal): Promise<Flow | null> {
  try {
    const analysis = await getAnalysis(analysisId, signal)
    return flowFor(analysis, analysis.decisions)
  } catch {
    return null
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

// The requirement count appears once the posting is read.
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
