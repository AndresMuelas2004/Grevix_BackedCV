// Mirrors the backend models (backend/src/backedcv/domain/models) and the
// report projection (backend/src/backedcv/api/projection.py).
// Field names stay in the backend's snake_case on purpose.

// ---- CV as read by the backend ------------------------------------------

export type LineSource = 'body' | 'header' | 'footer' | 'textbox' | 'table'

export type SectionType =
  | 'contact'
  | 'summary'
  | 'experience'
  | 'education'
  | 'skills'
  | 'projects'
  | 'certifications'
  | 'languages'
  | 'other'

export type EntryKind = 'job' | 'education' | 'project'

export interface CvLine {
  id: string // L001, L002, ...
  text: string
  page: number
  source: LineSource
  bold: boolean
  size: number | null
}

export interface ComputedFact {
  id: string // F01, F02, ...
  text: string
  derived_from: string[]
}

export interface CvSection {
  id: string
  heading_line_id: string | null
  type: SectionType
  line_ids: string[]
}

export interface CvEntry {
  id: string
  section_id: string
  kind: EntryKind
  title: string | null
  organization: string | null
  location: string | null
  start: string | null
  end: string | null
  date_source: 'parser' | 'model' | 'none'
  line_ids: string[]
}

export interface ContactField {
  value: string
  line_id: string
}

export interface Contact {
  name: ContactField | null
  email: ContactField | null
  phone: ContactField | null
  location: ContactField | null
  links: ContactField[]
}

export interface ParsedCv {
  lines: CvLine[]
  facts: ComputedFact[]
  sections: CvSection[]
  entries: CvEntry[]
  contact: Contact
  total_years: number | null
}

// ---- Job posting -----------------------------------------------------------

export type Category =
  | 'hard_skill'
  | 'soft_skill'
  | 'experience_years'
  | 'job_title'
  | 'education'
  | 'certification_license'
  | 'language'
  | 'work_authorization'
  | 'location'
  | 'clearance'
  | 'availability'
  | 'other'

export type Importance = 'required' | 'preferred'

export type KnockoutType =
  | 'work_authorization'
  | 'location'
  | 'language'
  | 'certification_license'
  | 'experience_years'
  | 'education'
  | 'clearance'
  | 'availability'

export interface Requirement {
  id: string // R01, R02, ...
  label: string
  quote: string
  quote_located: boolean
  terms: string[]
  category: Category
  importance: Importance
  cue: string | null
  knockout_type: KnockoutType | null
  min_years: number | null
  aliases: string[]
}

export interface JobPosting {
  title: string | null
  company: string | null
  seniority: string | null
  seniority_quote: string | null
  location: string | null
  remote_policy: string | null
  employment_type: string | null
  salary_present: boolean
  requirements: Requirement[]
}

export interface RequirementFlag {
  rule_id: 'R1' | 'R2'
  requirement_ids: string[]
  severity: 'info' | 'warning'
  explanation: string
}

export interface PostingBanner {
  rule_id: 'R3' | 'R4'
  requirement_ids: string[]
  severity: 'info' | 'warning'
  explanation: string
}

// ---- Assessment and score --------------------------------------------------

export type Status = 'met' | 'partial' | 'missing' | 'unknown'

export type MatchType = 'exact' | 'alias' | 'semantic' | 'inferred' | 'user_answer'

export interface Evidence {
  ref: string // an L or F ID
  quote: string
  match_type: MatchType
}

export interface RequirementAssessment {
  requirement_id: string
  status: Status
  evidence: Evidence[]
  rationale: string
  keyword_present: boolean
  source: 'cv' | 'user_answer'
  question: string | null
}

export interface CandidateFacts {
  work_authorization: string[] | null
  needs_sponsorship: boolean | null
  location: string | null
  willing_to_relocate: boolean | null
  languages: string[] | null
  licenses: string[] | null
}

export type ExcludedReason = 'not_relevant' | 'flagged_R1' | 'flagged_R2' | 'gate'

export interface Contribution {
  requirement_id: string
  label: string
  category: Category
  importance: Importance
  status: Status
  weight: number
  credit: number
  points_won: number
  points_lost: number
  excluded_reason: ExcludedReason | null
}

export interface ScoreBreakdown {
  fit: number | null
  coverage: number | null
  coverage_numerator: number
  coverage_denominator: number
  pending_points: number
  contributions: Contribution[]
  summary: string
}

export type VerdictLabel =
  | 'likely_screened_out'
  | 'answer_questions'
  | 'apply'
  | 'stretch'
  | 'long_shot'

export type Badge = 'tailor_first' | 'screening_risk' | 'posting_red_flags'

export interface VerdictReason {
  text: string
  requirement_ids: string[]
}

export interface Verdict {
  label: VerdictLabel
  title: string
  badges: Badge[]
  reasons: VerdictReason[]
  provisional: boolean
}

// ---- Report projection (GET /api/analyses/{id} and the "report" event) ----

export type CvKind = 'pdf' | 'docx' | 'text'

export interface CvMeta {
  kind: CvKind
  filename: string | null
  size: number
  lines: number
}

export interface NodeError {
  node: string
  error: string
  detail: string
}

export interface UsageTotal {
  calls: number
  input_tokens: number
  output_tokens: number
  cost_usd: number
  models: string[]
}

export type AnalysisStatus = 'running' | 'done' | 'paused' | 'stalled'

export interface AnalysisReport {
  analysis_id: string
  status: AnalysisStatus
  stage: string | null
  cv_meta: CvMeta | null
  cv: ParsedCv | null
  job: JobPosting | null
  job_notes: string[]
  flags: RequirementFlag[]
  banners: PostingBanner[]
  assessments: Record<string, RequirementAssessment>
  score: ScoreBreakdown | null
  verdict: Verdict | null
  facts: Partial<CandidateFacts>
  excluded_ids: string[]
  included_flagged_ids: string[]
  errors: NodeError[]
  usage: UsageTotal
}

// ---- Stream and HTTP payloads ----------------------------------------------

export type ProgressStep = 'prepare_cv' | 'prepare_job' | 'match' | 'score'

export type ProgressStatus = 'started' | 'done' | 'chunk_done'

// Data of the "progress" SSE event (see graph/nodes.py `_progress`).
export interface ProgressEvent {
  type: 'progress'
  step: ProgressStep
  status: ProgressStatus
  requirements?: number
}

// Body of every JSON error, and of the "error" SSE event.
export interface ErrorBody {
  code: string
  title: string
  detail: string
}

// Body of GET /api/samples.
export interface Samples {
  cv_text: string
  job_text: string
}
