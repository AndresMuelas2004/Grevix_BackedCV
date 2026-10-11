import type { StepState } from '../lib/progress'
import './Progress.css'

// One step of a progress list. `detail` is optional text shown under the step.
export interface ProgressRow {
  label: string
  state: StepState
  detail?: string
}

interface ProgressProps {
  title: string
  rows?: ProgressRow[] // left out when the steps are not known, e.g. for a run found on reload
  note?: string // a line under the title
}

const STATE_TEXT: Record<StepState, string> = {
  waiting: 'Waiting',
  active: 'In progress',
  done: 'Done',
}

export default function Progress({ title, rows, note }: ProgressProps) {
  return (
    <section className="progress card" aria-labelledby="progress-title">
      <h2 id="progress-title" tabIndex={-1} data-screen-heading>
        {title}
      </h2>
      {note && <p className="notice notice-info">{note}</p>}
      {rows && (
        <div aria-live="polite">
          <ol className="progress-steps">
            {rows.map((row, index) => (
              <li key={row.label} className={`progress-step is-${row.state}`}>
                <span className="step-marker" aria-hidden="true">
                  {row.state === 'done' ? '' : index + 1}
                </span>
                <span className="step-label">{row.label}</span>
                <span className="step-state">{STATE_TEXT[row.state]}</span>
                {row.detail && <span className="step-detail">{row.detail}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}
