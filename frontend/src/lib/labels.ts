// Display text for the backend's literal values.
import type {
  Badge,
  BarrierKind,
  Category,
  GateName,
  Importance,
  KnockoutType,
  MatchType,
  ParseWarning,
  RiskLevel,
  SectionType,
  Status,
  SuggestionKind,
} from '../api/types'

export const STATUS_LABELS: Record<Status, string> = {
  met: 'Met',
  partial: 'Partial',
  missing: 'Missing',
  unknown: 'Unknown',
}

export const CATEGORY_LABELS: Record<Category, string> = {
  hard_skill: 'Hard skill',
  soft_skill: 'Soft skill',
  experience_years: 'Years of experience',
  job_title: 'Job title',
  education: 'Education',
  certification_license: 'Certification or license',
  language: 'Language',
  work_authorization: 'Work authorization',
  location: 'Location',
  clearance: 'Security clearance',
  availability: 'Availability',
  other: 'Other',
}

export const IMPORTANCE_LABELS: Record<Importance, string> = {
  required: 'Required',
  preferred: 'Preferred',
}

export const KNOCKOUT_LABELS: Record<KnockoutType, string> = {
  work_authorization: 'work authorization',
  location: 'location',
  language: 'language',
  certification_license: 'certification or license',
  experience_years: 'years of experience',
  education: 'education',
  clearance: 'security clearance',
  availability: 'availability',
}

export const BADGE_LABELS: Record<Badge, string> = {
  tailor_first: 'Tailor your CV first',
  screening_risk: 'Screening risk',
  posting_red_flags: 'Posting red flags',
}

export const SUGGESTION_KIND_LABELS: Record<SuggestionKind, string> = {
  align_wording: 'Align wording',
  add_skill: 'Add skill',
  tailor_summary: 'Tailor summary',
}

export const RISK_LEVEL_LABELS: Record<RiskLevel, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

// "composite" is a risk that combines several others.
export const BARRIER_KIND_LABELS: Record<BarrierKind | 'composite', string> = {
  work_authorization: 'Work permit',
  location: 'Location',
  recency: 'Recency rule',
  graduation_window: 'Graduation window',
  language: 'Language',
  clearance: 'Clearance',
  availability: 'Availability',
  other: 'Other',
  composite: 'Combined risk',
}

// The gate's passes, as the user reads the one that failed.
export const GATE_LABELS: Record<GateName, string> = {
  backed: 'Backed by your CV',
  recent_enough: 'Recent enough for the posting',
  not_blocked: 'Not blocked by a barrier in the posting',
}

export const SECTION_LABELS: Record<SectionType, string> = {
  contact: 'Contact',
  summary: 'Summary',
  experience: 'Experience',
  education: 'Education',
  skills: 'Skills',
  projects: 'Projects',
  certifications: 'Certifications',
  languages: 'Languages',
  other: 'Other',
}

export const MATCH_LABELS: Record<MatchType, string> = {
  exact: 'exact match',
  alias: 'matched by another name',
  semantic: 'matched by meaning',
  inferred: 'inferred',
  user_answer: 'your answer',
}

export const FLAG_LABELS: Record<'R1' | 'R2', string> = {
  R1: 'Seniority mismatch',
  R2: 'Technology too new for the years asked',
}

export const SEVERITY_LABELS: Record<ParseWarning['severity'], string> = {
  error: 'Error',
  warning: 'Warning',
  info: 'Info',
}

// Plain words for why a requirement is left out of Fit (its contribution's excluded_reason).
// Reasons can be joined by the backend, e.g. "flagged_R1+R2".
export function describeExclusion(reason: string): string {
  if (reason === 'not_relevant') return 'You marked it as not relevant.'
  if (reason === 'gate') {
    return 'It is a screening question: it gives no points, but it can change the verdict.'
  }
  if (reason.startsWith('flagged_')) {
    const rules = reason.slice('flagged_'.length).split('+').filter(isFlagRule)
    if (rules.length > 0) {
      const names = rules.map((rule) => FLAG_LABELS[rule]).join(' and ')
      return `Left out because it was flagged (${names}). Choose "Count it anyway" to include it.`
    }
  }
  return 'It is left out of Fit.'
}

function isFlagRule(value: string): value is keyof typeof FLAG_LABELS {
  return value === 'R1' || value === 'R2'
}
