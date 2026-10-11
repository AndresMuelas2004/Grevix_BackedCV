// What to fix, most important first. A pure function of the report: it reads the requirements,
// their assessments, the hidden risks, the "looks met, but..." flags and the parse warnings, and
// returns one plain item per problem, in the order the candidate should work through them.
import type {
  AnalysisReport,
  BarrierKind,
  Category,
  HiddenRisk,
  KnockoutType,
  Requirement,
  RequirementAssessment,
  RiskLevel,
} from '../api/types'
import { BARRIER_KIND_LABELS, SECTION_LABELS } from './labels'
import { firstSentence, plainText } from './plainText'
import { formatDuration, formatRange } from './timeline'

export type Tier = 'rule_out' | 'serious' | 'improve'

export const TIER_LABELS: Record<Tier, string> = {
  rule_out: 'Could rule you out',
  serious: 'Serious gap',
  improve: 'Worth improving',
}

export const TIERS: readonly Tier[] = ['rule_out', 'serious', 'improve']

export interface PriorityItem {
  key: string
  tier: Tier
  tag: string // one short context tag, e.g. "Legal requirement"
  title: string
  why: string // one sentence
  jobQuote: string | null // the posting's sentence
  cvQuote: string | null // the CV line that shows it, or null when nothing does
  cvSource: string | null // the CV entry or section of that line
  action: string // what to do, one sentence
  answeredNo: boolean
  pointsLost: number
  required: boolean
  order: number // posting order
}

const TIER_RANK: Record<Tier, number> = { rule_out: 0, serious: 1, improve: 2 }
const LEVEL_RANK: Record<RiskLevel, number> = { high: 0, medium: 1, low: 2 }

// Hard dealbreakers: legal knockouts, and the hidden risks of the same kinds. A missing language,
// education or years is a soft dealbreaker: a serious gap, never "Could rule you out".
const LEGAL_KNOCKOUTS: ReadonlySet<KnockoutType> = new Set<KnockoutType>([
  'work_authorization',
  'clearance',
  'certification_license',
])
const LEGAL_RISKS: ReadonlySet<BarrierKind | 'composite'> = new Set<BarrierKind | 'composite'>([
  'work_authorization',
  'clearance',
])

// Knockout types that work as a yes/no gate. Years of experience is a gap, not a gate.
type GateType = Exclude<KnockoutType, 'experience_years'>
const GATE_TYPES: ReadonlySet<KnockoutType> = new Set<KnockoutType>([
  'work_authorization',
  'location',
  'clearance',
  'certification_license',
  'language',
  'education',
  'availability',
])

const GATE_TAGS: Record<GateType, string> = {
  work_authorization: 'Legal requirement',
  location: 'Location',
  clearance: 'Security clearance',
  certification_license: 'License or certificate',
  language: 'Language',
  education: 'Education',
  availability: 'Availability',
}

const GATE_ACTIONS: Record<GateType, string> = {
  work_authorization:
    'If you already have the right to work there, answer Yes and say it in your CV.',
  location: 'If you can work from there or would move, answer Yes and say it next to your location.',
  clearance: 'If you hold it, answer Yes and name it in your CV.',
  certification_license: 'If you hold it, answer Yes and list it with its date.',
  language: 'If you speak it at that level, answer Yes and list it with your level.',
  education: 'If you have it, answer Yes and list it under Education.',
  availability: 'If you can meet it, answer Yes and say it in your summary.',
}

// What to do about a soft dealbreaker the CV doesn't show.
const SOFT_ACTIONS: Record<GateType, string> = {
  work_authorization: 'If you have the right to work there, say it in your CV.',
  location: 'If you can work from there or would move, say it next to your location.',
  clearance: 'If you hold it, name it in your CV.',
  certification_license: 'If you hold it, list it with its date.',
  language: "If you speak it at that level, list it with your level. Don't claim it if not.",
  education: 'If you have it, list it under Education.',
  availability: 'If you can meet it, say it in your summary.',
}

