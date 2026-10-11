import { PROGRESS_STEPS, type ProgressState, type StepState } from '../lib/progress'
import './Progress.css'

interface ProgressProps {
  state: ProgressState
}

const STATE_TEXT: Record<StepState, string> = {
  waiting: 'Waiting',
  active: 'In progress',
  done: 'Done',
}

export default function Progress({ state }: ProgressProps) {
  const { requirements } = state
  return (
    <section className="progress card" aria-labelledby="progress-title">
      <h2 id="progress-title">Checking your CV against the posting</h2>
      <div aria-live="polite">
        <ol className="progress-steps">
          {PROGRESS_STEPS.map((step, index) => {
            const status = state.steps[step.id]
            return (
              <li key={step.id} className={`progress-step is-${status}`}>
                <span className="step-marker" aria-hidden="true">
                  {status === 'done' ? '' : index + 1}
                </span>
                <span className="step-label">{step.label}</span>
                <span className="step-state">{STATE_TEXT[status]}</span>
                {step.id === 'prepare_job' && status === 'done' && requirements !== null && (
                  <span className="step-detail">
                    {requirements} {requirements === 1 ? 'requirement' : 'requirements'} found
                  </span>
                )}
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}
