import type { ScoreBreakdown } from '../api/types'
import { formatScore } from '../lib/format'
import './ScorePanel.css'

interface ScorePanelProps {
  score: ScoreBreakdown
}

export default function ScorePanel({ score }: ScorePanelProps) {
  const pendingPoints = Math.round(score.pending_points)
  return (
    <section className="score-panel card" aria-labelledby="score-title">
      <p className="eyebrow" id="score-title">
        Score
      </p>

      <div className="meters">
        <Meter label="Fit" value={score.fit} />
        <Meter label="Keyword coverage" value={score.coverage} />
      </div>

      {score.summary && <p className="score-summary">{score.summary}</p>}

      {pendingPoints > 0 && (
        <p className="notice notice-info">
          Pending: {pendingPoints} {pendingPoints === 1 ? 'point depends' : 'points depend'} on
          requirements your CV does not confirm yet.
        </p>
      )}

      <p className="score-note">Indicative, not an ATS grade. Every point is explained below.</p>
    </section>
  )
}

interface MeterProps {
  label: string
  value: number | null
}

function Meter({ label, value }: MeterProps) {
  const scored = value !== null
  const percent = value === null ? 0 : Math.min(100, Math.max(0, value))
  return (
    <div className="meter">
      <div className="meter-head">
        <span className="meter-label">{label}</span>
        <span className="meter-value">
          {value === null ? 'Not scorable' : formatScore(value)}
          {value !== null && <small> / 100</small>}
        </span>
      </div>
      <div
        className="meter-track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value !== null ? percent : undefined}
        aria-valuetext={scored ? `${formatScore(percent)} out of 100` : 'Not scorable'}
      >
        <div className="meter-fill" style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}
