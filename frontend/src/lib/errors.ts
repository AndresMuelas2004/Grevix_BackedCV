import { ApiError } from '../api/client'

// A short, readable reason for a failed request. Callers put it after "not saved." or similar.
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return [error.title, error.detail].filter((part) => part !== '').join(' ')
  }
  return 'Something went wrong.'
}
