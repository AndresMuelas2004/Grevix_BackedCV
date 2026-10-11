import type {
  AnalysisReport,
  BuildStep,
  CandidateFacts,
  CoveragePreview,
  ErrorBody,
  InputsUpdate,
  OptimizeStep,
  ProgressEvent,
  ProgressStep,
  ReviewDecisions,
  Samples,
} from './types'
import { wait } from '../lib/wait'

const API_BASE = '/api'

// The server refuses a request with 409 run_in_progress while another request holds the same
// analysis. Such a request is sent once more after this delay; a second refusal is the error.
const BUSY_RETRY_MS = 1000

// A failed request: an HTTP error body ({code, title, detail}), a FastAPI validation
// answer (HTTP 422, code "invalid_request"), or a transport problem (status 0).
// Codes are the backend's stable codes.
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly title: string
  readonly detail: string

  constructor(status: number, code: string, title: string, detail = '') {
    super(title)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.title = title
    this.detail = detail
  }
}

// The CV is either an uploaded file or pasted text, never both.
export type CvSource = { file: File } | { text: string }

export interface AnalysisInput {
  cv: CvSource
  jobText: string
  facts?: Partial<CandidateFacts>
}

// What runAnalysis reports while the stream is open.
export type AnalysisEvent =
  | { type: 'created'; analysisId: string }
  | { type: 'progress'; progress: ProgressEvent }
  | { type: 'report'; report: AnalysisReport }
  | { type: 'error'; error: ErrorBody }

// What runOptimize reports while the stream is open.
export type OptimizeEvent =
  | { type: 'progress'; progress: ProgressEvent<OptimizeStep> }
  | { type: 'suggestions'; report: AnalysisReport }
  | { type: 'error'; error: ErrorBody }

// What runBuild reports while the stream is open.
export type BuildEvent =
  | { type: 'progress'; progress: ProgressEvent<BuildStep> }
  | { type: 'built'; report: AnalysisReport }
  | { type: 'error'; error: ErrorBody }

// The formats served by GET /api/analyses/{id}/cv.{format}.
export type CvDownloadFormat = 'docx' | 'pdf'

export async function getSamples(): Promise<Samples> {
  const response = await send(`${API_BASE}/samples`, {})
  if (!response.ok) throw await readError(response)
  const body: unknown = await response.json()
  if (!isSamples(body)) {
    throw new ApiError(response.status, 'bad_response', 'The sample could not be read.')
  }
  return body
}

// The Files made by getSampleCvFile. Kept by identity, so the form can tell them from uploads.
const sampleFiles = new WeakSet<File>()

// Downloads the sample CV PDF that getSamples describes, as a File ready to upload.
// Throws when the PDF cannot be fetched.
export async function getSampleCvFile(samples: Samples): Promise<File> {
  const response = await send(samples.cv_pdf_url, {})
  if (!response.ok) throw await readError(response)
  const blob = await response.blob()
  const file = new File([blob], samples.cv_filename, { type: 'application/pdf' })
  sampleFiles.add(file)
  return file
}

// True for a File made by getSampleCvFile, also after the form was unmounted and mounted again.
export function isSampleCvFile(file: File): boolean {
  return sampleFiles.has(file)
}

// Reads an analysis. Its status is "running" while the server is still working on it.
export async function getAnalysis(id: string, signal?: AbortSignal): Promise<AnalysisReport> {
  const response = await send(`${API_BASE}/analyses/${encodeURIComponent(id)}`, { signal })
  if (!response.ok) throw await readError(response)
  return (await response.json()) as AnalysisReport
}

