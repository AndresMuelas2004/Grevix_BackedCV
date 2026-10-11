import {
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
  type KeyboardEvent,
} from 'react'
import {
  getHiddenRiskSample,
  getSampleCvFile,
  getSamples,
  isSampleCvFile,
  type AnalysisInput,
} from '../api/client'
import type { Samples } from '../api/types'
import {
  ACCEPTED_FILE_TYPES,
  MAX_JOB_CHARS,
  MIN_JOB_CHARS,
  fileProblem,
  findProblems,
  toAnalysisInput,
  type AnalysisDraft,
  type CvMode,
} from '../lib/draft'
import { describeError } from '../lib/errors'
import { formatBytes, formatNumber } from '../lib/format'
import Benefits from './landing/Benefits'
import Hero from './landing/Hero'
import './InputForm.css'

interface InputFormProps {
  draft: AnalysisDraft
  onChange: (next: AnalysisDraft) => void
  onSubmit: (input: AnalysisInput) => void
}

const CV_TABS: CvMode[] = ['file', 'text']

const TAB_LABELS: Record<CvMode, string> = {
  file: 'Upload file',
  text: 'Paste text',
}

// Which button asked for a sample. Its loading label and its error show next to it.
type SampleSource = 'hero' | 'form'

interface SampleError {
  source: SampleSource
  message: string
}

// The sample PDF as a File, or null when it cannot be fetched.
async function fetchSamplePdf(sample: Samples): Promise<File | null> {
  try {
    return await getSampleCvFile(sample)
  } catch {
    return null
  }
}

