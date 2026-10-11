import type {
  AnalysisReport,
  CandidateFacts,
  ErrorBody,
  ProgressEvent,
  Samples,
} from './types'

const API_BASE = '/api'

// A failed request: either an HTTP error body ({code, title, detail}) or a
// transport problem (status 0). Codes are the backend's stable codes.
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

export async function getSamples(): Promise<Samples> {
  const response = await send(`${API_BASE}/samples`, {})
  if (!response.ok) throw await readError(response)
  const body: unknown = await response.json()
  if (!isRecord(body) || typeof body.cv_text !== 'string' || typeof body.job_text !== 'string') {
    throw new ApiError(response.status, 'bad_response', 'The sample could not be read.')
  }
  return { cv_text: body.cv_text, job_text: body.job_text }
}

export async function getAnalysis(id: string): Promise<AnalysisReport> {
  const response = await send(`${API_BASE}/analyses/${encodeURIComponent(id)}`, {})
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

  const response = await send(`${API_BASE}/analyses`, {
    method: 'POST',
    body: form,
    headers: { Accept: 'text/event-stream' },
    signal,
  })
  if (!response.ok) throw await readError(response)
  if (!response.body) {
    throw new ApiError(response.status, 'stream_missing', 'The analysis did not start.')
  }

  let finished = false
  try {
    await readSse(response.body, (message) => {
      const event = toAnalysisEvent(message)
      if (!event) return
      if (event.type === 'report' || event.type === 'error') finished = true
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
      'The connection closed before the analysis finished.',
    )
  }
}

// ---- helpers ---------------------------------------------------------------

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
  // FastAPI's own validation errors look like {detail: [...]}; anything else is a plain failure.
  const detail = isRecord(body) && typeof body.detail === 'string' ? body.detail : ''
  return new ApiError(
    response.status,
    'http_error',
    `The server answered with HTTP ${response.status}.`,
    detail,
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isErrorBody(value: unknown): value is ErrorBody {
  return (
    isRecord(value) &&
    typeof value.code === 'string' &&
    typeof value.title === 'string' &&
    typeof value.detail === 'string'
  )
}

interface SseMessage {
  event: string
  data: string
}

function toAnalysisEvent(message: SseMessage): AnalysisEvent | null {
  const payload = parseJson(message.data)
  switch (message.event) {
    case 'created':
      return isRecord(payload) && typeof payload.analysis_id === 'string'
        ? { type: 'created', analysisId: payload.analysis_id }
        : null
    case 'progress':
      // Shape is checked shallowly; the backend is trusted for the rest.
      return isRecord(payload) && typeof payload.step === 'string'
        ? { type: 'progress', progress: payload as unknown as ProgressEvent }
        : null
    case 'report':
      return isRecord(payload)
        ? { type: 'report', report: payload as unknown as AnalysisReport }
        : null
    case 'error':
      return {
        type: 'error',
        error: isErrorBody(payload)
          ? payload
          : { code: 'analysis_failed', title: 'The analysis could not finish.', detail: '' },
      }
    default:
      return null
  }
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