// Starts an analysis. A non-2xx answer is a JSON error and is thrown. A 2xx
// answer is an SSE stream: each event goes to onEvent, and the promise resolves
// after the stream ends. The "error" and "report" events both end the run.
export async function runAnalysis(
  input: AnalysisInput,
  onEvent: (event: AnalysisEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const form = new FormData()
  if ('file' in input.cv) {
    form.append('cv_file', input.cv.file, input.cv.file.name)
  } else {
    form.append('cv_text', input.cv.text)
  }
  form.append('job_text', input.jobText)
  if (input.facts) form.append('facts', JSON.stringify(input.facts))

  await streamEvents({
    url: `${API_BASE}/analyses`,
    init: { method: 'POST', body: form },
    label: 'analysis',
    parse: toAnalysisEvent,
    ends: (event) => event.type === 'report' || event.type === 'error',
    onEvent,
    signal,
  })
}

// Sends answers, exclusions or inclusions for a report waiting at its report stage.
// Returns the recomputed report. Fields left out keep their value (see InputsUpdate).
export async function updateInputs(id: string, body: InputsUpdate): Promise<AnalysisReport> {
  return retryWhenBusy(async () => {
    const response = await send(`${API_BASE}/analyses/${encodeURIComponent(id)}/inputs`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!response.ok) throw await readError(response)
    return (await response.json()) as AnalysisReport
  })
}

// Asks for suggestions on a report waiting at its report stage. The "suggestions"
// event (or "error") ends the run.
export async function runOptimize(
  id: string,
  onEvent: (event: OptimizeEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await retryWhenBusy(
    () =>
      streamEvents({
        url: `${API_BASE}/analyses/${encodeURIComponent(id)}/optimize`,
        init: { method: 'POST' },
        label: 'optimization',
        parse: toOptimizeEvent,
        ends: (event) => event.type === 'suggestions' || event.type === 'error',
        onEvent,
        signal,
      }),
    signal,
  )
}

// Checks one suggestion again after the user edited its text. Returns the new report.
export async function verifySuggestion(
  id: string,
  suggestionId: string,
  after: string,
): Promise<AnalysisReport> {
  const url =
    `${API_BASE}/analyses/${encodeURIComponent(id)}` +
    `/suggestions/${encodeURIComponent(suggestionId)}/verify`
  return retryWhenBusy(async () => {
    const response = await send(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ after }),
    })
    if (!response.ok) throw await readError(response)
    return (await response.json()) as AnalysisReport
  })
}

// Keyword coverage now, and if the given suggestions were accepted. Asked for each time the
// accepted set changes during the review. Pass a signal to cancel a request that is no longer wanted.
export async function previewCoverage(
  id: string,
  accepted: string[],
  signal?: AbortSignal,
): Promise<CoveragePreview> {
  const response = await send(`${API_BASE}/analyses/${encodeURIComponent(id)}/coverage-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accepted }),
    signal,
  })
  if (!response.ok) throw await readError(response)
  const body: unknown = await response.json()
  if (!isCoveragePreview(body)) {
    throw new ApiError(response.status, 'bad_response', 'The coverage preview could not be read.')
  }
  return body
}

// Builds the new CV from the user's decisions. The "built" event (or "error") ends the run.
export async function runBuild(
  id: string,
  decisions: ReviewDecisions,
  onEvent: (event: BuildEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await retryWhenBusy(
    () =>
      streamEvents({
        url: `${API_BASE}/analyses/${encodeURIComponent(id)}/build`,
        init: {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ accepted: decisions.accepted, rejected: decisions.rejected }),
        },
        label: 'CV build',
        parse: toBuildEvent,
        ends: (event) => event.type === 'built' || event.type === 'error',
        onEvent,
        signal,
      }),
    signal,
  )
}

// The address of the built CV in one format. Use it as a download link.
export function cvDownloadUrl(id: string, format: CvDownloadFormat): string {
  return `${API_BASE}/analyses/${encodeURIComponent(id)}/cv.${format}`
}

// Deletes an analysis and its saved state on the server.
export async function deleteAnalysis(id: string): Promise<void> {
  const response = await send(`${API_BASE}/analyses/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw await readError(response)
}

// ---- helpers ---------------------------------------------------------------

// Used when an "error" event does not carry an ErrorBody.
const ANALYSIS_FAILED: ErrorBody = {
  code: 'analysis_failed',
  title: 'The analysis could not finish.',
  detail: '',
}
const OPTIMIZE_FAILED: ErrorBody = {
  code: 'optimize_failed',
  title: 'The suggestions could not be generated.',
  detail: '',
}
const BUILD_FAILED: ErrorBody = {
  code: 'build_failed',
  title: 'The CV could not be built.',
  detail: '',
}

// Runs a request that the server may refuse while another run holds the analysis. A refusal with
// 409 run_in_progress is tried once more after a second. Nothing is sent again for any other error.
async function retryWhenBusy<T>(attempt: () => Promise<T>, signal?: AbortSignal): Promise<T> {
  try {
    return await attempt()
  } catch (error) {
    if (!isRunInProgress(error)) throw error
  }
  await wait(BUSY_RETRY_MS, signal)
  return attempt()
}

function isRunInProgress(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && error.code === 'run_in_progress'
}

async function send(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init)
  } catch (error) {
    if (init.signal?.aborted) throw error
    throw new ApiError(0, 'network_error', 'Could not reach the server.', 'Check that the backend is running.')
  }
}

