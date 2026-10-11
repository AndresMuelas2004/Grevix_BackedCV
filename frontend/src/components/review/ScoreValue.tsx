import { formatScore } from '../../lib/format'

interface ScoreValueProps {
  value: number | null
}

// A 0 to 100 score, or "Not scorable" when there is none.
export default function ScoreValue({ value }: ScoreValueProps) {
  if (value === null) return <>Not scorable</>
  return (
    <>
      {formatScore(value)}
      <small> / 100</small>
    </>
  )
}
