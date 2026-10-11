// The verdict in plain words for the top of the report, the must-have count and the strengths.
import type { AnalysisReport, VerdictLabel } from '../api/types'
import { firstSentence, normalizeQuestion, plainText } from './plainText'

export type Tone = 'red' | 'amber' | 'orange' | 'blue' | 'green'

export interface VerdictView {
  chip: string
  tone: Tone
  title: string
  sub: string
}

const TONES: Record<VerdictLabel, Tone> = {
  likely_screened_out: 'red',
  answer_questions: 'amber',
  long_shot: 'orange',
  stretch: 'blue',
  apply: 'green',
}

// pending: the questions still unanswered. answeredNo: a firm rule was answered No.
// blockReason: why the role is out of reach, if it is.
export function verdictView(
  analysis: AnalysisReport,
  pending: number,
  answeredNo: boolean,
  blockReason: string | null,
): VerdictView | null {
  const verdict = analysis.verdict
  if (!verdict) return null
  const tone = TONES[verdict.label]
  const fit = analysis.score?.fit ?? null
  const skills =
    fit === null
      ? 'Your skills could not be scored'
      : fit >= 75
        ? 'Your skills match well'
        : fit >= 55
          ? 'Your skills match in part'
          : 'Your skills match is low'
  switch (verdict.label) {
    case 'likely_screened_out':
      return {
        chip: 'Likely screened out',
        tone,
        title: answeredNo
          ? 'You answered No to a firm rule of this job, so this application will most likely be rejected.'
          : 'A firm rule in this posting will most likely get this application rejected.',
        sub: `${blockReason ? `${blockReason} ` : ''}Look for similar roles without this rule.`,
      }
    case 'answer_questions':
      return {
        chip: pending > 0 ? `${pending} ${pending === 1 ? 'answer' : 'answers'} needed` : 'Answers needed',
        tone,
        title:
          pending > 0
            ? `${skills}, but ${pending === 1 ? 'one line' : `${pending} lines`} in this posting could rule you out.`
            : `${skills}, but some lines in this posting could rule you out.`,
        sub:
          pending > 0
            ? `Answer the ${pending === 1 ? 'question' : `${pending} questions`} below. The verdict updates at once.`
            : 'The verdict updates as soon as your answers are saved.',
      }
    case 'long_shot':
      return {
        chip: 'Long shot',
        tone,
        title: 'This role is a long shot with the CV you have now.',
        sub: 'Some must-haves are missing or could rule you out. Apply only if you can fix the top of the list below.',
      }
    case 'stretch':
      return {
        chip: 'Worth a try: fix the gaps first',
        tone,
        title: 'You match a good part of this role, but not all of it.',
        sub: 'Fix the gaps below before you apply.',
      }
    case 'apply':
      return {
        chip: 'Worth applying',
        tone,
        title: 'Good match: your CV backs most of what they ask.',
        sub: 'Check the list below before you send it.',
      }
  }
}

// Why the role is out of reach: the verdict's first reason that is not a question.
export function blockReasonOf(analysis: AnalysisReport, questions: string[]): string | null {
  const verdict = analysis.verdict
  if (!verdict || verdict.label !== 'likely_screened_out') return null
  const asked = new Set(questions.map(normalizeQuestion))
  const labels = new Map((analysis.job?.requirements ?? []).map((req) => [req.id, req.label]))
  for (const reason of verdict.reasons) {
    if (asked.has(normalizeQuestion(reason.text))) continue
    const text = firstSentence(plainText(reason.text, labels))
    if (text !== '') return text
  }
  return null
}

// Must-haves the CV clearly shows: required, scored requirements (not gates, not left out).
export function mustHaveCount(analysis: AnalysisReport): { met: number; total: number } {
  const scored = (analysis.score?.contributions ?? []).filter(
    (item) => item.importance === 'required' && item.excluded_reason === null,
  )
  return { met: scored.filter((item) => item.status === 'met').length, total: scored.length }
}

// Requirements the CV clearly backs, required first. Answers to questions are not CV evidence.
export function strengths(analysis: AnalysisReport): { id: string; label: string }[] {
  const reqs = analysis.job?.requirements ?? []
  const met = reqs.filter((req) => {
    const assessment = analysis.assessments[req.id]
    return assessment?.status === 'met' && assessment.source !== 'user_answer'
  })
  const required = met.filter((req) => req.importance === 'required')
  const preferred = met.filter((req) => req.importance !== 'required')
  return [
    ...required.map((req) => ({ id: req.id, label: req.label })),
    ...preferred.map((req) => ({ id: req.id, label: `${req.label} (bonus)` })),
  ]
}
