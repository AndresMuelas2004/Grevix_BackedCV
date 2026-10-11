// The input form's values and their validation. Limits match the backend
// (routes/analyses.py and ingestion/reader.py).
import type { AnalysisInput } from '../api/client'
import { formatNumber } from './format'

export const MIN_JOB_CHARS = 150
export const MAX_JOB_CHARS = 20_000
export const MAX_FILE_BYTES = 4 * 1024 * 1024

export const ACCEPTED_FILE_TYPES =
  '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

export type CvMode = 'file' | 'text'

export interface AnalysisDraft {
  cvMode: CvMode
  cvFile: File | null
  cvText: string
  jobText: string
}

export const EMPTY_DRAFT: AnalysisDraft = {
  cvMode: 'file',
  cvFile: null,
  cvText: '',
  jobText: '',
}

export interface DraftProblems {
  cv: string | null
  job: string | null
}

export function fileProblem(file: File): string | null {
  if (!/\.(pdf|docx)$/i.test(file.name)) return 'Upload a PDF or DOCX file.'
  if (file.size === 0) return 'This file is empty.'
  if (file.size > MAX_FILE_BYTES) return 'This file is larger than 4 MB.'
  return null
}

export function findProblems(draft: AnalysisDraft): DraftProblems {
  let cv: string | null = null
  if (draft.cvMode === 'file') {
    if (!draft.cvFile) cv = 'Upload your CV as a PDF or DOCX file, or paste its text instead.'
  } else if (draft.cvText.trim() === '') {
    cv = 'Paste the text of your CV, or upload a file instead.'
  }

  const length = draft.jobText.trim().length
  let job: string | null = null
  if (length === 0) {
    job = 'Paste the job posting you want to check.'
  } else if (length < MIN_JOB_CHARS) {
    job = `The posting is too short. Paste the full posting: at least ${formatNumber(MIN_JOB_CHARS)} characters.`
  } else if (length > MAX_JOB_CHARS) {
    job = `Job postings are limited to ${formatNumber(MAX_JOB_CHARS)} characters. Remove ${formatNumber(length - MAX_JOB_CHARS)} characters to continue.`
  }
  return { cv, job }
}

// Only call this when findProblems reports no problems.
export function toAnalysisInput(draft: AnalysisDraft): AnalysisInput | null {
  const jobText = draft.jobText.trim()
  if (draft.cvMode === 'file') {
    return draft.cvFile ? { cv: { file: draft.cvFile }, jobText } : null
  }
  return { cv: { text: draft.cvText }, jobText }
}
