// Plain-language text for each error code the backend or the client can return. Each entry says
// what happened in one short sentence and what to do next. A code that is not listed falls back
// to the server's own title (see describeFailure).
import type { ErrorBody } from '../api/types'

export interface FriendlyText {
  message: string // what happened, in one short sentence
  next: string // what to do next
}

const FRIENDLY = {
  // The job posting
  job_too_short: {
    message: 'The job posting is too short to check.',
    next: 'Paste the full posting, with its requirements, and try again.',
  },
  job_too_long: {
    message: 'The job posting is too long to check.',
    next: 'Remove the text that is not part of the posting, then try again.',
  },

  // The CV file or text
  cv_missing: {
    message: 'No CV was received.',
    next: 'Upload your CV as a PDF or DOCX file, or paste its text, then try again.',
  },
  cv_unsupported_type: {
    message: 'This file type is not supported.',
    next: 'Save your CV as a PDF or DOCX file, or paste its text instead.',
  },
  cv_too_large: {
    message: 'This CV file is too large.',
    next: 'Save a smaller PDF or DOCX file (under 4 MB), or paste the text instead.',
  },
  cv_too_long: {
    message: 'This CV has too much text to check.',
    next: 'Shorten the CV, or paste only the parts that matter for this job.',
  },
  cv_too_many_pages: {
    message: 'This CV has too many pages to check.',
    next: 'Shorten it to the page limit, or paste the text instead.',
  },
  cv_empty: {
    message: 'No text could be read from this CV.',
    next: 'Check that the file has text in it, or paste the CV text instead.',
  },
  cv_image_only: {
    message: 'This PDF has no selectable text, so it looks like a scan.',
    next: 'Paste the CV text instead, or export the CV again from its original file.',
  },
  cv_unreadable: {
    message: 'We could not read this file.',
    next: 'Try saving it again as PDF or DOCX, or paste the text.',
  },

  // The request, the answers and the choices
  invalid_request: {
    message: 'Something in the request is not valid.',
    next: 'Check the CV and the job posting, then try again.',
  },
  facts_invalid: {
    message: 'Your answers could not be read.',
    next: 'Answer the questions again, then try again.',
  },
  inputs_invalid: {
    message: 'Some requirements are not part of this posting.',
    next: 'Start over and check the posting again.',
  },
  decisions_invalid: {
    message: 'Some of your choices could not be used.',
    next: 'Go back to the review, check your choices, and build again.',
  },

  // Limits
  rate_limited: {
    message: 'You have made too many checks in the last hour.',
    next: 'Wait for the time shown below, then try again.',
  },
  daily_limit_reached: {
    message: 'The daily limit of checks has been reached.',
    next: 'Try again once the limit resets.',
  },

  // Analyses and their steps
  not_found: {
    message: 'This analysis is no longer available.',
    next: 'Analyses are kept for 24 hours. Start a new check.',
  },
  suggestion_not_found: {
    message: 'That suggestion is no longer part of this analysis.',
    next: 'Go back to the review and try again.',
  },
  samples_missing: {
    message: 'The sample files are missing on the server.',
    next: 'Upload your own CV and job posting instead.',
  },
  run_in_progress: {
    message: 'This analysis is still running.',
    next: 'Wait for it to finish, then try again.',
  },
  wrong_stage: {
    message: 'This step is not available at this point.',
    next: 'Go back to the report or the review, or start over.',
  },
  not_paused: {
    message: 'This report is no longer open for changes.',
    next: 'Start over to check the job again with new answers.',
  },
  not_built: {
    message: 'The new CV has not been built yet.',
    next: 'Build it from the review first.',
  },
  not_ready: {
    message: 'This analysis has no report yet.',
    next: 'Wait a moment and reload the page, or start over.',
  },
  analysis_failed: {
    message: 'The check could not finish.',
    next: 'Try again. If it keeps failing, use a different CV file or paste the text.',
  },
  optimize_failed: {
    message: 'The suggestions could not be made.',
    next: 'Go back to the report and try again.',
  },
  build_failed: {
    message: 'Your new CV could not be built.',
    next: 'Go back to the review, check your choices, and try again.',
  },
  still_running: {
    message: 'This is taking longer than expected.',
    next: 'The work keeps going on the server. Reload the page in a few minutes to see the result.',
  },

  // The connection and the app itself
  network_error: {
    message: 'The server could not be reached.',
    next: 'Check your connection, then try again.',
  },
  stream_failed: {
    message: 'The connection to the server was lost.',
    next: 'Check your connection, then try again.',
  },
  stream_incomplete: {
    message: 'The connection closed before the work finished.',
    next: 'Try again.',
  },
  stream_missing: {
    message: 'The server did not start the work.',
    next: 'Try again.',
  },
  http_error: {
    message: 'The server returned an unexpected error.',
    next: 'Try again. If it keeps happening, start over.',
  },
  bad_response: {
    message: 'The server sent a reply this page could not read.',
    next: 'Refresh the page and try again.',
  },
  unexpected: {
    message: 'Something went wrong.',
    next: 'Try again. If it keeps happening, start over.',
  },
} satisfies Record<string, FriendlyText>

export type KnownCode = keyof typeof FRIENDLY

// The plain text of a known code, for screens that show it without a server error.
export function friendlyText(code: KnownCode): FriendlyText {
  return FRIENDLY[code]
}

// What an error screen shows for one error.
export interface FailureText {
  message: string // the headline
  next: string | null // what to do next; null for a code this file does not know
  detail: string // the server's detail, shown in smaller text ('' when there is none)
}

export function describeFailure(error: ErrorBody): FailureText {
  if (isKnownCode(error.code)) {
    const friendly = FRIENDLY[error.code]
    return { message: friendly.message, next: friendly.next, detail: error.detail }
  }
  // Unknown code: the server's title is the best description there is.
  return { message: error.title, next: null, detail: error.detail }
}

function isKnownCode(code: string): code is KnownCode {
  return Object.hasOwn(FRIENDLY, code)
}