const RISK_TAGS: Record<BarrierKind | 'composite', string> = {
  work_authorization: 'Legal requirement',
  location: 'Location',
  recency: 'Experience too old',
  graduation_window: 'Graduation date',
  language: 'Language',
  clearance: 'Security clearance',
  availability: 'Availability',
  other: 'Screening rule',
  composite: 'Screening rule',
}

const MUST_HAVE_TAGS: Partial<Record<Category, string>> = {
  hard_skill: 'Must-have skill',
  soft_skill: 'Must-have soft skill',
  job_title: 'Must-have · job title',
  education: 'Must-have · education',
  certification_license: 'Must-have · license',
  language: 'Must-have · language',
}

interface Evidence {
  quote: string
  source: string | null
}

interface Context {
  analysis: AnalysisReport
  answers: Record<string, boolean>
  requirements: Map<string, Requirement>
  order: Map<string, number>
  pointsLost: Map<string, number>
  lineText: Map<string, string>
  lineSource: Map<string, string>
  labels: Map<string, string>
  unanswered: Set<string> // requirement and risk IDs whose question is not answered yet
}

export function buildPriorities(analysis: AnalysisReport): PriorityItem[] {
  const context = makeContext(analysis)
  const items: PriorityItem[] = []
  const usedRequirements = new Set<string>()
  const usedRisks = new Set<string>()

  // 1. Hidden risks, each one together with the requirements it follows.
  const risks = analysis.hidden_risks ?? []
  const composites = risks.filter((risk) => risk.kind === 'composite' && !risk.resolved)
  const singles = risks
    .filter((risk) => risk.kind !== 'composite' && !risk.resolved)
    .map((risk) => ({ risk, level: effectiveLevel(risk, composites) }))
    .sort((a, b) => LEVEL_RANK[a.level] - LEVEL_RANK[b.level])
  for (const { risk, level } of singles) {
    const linked = risk.requirement_ids.filter(
      (id) => context.requirements.has(id) && !usedRequirements.has(id),
    )
    linked.forEach((id) => usedRequirements.add(id))
    usedRisks.add(risk.id)
    items.push(riskItem(context, risk, level, linked))
  }

  // 2. Requirements on their own.
  const excluded = new Set(analysis.excluded_ids)
  for (const req of analysis.job?.requirements ?? []) {
    if (usedRequirements.has(req.id) || excluded.has(req.id)) continue
    const item = requirementItem(context, req, analysis.assessments[req.id])
    if (item) {
      usedRequirements.add(req.id)
      items.push(item)
    }
  }

  // 3. "Looks met, but..." flags that no item above already covers.
  for (const flag of analysis.screening_flags ?? []) {
    if (flag.risk === 'low') continue
    if (usedRequirements.has(flag.requirement_id)) continue
    if (flag.risk_ids.some((id) => usedRisks.has(id))) continue
    const req = context.requirements.get(flag.requirement_id)
    if (!req) continue
    usedRequirements.add(req.id)
    const evidence = requirementEvidence(context, analysis.assessments[req.id])
    const reason = flag.reasons.find((text) => text.trim() !== '')
    items.push({
      key: `flag-${req.id}`,
      tier: 'serious',
      tag: 'Looks met, but...',
      title: `${req.label}: looks met, but may still get you rejected`,
      why: reason
        ? firstSentence(plainText(reason, context.labels))
        : 'A screener may still read it as a gap.',
      jobQuote: quoteOf(req),
      cvQuote: evidence?.quote ?? null,
      cvSource: evidence?.source ?? null,
      action: 'Make the line that shows it easy to find, with its dates, if it is true.',
      answeredNo: false,
      pointsLost: context.pointsLost.get(req.id) ?? 0,
      required: req.importance === 'required',
      order: context.order.get(req.id) ?? 999,
    })
  }

  // 4. Problems in how the CV reads.
  analysis.parse_warnings.forEach((warning, index) => {
    if (warning.severity === 'info') return
    const message = plainText(warning.message, context.labels)
    const lineId = warning.line_ids.find((id) => context.lineText.has(id))
    items.push({
      key: `parse-${index}`,
      tier: 'improve',
      tag: 'How your CV reads',
      title: shorten(firstSentence(message), 90),
      why: 'Screening software may read this part of your CV wrong.',
      jobQuote: null,
      cvQuote: lineId ? (context.lineText.get(lineId) ?? null) : null,
      cvSource: lineId ? (context.lineSource.get(lineId) ?? null) : null,
      action: 'Fix it in your CV file, then check the CV again.',
      answeredNo: false,
      pointsLost: 0,
      required: false,
      order: 2000 + index,
    })
  })

  return items.sort(compareItems)
}

