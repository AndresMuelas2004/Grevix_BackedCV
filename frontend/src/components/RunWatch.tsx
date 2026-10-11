import { useEffect, useEffectEvent } from 'react'
import type { AnalysisReport, ErrorBody } from '../api/types'
import { watchRun, type RunStep } from '../lib/runWatch'
import Progress from './Progress'

const STEP_TITLES: Record<RunStep, string> = {
  analysis: 'Checking your CV against the posting',
  optimize: 'Suggesting changes to your CV',
  build: 'Building your new CV',
}

interface RunWatchProps {
  analysisId: string
  step: RunStep
  onSettled: (analysis: AnalysisReport) => void // the run has stopped: paused, done or stalled
  onTimeout: () => void
  onFailed: (error: ErrorBody) => void
}

// The progress screen of a run that is still going on the server. It checks the analysis until the
// run stops, then hands over. The checks stop when the screen goes away.
export default function RunWatch({
  analysisId,
  step,
  onSettled,
  onTimeout,
  onFailed,
}: RunWatchProps) {
  // Effect events always call the latest callbacks, without restarting the checks.
  const settle = useEffectEvent(onSettled)
  const timeOut = useEffectEvent(onTimeout)
  const fail = useEffectEvent(onFailed)

  useEffect(() => {
    const controller = new AbortController()
    void watchRun(analysisId, controller.signal).then((outcome) => {
      if (outcome === null || controller.signal.aborted) return
      if (outcome.kind === 'settled') settle(outcome.analysis)
      else if (outcome.kind === 'timeout') timeOut()
      else fail(outcome.error)
    })
    return () => controller.abort()
  }, [analysisId])

  return <Progress title={STEP_TITLES[step]} note="Still working on it..." />
}