// The first screen: the hero with the live example, the benefits, and the form.
export default function InputForm({ draft, onChange, onSubmit }: InputFormProps) {
  const [showProblems, setShowProblems] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [sampleLoading, setSampleLoading] = useState(false)
  const [hiddenSampleLoading, setHiddenSampleLoading] = useState<SampleSource | null>(null)
  const [sampleError, setSampleError] = useState<SampleError | null>(null)
  const sampleBusy = sampleLoading || hiddenSampleLoading !== null
  const formRef = useRef<HTMLFormElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const cvTextInput = useRef<HTMLTextAreaElement>(null)
  const jobTextInput = useRef<HTMLTextAreaElement>(null)

  const problems = findProblems(draft)
  const jobLength = draft.jobText.trim().length
  const jobOver = jobLength > MAX_JOB_CHARS
  const shownJob = showProblems ? problems.job : null
  const cvMessage = draft.cvMode === 'file' && fileError ? fileError : showProblems ? problems.cv : null
  const sampleInUse = draft.cvFile !== null && isSampleCvFile(draft.cvFile)

  function update(patch: Partial<AnalysisDraft>) {
    onChange({ ...draft, ...patch })
  }

  // Scrolls to the form and puts the cursor in its first field.
  function goToForm() {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    formRef.current?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
    jobTextInput.current?.focus({ preventScroll: true })
  }

  function acceptFile(file: File) {
    const problem = fileProblem(file)
    setFileError(problem)
    if (!problem) update({ cvMode: 'file', cvFile: file })
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) acceptFile(file)
    event.target.value = '' // lets the same file be chosen again
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files[0]
    if (file) acceptFile(file)
  }

  // Arrow keys, Home and End move between the two CV tabs (WAI-ARIA tabs pattern).
  function onTabKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = CV_TABS.indexOf(draft.cvMode)
    let next: number
    switch (event.key) {
      case 'ArrowRight':
        next = (index + 1) % CV_TABS.length
        break
      case 'ArrowLeft':
        next = (index - 1 + CV_TABS.length) % CV_TABS.length
        break
      case 'Home':
        next = 0
        break
      case 'End':
        next = CV_TABS.length - 1
        break
      default:
        return
    }
    event.preventDefault()
    const mode = CV_TABS[next]
    update({ cvMode: mode })
    document.getElementById(`cv-tab-${mode}`)?.focus()
  }

  // Loads the sample CV as a PDF upload and fills the posting. When the PDF cannot be fetched,
  // the sample text goes in paste mode instead.
  async function loadSample() {
    if (sampleBusy) return
    setSampleLoading(true)
    setSampleError(null)
    setFileError(null)
    try {
      const sample = await getSamples()
      const cvFile = await fetchSamplePdf(sample)
      if (cvFile) {
        update({ cvMode: 'file', cvFile, jobText: sample.job_text })
      } else {
        update({ cvMode: 'text', cvText: sample.cv_text, jobText: sample.job_text })
      }
    } catch (error) {
      setSampleError({ source: 'form', message: `The sample could not be loaded. ${describeError(error)}` })
    } finally {
      setSampleLoading(false)
    }
  }

  // Loads the posting that hides barriers, with its CV as pasted text (no file): the pair the live
  // example shows. From the hero it also starts the analysis, so one click opens the full report.
  async function loadHiddenRiskSample(source: SampleSource) {
    if (sampleBusy) return
    setHiddenSampleLoading(source)
    setSampleError(null)
    setFileError(null)
    try {
      const sample = await getHiddenRiskSample()
      const next: AnalysisDraft = {
        ...draft,
        cvMode: 'text',
        cvText: sample.cv_text,
        jobText: sample.job_text,
      }
      onChange(next)
      if (source === 'hero') {
        const found = findProblems(next)
        const input = found.cv || found.job ? null : toAnalysisInput(next)
        if (input) {
          onSubmit(input)
        } else {
          setShowProblems(true)
          goToForm()
        }
      }
    } catch (error) {
      setSampleError({ source, message: `The sample could not be loaded. ${describeError(error)}` })
    } finally {
      setHiddenSampleLoading(null)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setShowProblems(true)
    const found = findProblems(draft)
    // The first field with a problem takes the focus, in the order they appear.
    if (found.job) {
      jobTextInput.current?.focus()
      return
    }
    if (found.cv) {
      const control = draft.cvMode === 'file' ? fileInput.current : cvTextInput.current
      control?.focus()
      return
    }
    const input = toAnalysisInput(draft)
    if (input) onSubmit(input)
  }

  return (
    <div className="landing">
      <Hero
        onCheck={goToForm}
        onSample={() => loadHiddenRiskSample('hero')}
        sampleLoading={hiddenSampleLoading === 'hero'}
        sampleBusy={sampleBusy}
        sampleError={sampleError?.source === 'hero' ? sampleError.message : null}
      />

      <Benefits />

      <form
        id="try"
        ref={formRef}
        className="input-form"
        onSubmit={handleSubmit}
        noValidate
        aria-labelledby="input-title"
      >
        <div className="form-intro">
          <h2 id="input-title" tabIndex={-1} data-screen-heading>
            Try it with your CV
          </h2>
          <p>Paste a job posting and add your CV. No CV at hand? Fill both in with a sample.</p>
        </div>

        <div className="form-fields">
          <section className="form-section" aria-labelledby="job-heading">
            <h3 id="job-heading" className="form-section-title">
              <label htmlFor="job-text">1. The job posting</label>
            </h3>
            <p id="job-hint" className="field-hint">
              Paste the full posting, with its requirements.
            </p>
            <textarea
              id="job-text"
              ref={jobTextInput}
              rows={10}
              value={draft.jobText}
              onChange={(event) => update({ jobText: event.target.value })}
              aria-invalid={shownJob !== null}
              aria-describedby={shownJob ? 'job-hint job-counter job-error' : 'job-hint job-counter'}
              placeholder="Paste the full posting text"
            />
            <p id="job-counter" className={jobOver ? 'counter is-over' : 'counter'}>
              {formatNumber(jobLength)} characters ({formatNumber(MIN_JOB_CHARS)} to{' '}
              {formatNumber(MAX_JOB_CHARS)} allowed)
            </p>
            {shownJob && (
              <p id="job-error" className="field-error" role="alert">
                {shownJob}
              </p>
            )}
          </section>

          <section className="form-section" aria-labelledby="cv-heading">
            <h3 id="cv-heading" className="form-section-title">
              2. Your CV
            </h3>

            <div role="tablist" aria-label="How to add your CV" className="tabs" onKeyDown={onTabKeyDown}>
              {CV_TABS.map((mode) => {
                const selected = draft.cvMode === mode
                return (
                  <button
                    key={mode}
                    type="button"
                    role="tab"
                    id={`cv-tab-${mode}`}
                    aria-selected={selected}
                    aria-controls={`cv-panel-${mode}`}
                    tabIndex={selected ? 0 : -1}
                    className="tab"
                    onClick={() => update({ cvMode: mode })}
                  >
                    {TAB_LABELS[mode]}
                  </button>
                )
              })}
            </div>

            <div
              role="tabpanel"
              id="cv-panel-file"
              aria-labelledby="cv-tab-file"
              hidden={draft.cvMode !== 'file'}
              className="tab-panel"
            >
              <label
                className={dragging ? 'dropzone is-dragging' : 'dropzone'}
                onDragOver={(event) => {
                  event.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
              >
                <svg
                  className="dropzone-icon"
                  width="28"
                  height="28"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  focusable="false"
                >
                  <path d="M12 15V4" />
                  <path d="M7.5 8.5L12 4l4.5 4.5" />
                  <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
                </svg>
                <span className="dropzone-title">Drop your CV here, or choose a file</span>
                <span className="dropzone-hint" id="cv-file-hint">
                  PDF or DOCX, up to 4 MB
                </span>
                <input
                  ref={fileInput}
                  type="file"
                  accept={ACCEPTED_FILE_TYPES}
                  className="lp-visually-hidden"
                  aria-describedby="cv-file-hint"
                  aria-invalid={cvMessage !== null}
                  onChange={onFileChange}
                />
              </label>
              {draft.cvFile && (
                <div className="file-chosen">
                  <p>
                    <span className="file-name">{draft.cvFile.name}</span>{' '}
                    <span className="file-size">{formatBytes(draft.cvFile.size)}</span>
                  </p>
                  <button
                    type="button"
                    className="lp-btn lp-btn-secondary lp-btn-small"
                    onClick={() => {
                      update({ cvFile: null })
                      setFileError(null)
                      // This button leaves the page with the file, so the focus goes to the file input.
                      fileInput.current?.focus()
                    }}
                  >
                    Remove file
                  </button>
                </div>
              )}
              {sampleInUse && (
                <p className="notice notice-info">
                  Sample: a fictional candidate. The PDF has two columns on purpose, to show how
                  screening software reads it.
                </p>
              )}
            </div>

            <div
              role="tabpanel"
              id="cv-panel-text"
              aria-labelledby="cv-tab-text"
              hidden={draft.cvMode !== 'text'}
              className="tab-panel"
            >
              <label htmlFor="cv-text" className="field-label">
                CV text
              </label>
              <textarea
                id="cv-text"
                ref={cvTextInput}
                rows={10}
                value={draft.cvText}
                onChange={(event) => update({ cvText: event.target.value })}
                aria-invalid={cvMessage !== null}
                aria-describedby={cvMessage ? 'cv-error' : undefined}
                placeholder="Paste the plain text of your CV"
              />
            </div>

            {cvMessage && (
              <p id="cv-error" className="field-error" role="alert">
                {cvMessage}
              </p>
            )}
          </section>
        </div>

        <div className="form-footer">
          <div className="form-actions">
            <button type="submit" className="lp-btn lp-btn-primary">
              Check my CV
            </button>
            <div className="sample-actions">
              <button
                type="button"
                className="lp-btn lp-btn-secondary"
                onClick={loadSample}
                aria-disabled={sampleBusy}
              >
                {sampleLoading ? 'Loading sample...' : 'Try the sample'}
              </button>
              <button
                type="button"
                className="lp-btn lp-btn-secondary"
                onClick={() => loadHiddenRiskSample('form')}
                aria-disabled={sampleBusy}
              >
                {hiddenSampleLoading === 'form' ? 'Loading sample...' : 'Try a posting with hidden barriers'}
              </button>
            </div>
          </div>
          {sampleError?.source === 'form' && (
            <p className="notice notice-error" role="alert">
              {sampleError.message}
            </p>
          )}
          <p className="privacy-note">
            Privacy: contact details (email, phone, links) are replaced before any AI call, uploaded
            files are not stored, and analyses are deleted after 24 hours. In this public demo,
            please use the samples or a CV with fictional details.
          </p>
        </div>
      </form>
    </div>
  )
}
