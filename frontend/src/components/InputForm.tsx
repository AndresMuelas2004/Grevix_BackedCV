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

// The sample PDF as a File, or null when it cannot be fetched.
async function fetchSamplePdf(sample: Samples): Promise<File | null> {
  try {
    return await getSampleCvFile(sample)
  } catch {
    return null
  }
}

export default function InputForm({ draft, onChange, onSubmit }: InputFormProps) {
  const [showProblems, setShowProblems] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [sampleLoading, setSampleLoading] = useState(false)
  const [hiddenSampleLoading, setHiddenSampleLoading] = useState(false)
  const [sampleError, setSampleError] = useState<string | null>(null)
  const sampleBusy = sampleLoading || hiddenSampleLoading
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
      setSampleError(`The sample could not be loaded. ${describeError(error)}`)
    } finally {
      setSampleLoading(false)
    }
  }

  // Loads the posting that hides barriers, with its CV as pasted text (no file).
  async function loadHiddenRiskSample() {
    if (sampleBusy) return
    setHiddenSampleLoading(true)
    setSampleError(null)
    setFileError(null)
    try {
      const sample = await getHiddenRiskSample()
      update({ cvMode: 'text', cvText: sample.cv_text, jobText: sample.job_text })
    } catch (error) {
      setSampleError(`The sample could not be loaded. ${describeError(error)}`)
    } finally {
      setHiddenSampleLoading(false)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setShowProblems(true)
    const found = findProblems(draft)
    if (found.cv) {
      const control = draft.cvMode === 'file' ? fileInput.current : cvTextInput.current
      control?.focus()
      return
    }
    if (found.job) {
      jobTextInput.current?.focus()
      return
    }
    const input = toAnalysisInput(draft)
    if (input) onSubmit(input)
  }

  return (
    <form className="input-form card" onSubmit={handleSubmit} noValidate aria-labelledby="input-title">
      <h2 id="input-title" tabIndex={-1} data-screen-heading>
        Check a job against your CV
      </h2>

      <section className="form-section" aria-labelledby="cv-heading">
        <div className="section-head">
          <h3 id="cv-heading">Your CV</h3>
          <div className="sample-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={loadSample}
              aria-disabled={sampleBusy}
            >
              {sampleLoading ? 'Loading sample...' : 'Try the sample'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={loadHiddenRiskSample}
              aria-disabled={sampleBusy}
            >
              {hiddenSampleLoading ? 'Loading sample...' : 'Try a posting with hidden barriers'}
            </button>
          </div>
        </div>
        {sampleError && (
          <p className="notice notice-error" role="alert">
            {sampleError}
          </p>
        )}

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
            <span className="dropzone-title">Drop your CV here, or choose a file</span>
            <span className="dropzone-hint" id="cv-file-hint">
              PDF or DOCX, up to 4 MB
            </span>
            <input
              ref={fileInput}
              type="file"
              accept={ACCEPTED_FILE_TYPES}
              className="visually-hidden"
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
                className="btn btn-secondary"
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
            rows={12}
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

      <section className="form-section" aria-labelledby="job-heading">
        <div className="section-head">
          <h3 id="job-heading">Job posting</h3>
          <p id="job-counter" className={jobOver ? 'counter is-over' : 'counter'}>
            {formatNumber(jobLength)} characters ({formatNumber(MIN_JOB_CHARS)} to{' '}
            {formatNumber(MAX_JOB_CHARS)} allowed)
          </p>
        </div>
        <label htmlFor="job-text" className="field-label">
          Paste the full posting, with its requirements
        </label>
        <textarea
          id="job-text"
          ref={jobTextInput}
          rows={12}
          value={draft.jobText}
          onChange={(event) => update({ jobText: event.target.value })}
          aria-invalid={shownJob !== null}
          aria-describedby={shownJob ? 'job-counter job-error' : 'job-counter'}
          placeholder="Paste the job posting here"
        />
        {shownJob && (
          <p id="job-error" className="field-error" role="alert">
            {shownJob}
          </p>
        )}
      </section>

      <div className="form-actions">
        <button type="submit" className="btn btn-primary">
          Check this job
        </button>
      </div>
    </form>
  )
}
