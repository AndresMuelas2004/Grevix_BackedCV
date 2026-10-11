import type { AnalysisReport } from '../api/types'
import { knockoutItems } from './knockouts'
import { normalizeQuestion, plainText } from './plainText'

// One yes/no question of the report. The same question can come from a requirement and from a
// hidden risk: it is shown once, and its answer is saved under every ID that asks it.
export interface ReportQuestion {
  key: string // the normalized text
  text: string
  answerIds: string[] // requirement or hidden-risk IDs the answer is saved under
  answer: boolean | null // null while unanswered
}

// Every yes/no question the candidate can answer: the deal-breaker questions of the requirements,
// then the questions of the hidden risks. Answered ones stay listed, so an answer can be changed.
export function reportQuestions(analysis: AnalysisReport): ReportQuestion[] {
  const answers = analysis.facts.answers ?? {}
  const byKey = new Map<string, ReportQuestion>()
  const list: ReportQuestion[] = []

  function add(id: string, text: string, answer: boolean | null) {
    const key = normalizeQuestion(text)
    if (key === '') return
    const existing = byKey.get(key)
    if (existing) {
      if (!existing.answerIds.includes(id)) existing.answerIds.push(id)
      if (existing.answer === null) existing.answer = answer
      return
    }
    const question: ReportQuestion = { key, text: plainText(text), answerIds: [id], answer }
    byKey.set(key, question)
    list.push(question)
  }

  for (const item of knockoutItems(analysis)) add(item.requirementId, item.question, item.answer)

  for (const risk of analysis.hidden_risks ?? []) {
    if (risk.question === null) continue
    const saved: unknown = answers[risk.id]
    let answer: boolean | null = typeof saved === 'boolean' ? saved : null
    if (answer === null && risk.resolved) answer = true
    else if (answer === null && risk.confirmed) answer = false
    add(risk.id, risk.question, answer)
  }
  return list
}

export function unansweredCount(questions: ReportQuestion[]): number {
  return questions.filter((question) => question.answer === null).length
}