function compareItems(a: PriorityItem, b: PriorityItem): number {
  return (
    TIER_RANK[a.tier] - TIER_RANK[b.tier] ||
    Number(b.answeredNo) - Number(a.answeredNo) ||
    b.pointsLost - a.pointsLost ||
    Number(b.required) - Number(a.required) ||
    a.order - b.order
  )
}

function makeContext(analysis: AnalysisReport): Context {
  const requirements = new Map<string, Requirement>()
  const order = new Map<string, number>()
  const labels = new Map<string, string>()
  ;(analysis.job?.requirements ?? []).forEach((req, index) => {
    requirements.set(req.id, req)
    order.set(req.id, index)
    labels.set(req.id, req.label)
  })
  const pointsLost = new Map<string, number>()
  for (const contribution of analysis.score?.contributions ?? []) {
    pointsLost.set(contribution.requirement_id, contribution.points_lost)
  }

  const lineText = new Map<string, string>()
  const lineSource = new Map<string, string>()
  const cv = analysis.cv
  if (cv) {
    for (const line of cv.lines) lineText.set(line.id, line.text)
    for (const fact of cv.facts) lineText.set(fact.id, fact.text)
    for (const fact of cv.facts) lineSource.set(fact.id, 'Computed from your dates')
    for (const section of cv.sections) {
      for (const id of section.line_ids) lineSource.set(id, SECTION_LABELS[section.type])
    }
    for (const entry of cv.entries) {
      const name = entry.title?.trim() || entry.organization?.trim()
      if (!name) continue
      const dated = entry.start !== null || entry.end !== null
      const source = dated ? `${name}, ${formatRange(entry)}` : name
      for (const id of entry.line_ids) lineSource.set(id, source)
    }
  }

  const answers: Record<string, boolean> = {}
  for (const [id, value] of Object.entries(analysis.facts.answers ?? {})) {
    if (typeof value === 'boolean') answers[id] = value
  }
  const unanswered = new Set<string>()
  for (const assessment of Object.values(analysis.assessments)) {
    if (assessment.question && assessment.status === 'unknown' && !(assessment.requirement_id in answers)) {
      unanswered.add(assessment.requirement_id)
    }
  }
  for (const risk of analysis.hidden_risks ?? []) {
    if (risk.question && !risk.resolved && !risk.confirmed && !(risk.id in answers)) {
      unanswered.add(risk.id)
    }
  }

  return { analysis, answers, requirements, order, pointsLost, lineText, lineSource, labels, unanswered }
}

// A risk inside an open combined risk counts at the combined risk's level when that is higher.
function effectiveLevel(risk: HiddenRisk, composites: HiddenRisk[]): RiskLevel {
  let level = risk.risk
  for (const composite of composites) {
    if (composite.component_ids.includes(risk.id) && LEVEL_RANK[composite.risk] < LEVEL_RANK[level]) {
      level = composite.risk
    }
  }
  return level
}

