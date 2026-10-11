// Display text for the backend's literal values. Keys are the backend's values.
import type {
  Badge,
  Category,
  Importance,
  KnockoutType,
  MatchType,
  SectionType,
  Status,
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
  alias: 'alias match',
  semantic: 'matched by meaning',
  inferred: 'inferred',
  user_answer: 'your answer',
}

export const FLAG_LABELS: Record<'R1' | 'R2', string> = {
  R1: 'Seniority mismatch',
  R2: 'Technology too new for the years asked',
}
