import { ApiError } from '../api/client'
import { describeFailure } from './errorMessages'

// A short, plain reason for a failed request: what happened, then what to do next. Callers put it
// after "not saved." or similar.
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    const text = describeFailure({ code: error.code, title: error.title, detail: error.detail })
    return [text.message, text.next ?? ''].filter((part) => part !== '').join(' ')
  }
  return 'Something went wrong.'
}