function riskItem(context: Context, risk: HiddenRisk, level: RiskLevel, linked: string[]): PriorityItem {
  const reqs = linked.map((id) => context.requirements.get(id)).filter((req) => req !== undefined)
  const answeredNo =
    context.answers[risk.id] === false || linked.some((id) => context.answers[id] === false)
  const askAbove = context.unanswered.has(risk.id) || linked.some((id) => context.unanswered.has(id))

  // "Could rule you out" is only for a No, a question still open, or a high legal barrier
  // (work permit, clearance). Everything else is at most a serious gap.
  let tier: Tier
  if (answeredNo || askAbove) tier = 'rule_out'
  else if (level === 'high' && LEGAL_RISKS.has(risk.kind)) tier = 'rule_out'
  else tier = level === 'low' ? 'improve' : 'serious'
  // The requirement the risk follows can make it more urgent (a legal knockout the CV misses).
  if (risk.kind !== 'recency') {
    for (const req of reqs) {
      const own = classify(context, req, context.analysis.assessments[req.id])
      if (own && TIER_RANK[own.tier] < TIER_RANK[tier]) tier = own.tier
    }
  }
  const baseTag = RISK_TAGS[risk.kind]
  const tag = answeredNo ? `${baseTag} · you answered No` : askAbove ? `${baseTag} · answer above` : baseTag

  const firstReq = reqs[0]
  const kindLabel = BARRIER_KIND_LABELS[risk.kind]
  const title =
    risk.kind === 'recency' && firstReq
      ? `${firstReq.label}: your experience is too old for this posting`
      : firstReq
        ? `${kindLabel}: ${firstReq.label}`
        : `${kindLabel} rule in this posting`

  const cvRef = risk.cv_refs.find((id) => context.lineText.has(id))
  const reqEvidence = firstReq
    ? requirementEvidence(context, context.analysis.assessments[firstReq.id])
    : null
  const cvQuote = cvRef ? (context.lineText.get(cvRef) ?? null) : (reqEvidence?.quote ?? null)
  const cvSource = cvRef ? (context.lineSource.get(cvRef) ?? null) : (reqEvidence?.source ?? null)

  const action = risk.action.trim()
    ? firstSentence(plainText(risk.action, context.labels))
    : answeredNo
      ? 'Look for similar roles without this rule. If your answer was wrong, change it above.'
      : askAbove
        ? 'Answer the question above. If the answer is yes, say it in your CV too.'
        : 'If you meet it, say it in plain words in your CV.'

  const why = risk.explanation.trim()
    ? firstSentence(plainText(risk.explanation, context.labels))
    : 'A screener may reject you for this without a word.'

  return {
    key: `risk-${risk.id}`,
    tier,
    tag,
    title,
    why,
    jobQuote: risk.quote.trim() ? risk.quote.trim() : firstReq ? quoteOf(firstReq) : null,
    cvQuote,
    cvSource,
    action,
    answeredNo,
    pointsLost: linked.reduce((sum, id) => sum + (context.pointsLost.get(id) ?? 0), 0),
    required: reqs.length === 0 || reqs.some((req) => req.importance === 'required'),
    order: Math.min(999, ...linked.map((id) => context.order.get(id) ?? 999)),
  }
}

type Kind =
  | 'gate_ask'
  | 'gate_no'
  | 'gate_missing'
  | 'gate_partial'
  | 'too_old'
  | 'years'
  | 'years_partial'
  | 'years_ask'
  | 'years_no'
  | 'missing'
  | 'partial'
  | 'unclear'
  | 'preferred_missing'
  | 'preferred_partial'

