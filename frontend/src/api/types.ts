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

// A problem found while reading the CV (backend ParseWarning).
export interface ParseWarning {
  code: string
  severity: 'info' | 'warning' | 'error'
  message: string
  line_ids: string[]
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
  answers: Record<string, boolean> // requirement ID -> yes (true) or no (false)
  work_authorization: string[] | null
  needs_sponsorship: boolean | null
  location: string | null
  willing_to_relocate: boolean | null
  languages: string[] | null
  licenses: string[] | null
}

// A plain string, because rule IDs can be joined: e.g. "not_relevant", "gate", "flagged_R1+R2".
export type ExcludedReason = string

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

// ---- Suggestions and review -------------------------------------------------

export type SuggestionKind = 'align_wording' | 'add_skill' | 'tailor_summary'

export type VerificationStatus = 'pending' | 'verified' | 'unsupported'

// One atomic claim of a suggestion, and the CV references (L and F IDs) backing it.
export interface ClaimCheck {
  text: string
  supported_by: string[]
  ok: boolean
  reason: string | null
}

// A check run in code. A failed hard guard makes the suggestion unsupported.
export interface GuardResult {
  name: string
  ok: boolean
  hard: boolean
  detail: string | null
}

export interface Verification {
  status: VerificationStatus
  claims: ClaimCheck[]
  guards: GuardResult[]
  reason: string | null // the first failing reason, shown to the user
}

// A proposed CV change. `target` is a line ID (align_wording) or a section ID (add_skill,
// tailor_summary). `before` is null when a line is added.
export interface Suggestion {
  id: string // S01, S02, ...
  kind: SuggestionKind
  target: string
  before: string | null
  after: string
  requirement_ids: string[]
  cited_refs: string[]
  introduced_terms: string[]
  covers_requirement_ids: string[]
  edited_by_user: boolean
  verification: Verification
}

// The user's choices on the suggestions, sent to the build.
export interface ReviewDecisions {
  accepted: string[]
  rejected: string[]
}

// ---- Rebuilt CV ------------------------------------------------------------

export type DocLineKind = 'text' | 'bullet'

// `origin` is the original line ID (L012) or the accepted suggestion ID (S03) of the text.
export interface DocLine {
  text: string
  origin: string
  kind: DocLineKind
}

// One block inside a section: a job, a degree, a project, or loose lines.
export interface DocItem {
  id: string // the entry ID, or "<section_id>-i<n>" for loose lines
  lines: DocLine[]
}

export interface DocSection {
  id: string // the CV section ID, or "added-<type>" for a section a suggestion created
  type: SectionType
  heading: string
  heading_origin: string | null // the heading's line ID; null for a standard heading
  items: DocItem[]
}

export interface DocContact {
  name: string | null
  details: string[] // email, phone, location, links
  origins: string[] // line IDs the contact came from
  // Optional: documents saved before the headline existed do not have these keys.
  headline?: string | null // the line under the name, as written or as its accepted rewrite
  headline_origin?: string | null // the headline's line ID, or the suggestion ID that rewrote it
}

export interface CVDocument {
  contact: DocContact
  sections: DocSection[]
}

export type DiffStatus = 'unchanged' | 'changed' | 'added' | 'removed'

export interface DiffLine {
  section_id: string
  status: DiffStatus
  before: string | null
  after: string | null
  origin: string | null
}

// What the build changed, and how the new CV was checked.
export interface BuildReport {
  diff: DiffLine[]
  coverage_before: number | null
  coverage_after: number | null
  fit: number | null
  roundtrip_ok: boolean | null
  roundtrip_issues: string[]
  built_by: 'agent' | 'fallback'
  validation_errors: string[]
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

export type AnalysisStatus = 'running' | 'paused' | 'done' | 'stalled'

// Where the run is: waiting for optimize, waiting for the review, or built.
export type AnalysisStage = 'report_ready' | 'review_ready' | 'built'

export interface AnalysisReport {
  analysis_id: string
  status: AnalysisStatus
  stage: AnalysisStage | null
  cv_meta: CvMeta | null
  cv: ParsedCv | null
  parse_warnings: ParseWarning[]
  job: JobPosting | null
  job_notes: string[]
  flags: RequirementFlag[]
  banners: PostingBanner[]
  assessments: Record<string, RequirementAssessment>
  score: ScoreBreakdown | null
  verdict: Verdict | null
  suggestions: Suggestion[]
  decisions: ReviewDecisions | null
  document: CVDocument | null
  build_report: BuildReport | null
  facts: Partial<CandidateFacts>
  excluded_ids: string[]
  included_flagged_ids: string[]
  errors: NodeError[]
  usage: UsageTotal
}

// ---- Stream and HTTP payloads ----------------------------------------------

export type ProgressStep = 'prepare_cv' | 'prepare_job' | 'match' | 'score'

// Steps of the optimize stream and of the build stream (the analysis has its own list).
export type OptimizeStep = 'suggest' | 'verify'
export type BuildStep = 'build' | 'checks'

export type ProgressStatus = 'started' | 'done' | 'chunk_done'

// Data of a "progress" SSE event (see graph/nodes.py `_progress`). Its step names the stream it
// came from: ProgressStep for the analysis, OptimizeStep or BuildStep for the other two.
export interface ProgressEvent<Step extends string = ProgressStep> {
  type: 'progress'
  step: Step
  status: ProgressStatus
  requirements?: number
  suggestions?: number
  built_by?: 'agent' | 'fallback'
  roundtrip_ok?: boolean | null
}

// Body of every JSON error, and of the "error" SSE event.
export interface ErrorBody {
  code: string
  title: string
  detail: string
}

// Body of GET /api/samples. The sample CV is also served as a PDF and a DOCX, at the two URLs.
// cv_filename is the name the PDF gets when it is uploaded as a CV.
export interface Samples {
  cv_text: string
  job_text: string
  cv_pdf_url: string
  cv_docx_url: string
  cv_filename: string
}

// Body of PATCH /api/analyses/{id}/inputs. A field left out keeps its value, and a list that
// is sent replaces the old one. Sending `facts.answers` replaces the whole answers map, so
// send every answer each time.
export interface InputsUpdate {
  facts?: Partial<CandidateFacts>
  excluded_ids?: string[]
  included_flagged_ids?: string[]
}
