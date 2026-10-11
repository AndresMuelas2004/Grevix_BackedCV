import type { ProgressEvent, ProgressStep } from '../api/types'

export const PROGRESS_STEPS: { id: ProgressStep; label: string }[] = [
  { id: 'prepare_cv', label: 'Reading your CV' },
  { id: 'prepare_job', label: 'Reading the job posting' },
  { id: 'match', label: 'Matching requirements' },
  { id: 'score', label: 'Scoring' },
]

export type StepState = 'waiting' | 'active' | 'done'

export interface ProgressState {
  steps: Record<ProgressStep, StepState>
  requirements: number | null
}

export function initialProgress(): ProgressState {
  return {
    steps: { prepare_cv: 'waiting', prepare_job: 'waiting', match: 'waiting', score: 'waiting' },
    requirements: null,
  }
}

// The backend never sends "done" for the match step, so any event for a later
// step also closes the earlier ones.
export function applyProgress(state: ProgressState, event: ProgressEvent): ProgressState {
  const index = PROGRESS_STEPS.findIndex((step) => step.id === event.step)
  if (index === -1) return state

  const steps = { ...state.steps }
  PROGRESS_STEPS.forEach((step, i) => {
    if (i < index) steps[step.id] = 'done'
    else if (i === index) steps[step.id] = event.status === 'done' ? 'done' : 'active'
  })

  const requirements =
    event.step === 'prepare_job' && event.status === 'done' && typeof event.requirements === 'number'
      ? event.requirements
      : state.requirements
  return { steps, requirements }
}