async function readError(response: Response): Promise<ApiError> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    body = undefined
  }
  if (isErrorBody(body)) {
    return new ApiError(response.status, body.code, body.title, body.detail)
  }
  const fields: Record<string, unknown> = isRecord(body) ? body : {}
  // FastAPI's own validation errors (HTTP 422) look like {detail: [{loc, msg, type}, ...]}.
  if (response.status === 422 && isList(fields.detail)) {
    return new ApiError(
      422,
      'invalid_request',
      'The request data is not valid.',
      describeValidation(fields.detail),
    )
  }
  // Anything else is a plain failure.
  const detail = typeof fields.detail === 'string' ? fields.detail : ''
  return new ApiError(
    response.status,
    'http_error',
    `The server answered with HTTP ${response.status}.`,
    detail,
  )
}

// Turns FastAPI's list of problems into one line, e.g. "after: Field required".
function describeValidation(problems: unknown[]): string {
  const lines: string[] = []
  for (const problem of problems) {
    if (!isRecord(problem)) continue
    const msg = problem.msg
    if (typeof msg !== 'string') continue
    // loc starts with where the value came from ("body", "query"...), then the field path.
    const loc = problem.loc
    const path = isList(loc) ? loc.slice(1).map(String).join('.') : ''
    lines.push(path ? `${path}: ${msg}` : msg)
  }
  return lines.join('; ')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isList(value: unknown): value is unknown[] {
  return Array.isArray(value)
}

function isErrorBody(value: unknown): value is ErrorBody {
  return (
    isRecord(value) &&
    typeof value.code === 'string' &&
    typeof value.title === 'string' &&
    typeof value.detail === 'string'
  )
}

function isCoveragePreview(value: unknown): value is CoveragePreview {
  return (
    isRecord(value) &&
    isNullableNumber(value.coverage) &&
    isNullableNumber(value.coverage_now) &&
    isList(value.gained_requirement_ids) &&
    value.gained_requirement_ids.every((id) => typeof id === 'string')
  )
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === 'number'
}

function isSamples(value: unknown): value is Samples {
  return (
    isRecord(value) &&
    typeof value.cv_text === 'string' &&
    typeof value.job_text === 'string' &&
    typeof value.cv_pdf_url === 'string' &&
    typeof value.cv_docx_url === 'string' &&
    typeof value.cv_filename === 'string'
  )
}

interface SseMessage {
  event: string
  data: string
}

// Everything streamEvents needs. `label` names the work in its error messages.
interface StreamRequest<E> {
  url: string
  init: RequestInit
  label: string
  parse: (message: SseMessage) => E | null
  ends: (event: E) => boolean // true for the event that finishes the run
  onEvent: (event: E) => void
  signal?: AbortSignal
}

// The one reader for every stream. Sends the request, then reports each parsed event.
// A non-2xx answer is a JSON error and is thrown. The promise resolves after an event
// that ends the run; a stream that closes before that throws.
async function streamEvents<E>(request: StreamRequest<E>): Promise<void> {
  const { url, init, label, parse, ends, onEvent, signal } = request
  const headers = new Headers(init.headers)
  headers.set('Accept', 'text/event-stream')
  const response = await send(url, { ...init, headers, signal })
  if (!response.ok) throw await readError(response)
  if (!response.body) {
    throw new ApiError(response.status, 'stream_missing', `The ${label} did not start.`)
  }

  let finished = false
  try {
    await readSse(response.body, (message) => {
      const event = parse(message)
      if (!event) return
      if (ends(event)) finished = true
      onEvent(event)
    })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError(response.status, 'stream_failed', 'The connection to the server was lost.')
  }
  if (!finished) {
    throw new ApiError(
      response.status,
      'stream_incomplete',
      `The connection closed before the ${label} finished.`,
    )
  }
}

// The analysis stream: created, progress, report or error.
function toAnalysisEvent(message: SseMessage): AnalysisEvent | null {
  const payload = parseJson(message.data)
  switch (message.event) {
    case 'created':
      return isRecord(payload) && typeof payload.analysis_id === 'string'
        ? { type: 'created', analysisId: payload.analysis_id }
        : null
    case 'progress': {
      const progress = toProgress<ProgressStep>(payload)
      return progress ? { type: 'progress', progress } : null
    }
    case 'report':
      return isRecord(payload)
        ? { type: 'report', report: payload as unknown as AnalysisReport }
        : null
    case 'error':
      return { type: 'error', error: errorFrom(payload, ANALYSIS_FAILED) }
    default:
      return null
  }
}

// The optimize stream: progress, suggestions or error.
function toOptimizeEvent(message: SseMessage): OptimizeEvent | null {
  const payload = parseJson(message.data)
  switch (message.event) {
    case 'progress': {
      const progress = toProgress<OptimizeStep>(payload)
      return progress ? { type: 'progress', progress } : null
    }
    case 'suggestions':
      return isRecord(payload)
        ? { type: 'suggestions', report: payload as unknown as AnalysisReport }
        : null
    case 'error':
      return { type: 'error', error: errorFrom(payload, OPTIMIZE_FAILED) }
    default:
      return null
  }
}

// The build stream: progress, built or error.
function toBuildEvent(message: SseMessage): BuildEvent | null {
  const payload = parseJson(message.data)
  switch (message.event) {
    case 'progress': {
      const progress = toProgress<BuildStep>(payload)
      return progress ? { type: 'progress', progress } : null
    }
    case 'built':
      return isRecord(payload)
        ? { type: 'built', report: payload as unknown as AnalysisReport }
        : null
    case 'error':
      return { type: 'error', error: errorFrom(payload, BUILD_FAILED) }
    default:
      return null
  }
}

// Shape is checked shallowly; the backend is trusted for the rest.
function toProgress<Step extends string>(payload: unknown): ProgressEvent<Step> | null {
  return isRecord(payload) && typeof payload.step === 'string'
    ? (payload as unknown as ProgressEvent<Step>)
    : null
}

function errorFrom(payload: unknown, fallback: ErrorBody): ErrorBody {
  return isErrorBody(payload) ? payload : fallback
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown
  } catch {
    return undefined
  }
}

