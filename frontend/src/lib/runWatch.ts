import { getAnalysis } from '../api/client'
import type { AnalysisReport, ErrorBody } from '../api/types'
import { isNetworkError, toErrorBody } from './errors'
import { wait } from './wait'

// The step a run is in. A reload only has the analysis to tell it by.
export type RunStep = 'analysis' | 'optimize' | 'build'

// A running analysis is checked every 2 seconds, and every 5 seconds after the first minute.
const FAST_INTERVAL_MS = 2000
const SLOW_INTERVAL_MS = 5000
const SLOW_AFTER_MS = 60_000
// The wait gives up after three minutes. The run itself keeps going on the server.
const GIVE_UP_AFTER_MS = 180_000

export type WatchOutcome =
  | { kind: 'settled'; analysis: AnalysisReport } // paused, done or stalled: the run has stopped
  | { kind: 'timeout' }
  | { kind: 'failed'; error: ErrorBody }

// Checks an analysis until its run stops on the server. Resolves null when `signal` aborts first.
export async function watchRun(
  analysisId: string,
  signal: AbortSignal,
): Promise<WatchOutcome | null> {
  const started = Date.now()
  for (;;) {
    const elapsed = Date.now() - started
    if (elapsed >= GIVE_UP_AFTER_MS) return { kind: 'timeout' }
    await wait(elapsed < SLOW_AFTER_MS ? FAST_INTERVAL_MS : SLOW_INTERVAL_MS, signal).catch(
      () => undefined,
    )
    if (signal.aborted) return null
    try {
      const analysis = await getAnalysis(analysisId, signal)
      if (analysis.status !== 'running') return { kind: 'settled', analysis }
    } catch (error) {
      if (signal.aborted) return null
      // A dropped connection does not end the wait: the next check tries again.
      if (!isNetworkError(error)) return { kind: 'failed', error: toErrorBody(error) }
    }
  }
}
