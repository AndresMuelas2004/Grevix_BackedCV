import type { AnalysisReport } from '../api/types'

export interface KnockoutItem {
  requirementId: string
  label: string
  question: string
  answer: boolean | null // the user's answer, or null while unanswered
}

// The screening questions to show: unknown requirements with a question, plus the ones the user
// already answered. An answered one no longer has status "unknown", so its answer keeps it listed.
export function knockoutItems(analysis: AnalysisReport): KnockoutItem[] {
  const answers = analysis.facts.answers ?? {}
  const labels = new Map((analysis.job?.requirements ?? []).map((req) => [req.id, req.label]))
  const items: KnockoutItem[] = []

  for (const assessment of Object.values(analysis.assessments)) {
    const question = assessment.question
    if (question === null) continue
    const answer: boolean | undefined = answers[assessment.requirement_id]
    if (assessment.status !== 'unknown' && answer === undefined) continue
    items.push({
      requirementId: assessment.requirement_id,
      label: labels.get(assessment.requirement_id) ?? assessment.requirement_id,
      question,
      answer: answer ?? null,
    })
  }
  return items
}