function classify(
  context: Context,
  req: Requirement,
  assessment: RequirementAssessment | undefined,
): { tier: Tier; kind: Kind } | null {
  const status = assessment?.status ?? 'unknown'
  const required = req.importance === 'required'
  const years = req.category === 'experience_years' || req.knockout_type === 'experience_years'
  const gate = req.knockout_type !== null && GATE_TYPES.has(req.knockout_type)

  // Any No to a knockout question, and any question still open, could rule the candidate out.
  if (context.answers[req.id] === false && (req.knockout_type !== null || years)) {
    return { tier: 'rule_out', kind: years ? 'years_no' : 'gate_no' }
  }
  if (status === 'unknown' && assessment?.question && context.unanswered.has(req.id)) {
    return { tier: 'rule_out', kind: years ? 'years_ask' : 'gate_ask' }
  }

  if (gate && required) {
    // Only a legal knockout the CV misses is a hard dealbreaker; language, education, location
    // and availability are soft ones.
    const legal = req.knockout_type !== null && LEGAL_KNOCKOUTS.has(req.knockout_type)
    if (status === 'missing') return { tier: legal ? 'rule_out' : 'serious', kind: 'gate_missing' }
    if (status === 'partial') return { tier: 'serious', kind: 'gate_partial' }
    if (status === 'unknown') return { tier: 'improve', kind: 'unclear' }
    return null
  }

  if (years && required) {
    if (status === 'missing') return { tier: 'serious', kind: 'years' }
    if (status === 'partial') return { tier: 'improve', kind: 'years_partial' }
    return null
  }

  if (status === 'missing') {
    if (!required) return { tier: 'improve', kind: 'preferred_missing' }
    const downgraded = context.analysis.recency?.[req.id]?.effect === 'downgraded'
    return { tier: 'serious', kind: downgraded ? 'too_old' : 'missing' }
  }
  if (status === 'partial') {
    return { tier: 'improve', kind: required ? 'partial' : 'preferred_partial' }
  }
  if (status === 'unknown' && required) return { tier: 'improve', kind: 'unclear' }
  return null
}

function requirementItem(
  context: Context,
  req: Requirement,
  assessment: RequirementAssessment | undefined,
): PriorityItem | null {
  const found = classify(context, req, assessment)
  if (!found) return null
  const { tier, kind } = found
  const evidence = requirementEvidence(context, assessment)
  const gateType = req.knockout_type !== null && req.knockout_type !== 'experience_years'
    ? req.knockout_type
    : null
  const gateTag = gateType ? GATE_TAGS[gateType] : 'Firm rule'
  const mustTag = MUST_HAVE_TAGS[req.category] ?? 'Must-have'
  const label = req.label

  let tag = mustTag
  let title = `${label}: not in your CV`
  let why = 'The job lists it as a must-have, and nothing in your CV shows it.'
  let action = "If you have done this, add one line that shows it, with dates. If not, don't claim it."

  switch (kind) {
    case 'gate_ask':
      tag = `${gateTag} · answer above`
      title = `${label}: your CV doesn't say`
      why = "Your CV doesn't say, and screeners who are unsure often reject."
      action = gateType ? GATE_ACTIONS[gateType] : 'Answer the question above.'
      break
    case 'gate_no':
      tag = `${gateTag} · you answered No`
      title = `${label}: you answered No`
      why = 'This is a firm rule for this job, so a No usually means a rejection.'
      action = 'Look for similar roles without this rule. If your answer was wrong, change it above.'
      break
    case 'gate_missing':
      tag = gateTag
      title = `${label}: not shown in your CV`
      if (tier === 'rule_out') {
        why = "The job makes it a legal must, and your CV doesn't show it."
        action = 'If you meet it, say it in plain words in your CV. If not, this role is likely out of reach.'
      } else {
        why = "The job asks for it, and your CV doesn't show it."
        action = gateType
          ? SOFT_ACTIONS[gateType]
          : "If you meet it, say it in plain words in your CV. Don't claim it if not."
      }
      break
    case 'gate_partial':
      tag = gateTag
      title = `${label}: only partly shown`
      why = 'The job makes it a firm rule, and your CV only partly shows it.'
      action = 'If you fully meet it, say it in plain words in your CV.'
      break
    case 'too_old': {
      tag = 'Must-have skill · experience too old'
      title = `${label}: your experience is too old for this posting`
      const check = context.analysis.recency?.[req.id]
      why = check?.explanation.trim()
        ? firstSentence(plainText(check.explanation, context.labels))
        : 'They want recent experience, and your last use of it is too long ago.'
      action = "We won't reword this one: it would stretch the truth. If you used it more recently, add it with its dates."
      break
    }
    case 'years':
    case 'years_partial': {
      tag = 'Must-have · years of experience'
      title = `${label}: fewer years than they ask`
      why = yearsSentence(context, req, assessment)
      action = "Check that every job in your CV has its dates. Don't stretch them."
      break
    }
    case 'years_ask':
      tag = 'Must-have · years of experience · answer above'
      title = `${label}: your dates don't settle it`
      why = yearsSentence(context, req, assessment)
      action = 'Answer the question above, and add the missing months to your job dates.'
      break
    case 'years_no':
      tag = 'Must-have · years of experience · you answered No'
      title = `${label}: fewer years than they ask`
      why = yearsSentence(context, req, assessment)
      action = 'Look for roles that ask for fewer years. If your answer was wrong, change it above.'
      break
    case 'missing':
      break
    case 'partial':
      tag = `${mustTag} · only partly shown`
      title = `${label}: only partly shown`
      why = "Your CV hints at it but doesn't show it clearly."
      action = 'If you have more of this, add one clear line that shows it.'
      break
    case 'unclear':
      tag = `${mustTag} · unclear`
      title = `${label}: unclear from your CV`
      why = "Your CV doesn't make it clear either way."
      action = 'If you have it, add one clear line that shows it.'
      break
    case 'preferred_missing':
      tag = 'Nice to have'
      title = `${label}: not in your CV`
      why = 'A bonus, not a requirement.'
      action = 'Add it only if you really have it.'
      break
    case 'preferred_partial':
      tag = 'Nice to have · only partly shown'
      title = `${label}: only partly shown`
      why = 'A bonus, not a requirement.'
      action = 'If you have more of this, make it clearer. Skip it if not.'
      break
  }

  return {
    key: `req-${req.id}`,
    tier,
    tag,
    title,
    why,
    jobQuote: quoteOf(req),
    cvQuote: evidence?.quote ?? null,
    cvSource: evidence?.source ?? null,
    action,
    answeredNo: kind === 'gate_no' || kind === 'years_no',
    pointsLost: context.pointsLost.get(req.id) ?? 0,
    required: req.importance === 'required',
    order: context.order.get(req.id) ?? 999,
  }
}

