import { ApiError } from '../api/client'
import type { ErrorBody } from '../api/types'
import { describeFailure } from './errorMessages'

// Codes of a request or stream that broke in transit. The server may still be doing the work.
const BROKEN_CODES: ReadonlySet<string> = new Set([
  'network_error',
  'stream_failed',
  'stream_incomplete',
  'stream_missing',
])

// A plain reason for a failed request: what happened, then what to do next.
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    const text = describeFailure({ code: error.code, title: error.title, detail: error.detail })
    return [text.message, text.next ?? ''].filter((part) => part !== '').join(' ')
  }
  return 'Something went wrong.'
}

export function toErrorBody(error: unknown): ErrorBody {
  if (error instanceof ApiError) {
    return { code: error.code, title: error.title, detail: error.detail }
  }
  return {
    code: 'unexpected',
    title: 'Something went wrong.',
    detail: error instanceof Error ? error.message : '',
  }
}

export function isBrokenConnection(error: unknown): boolean {
  return error instanceof ApiError && BROKEN_CODES.has(error.code)
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof ApiError && error.code === 'network_error'
}
