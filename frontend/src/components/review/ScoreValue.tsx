import { formatScore } from '../../lib/format'

interface ScoreValueProps {
  value: number | null
}

export default function ScoreValue({ value }: ScoreValueProps) {
  if (value === null) return <>Not scorable</>
  return (
    <>
      {formatScore(value)}
      <small> / 100</small>
    </>
  )
}
