// Mirrors the backend models (backend/src/backedcv/domain/models) and the
// report projection (backend/src/backedcv/api/projection.py).
// Field names stay in the backend's snake_case on purpose.

// CV as read by the backend

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
  // Optional: analyses saved before the date timeline have neither.
  month_unknown?: boolean // the start or the end shows only the year: no month is invented
  months_counted?: number | null // jobs only: the months this entry adds; null when not counted
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
  // Optional: analyses saved before the date timeline have none of these.
  total_months?: number | null // job periods, overlaps counted once
  total_is_minimum?: boolean // a job date shows only the year, or a job has no dates
  dates_note?: string | null // one plain sentence saying why the total is a minimum
}

export interface ParseWarning {
  code: string
  severity: 'info' | 'warning' | 'error'
  message: string
  line_ids: string[]
}

// Job posting

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

// Assessment and score

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
  years_check?: YearsCheck | null // minimum-years requirements, when the CV has dates
}

// A minimum-years requirement against the months the CV's own job dates add up to.
export interface YearsCheck {
  min_years: number
  cv_months: number // the shortest total the dates allow (overlaps counted once)
  reliable: boolean // false when a job date shows only the year or a job has no dates
  share: number
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

// Suggestions and review

export type SuggestionKind = 'align_wording' | 'add_skill' | 'tailor_summary'

// "refused": backed by the CV but not viable for the posting. It can never be accepted.
export type VerificationStatus = 'pending' | 'verified' | 'unsupported' | 'refused'

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
  // The gate's passes. Optional: older saved analyses have none.
  passes?: GatePass[]
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

export interface ReviewDecisions {
  accepted: string[]
  rejected: string[]
}

// `coverage` is the keyword coverage if the accepted changes were built, `coverage_now` the
// current one. `gained_requirement_ids` are the requirements those changes newly cover.
export interface CoveragePreview {
  coverage: number | null
  coverage_now: number | null
  gained_requirement_ids: string[]
}

// Rebuilt CV

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

// Screening risks, recency and the gate

// How recent the CV's evidence of a requirement is: recent (3 years or less), aging (up to 6),
// stale (more), or undated (no dated entry shows it).
export type RecencyBand = 'recent' | 'aging' | 'stale' | 'undated'

// A recency rule the posting states, e.g. "within the last 5 years". The quote is its sentence.
export interface RecencyRule {
  quote: string
  window_years: number
  requirement_ids: string[] // empty: a general rule
  source: 'rule' | 'model'
}

export interface RecencyCheck {
  requirement_id: string
  original_status: string
  last_used: string | null // YYYY-MM of the most recent dated entry that shows it
  years_since: number | null
  band: RecencyBand
  evidence_refs: string[]
  rule: RecencyRule | null
  within_rule: boolean | null // null when no rule applies
  effect: 'none' | 'warning' | 'downgraded' // downgraded: the requirement counts as missing
  explanation: string
}

export type RiskLevel = 'high' | 'medium' | 'low'

export type BarrierKind =
  | 'work_authorization'
  | 'location'
  | 'recency'
  | 'graduation_window'
  | 'language'
  | 'clearance'
  | 'availability'
  | 'other'

// A line of the posting that may get the candidate screened out without a word. The quote is the
// posting's exact sentence. A composite combines several risks and has no quote.
export interface HiddenRisk {
  id: string // H01, H02, ...; composites are HC1, HC2, ...
  kind: BarrierKind | 'composite'
  quote: string // empty for a composite
  explanation: string // why a screener may reject without a word
  action: string // what the candidate can do; may be empty
  risk: RiskLevel
  requirement_ids: string[]
  question: string | null // a yes/no question; its answer is saved as facts.answers[id]
  resolved: boolean // answered yes, or (no question) the requirement it follows is met
  confirmed: boolean // answered no, or (no question) the requirement it follows is missing
  component_ids: string[] // composites: the risks they combine
  cv_refs: string[] // CV lines that show the conflict
}

// A requirement that looks met but may still be rejected without a word.
export interface ScreeningFlag {
  requirement_id: string
  risk: RiskLevel
  reasons: string[] // plain sentences
  risk_ids: string[] // the risk IDs behind it
}

export type GateName = 'backed' | 'recent_enough' | 'not_blocked'

// One pass of the gate. A failed hard pass refuses the edit as not viable.
export interface GatePass {
  name: GateName
  ok: boolean
  hard: boolean
  detail: string | null
}

// An edit refused as not viable: a requirement (suggestion_id null), or a generated suggestion.
export interface Refusal {
  requirement_id: string
  gate: 'recent_enough' | 'not_blocked'
  reason: string
  refs: string[] // the old or conflicting evidence lines
  suggestion_id: string | null
}

// Report projection (GET /api/analyses/{id} and the "report" event)

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
  cached_calls: number // the calls replayed from the cache, also counted in calls
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
  // Optional: older saved analyses have none of these, so read them with a default.
  hidden_risks?: HiddenRisk[]
  screening_flags?: ScreeningFlag[]
  recency?: Record<string, RecencyCheck>
  refusals?: Refusal[]
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

// Stream and HTTP payloads

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

// Body of GET /api/samples. cv_filename is the name the PDF gets when it is uploaded as a CV.
export interface Samples {
  cv_text: string
  job_text: string
  cv_pdf_url: string
  cv_docx_url: string
  cv_filename: string
}

// Body of GET /api/samples/hidden-risk: a posting with hidden barriers, and its CV as plain text.
export interface HiddenRiskSample {
  cv_text: string
  job_text: string
}

// Body of PATCH /api/analyses/{id}/inputs. A field left out keeps its value, and a list that
// is sent replaces the old one. Sending `facts.answers` replaces the whole answers map, so
// send every answer each time.
export interface InputsUpdate {
  facts?: Partial<CandidateFacts>
  excluded_ids?: string[]
  included_flagged_ids?: string[]
}