function yearsSentence(
  context: Context,
  req: Requirement,
  assessment: RequirementAssessment | undefined,
): string {
  const asked = assessment?.years_check?.min_years ?? req.min_years
  const cv = context.analysis.cv
  let months: number | null = assessment?.years_check?.cv_months ?? null
  if (months === null && cv) {
    if (typeof cv.total_months === 'number') months = cv.total_months
    else if (cv.total_years !== null) months = Math.round(cv.total_years * 12)
  }
  const askedText = asked !== null ? `${formatYears(asked)}+ years` : 'more years'
  if (months === null) return `The job asks for ${askedText}; your CV's dates don't show how many you have.`
  const minimum = assessment?.years_check?.reliable === false || cv?.total_is_minimum === true
  return `The job asks for ${askedText}; your CV's dates add up to ${minimum ? 'at least' : 'about'} ${formatDuration(months)}.`
}

function formatYears(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

function quoteOf(req: Requirement): string | null {
  const quote = req.quote.trim()
  return quote === '' ? null : quote
}

// The first CV line or computed fact that backs a requirement, with the entry or section it is in.
function requirementEvidence(
  context: Context,
  assessment: RequirementAssessment | undefined,
): Evidence | null {
  if (!assessment) return null
  for (const item of assessment.evidence) {
    // An answer to a question is not a line of the CV.
    if (item.match_type === 'user_answer' || !context.lineText.has(item.ref)) continue
    const text = item.quote.trim() || context.lineText.get(item.ref)
    if (!text) continue
    return { quote: text, source: context.lineSource.get(item.ref) ?? null }
  }
  return null
}

function shorten(text: string, max: number): string {
  if (text.length <= max) return text
  const cut = text.slice(0, max)
  const space = cut.lastIndexOf(' ')
  return `${(space > 40 ? cut.slice(0, space) : cut).replace(/[,;:.]$/, '')}...`
}
