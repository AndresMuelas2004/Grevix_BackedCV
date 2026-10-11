import type { UsageTotal } from '../api/types'
import { formatNumber, formatUsd } from '../lib/format'
import './HowComputed.css'

const REPOSITORY_URL = 'https://github.com/AndresMuelas2004/Grevix_BackedCV'
const SCORING_URL = 'https://github.com/AndresMuelas2004/Grevix_BackedCV/blob/main/docs/scoring.md'

interface HowComputedProps {
  usage: UsageTotal
}

// A panel, closed by default, at the foot of the report, review and built screens. It says which
// models ran, what they cost, and how the results are made.
export default function HowComputed({ usage }: HowComputedProps) {
  const models = usage.models.filter((model) => model !== '')
  return (
    <details className="how-computed card">
      <summary>How this was computed</summary>

      <div className="how-body">
        <dl className="how-facts">
          <div>
            <dt>Models</dt>
            <dd>{models.length > 0 ? models.join(', ') : 'No model was called'}</dd>
          </div>
          <div>
            <dt>Model calls</dt>
            <dd>
              {formatNumber(usage.calls)} {usage.calls === 1 ? 'call' : 'calls'},{' '}
              {formatNumber(usage.cached_calls)} reused from an earlier run
            </dd>
          </div>
          <div>
            <dt>Text sent and received</dt>
            <dd>
              {formatNumber(usage.input_tokens)} sent, {formatNumber(usage.output_tokens)} received
            </dd>
          </div>
          <div>
            <dt>Cost</dt>
            <dd>{formatUsd(usage.cost_usd)}</dd>
          </div>
        </dl>

        <p>
          The score is computed in code from published weights.{' '}
          <a href={SCORING_URL}>Read the scoring rules</a>.
        </p>
        <p>
          Every suggestion passes automatic checks and a second AI check before you can accept it.
        </p>
        <p>The files you upload are not stored. Analyses are deleted after 24 hours.</p>
        <p>
          Source code: <a href={REPOSITORY_URL}>Grevix_BackedCV on GitHub</a>.
        </p>
      </div>
    </details>
  )
}