// Reads a text/event-stream body. Handles LF, CRLF and CR line endings, and
// events split across network chunks. A stream that ends mid-event still
// dispatches what it has, so a final report is never lost.
async function readSse(
  body: ReadableStream<Uint8Array>,
  onMessage: (message: SseMessage) => void,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let pending = ''
  let eventName = ''
  let dataLines: string[] = []

  const dispatch = (): void => {
    if (dataLines.length > 0) {
      onMessage({ event: eventName || 'message', data: dataLines.join('\n') })
    }
    eventName = ''
    dataLines = []
  }

  const handleLine = (line: string): void => {
    if (line === '') {
      dispatch()
      return
    }
    if (line.startsWith(':')) return // comment or keep-alive
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') eventName = value
    else if (field === 'data') dataLines.push(value)
    // "id" and "retry" are not used by this client.
  }

  for (;;) {
    const result = await reader.read()
    if (result.done) break
    pending += decoder.decode(result.value, { stream: true })
    const split = splitLines(pending, false)
    pending = split.rest
    split.lines.forEach(handleLine)
  }

  pending += decoder.decode()
  const last = splitLines(pending, true)
  last.lines.forEach(handleLine)
  dispatch()
}

// Splits text into complete lines. A CR at the very end may be the first half
// of a CRLF, so it stays in `rest` until the next chunk arrives (unless final).
function splitLines(text: string, final: boolean): { lines: string[]; rest: string } {
  const lines: string[] = []
  let start = 0
  let i = 0
  while (i < text.length) {
    const ch = text[i]
    if (ch !== '\n' && ch !== '\r') {
      i++
      continue
    }
    if (ch === '\r' && i === text.length - 1 && !final) break
    lines.push(text.slice(start, i))
    i += ch === '\r' && text[i + 1] === '\n' ? 2 : 1
    start = i
  }
  const rest = text.slice(start)
  if (final && rest !== '') return { lines: [...lines, rest], rest: '' }
  return { lines, rest }
}
