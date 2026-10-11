import type { MouseEvent } from 'react'
import ExampleWindow from './ExampleWindow'
import './Landing.css'

interface HeroProps {
  onCheck: () => void // moves to the form and focuses its first field
  onSample: () => void // loads the sample pair and starts the analysis
  sampleLoading: boolean
  sampleBusy: boolean // any sample is loading
  sampleError: string | null
}

export default function Hero({ onCheck, onSample, sampleLoading, sampleBusy, sampleError }: HeroProps) {
  function onCheckClick(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault()
    onCheck()
  }

  return (
    <section className="lp-hero" aria-labelledby="hero-title">
      <div className="lp-hero-copy">
        <h1 id="hero-title" className="lp-hero-title">
          Find out what could get your CV rejected, before you apply.
        </h1>
        <p className="lp-hero-sub">
          Paste a job posting and your CV. In under a minute you get a plain answer, the problems
          ranked by how much they hurt, and edits backed by your own experience. Nothing invented.
        </p>
        <div className="lp-hero-actions">
          <a href="#try" className="lp-btn lp-btn-primary" onClick={onCheckClick}>
            Check my CV
          </a>
          <button
            type="button"
            className="lp-btn lp-btn-secondary"
            onClick={onSample}
            aria-disabled={sampleBusy}
          >
            {sampleLoading ? 'Loading the sample...' : 'See it on the sample'}
          </button>
        </div>
        {sampleError && (
          <p className="lp-notice-error" role="alert">
            {sampleError}
          </p>
        )}
        <p className="lp-hero-privacy">
          Free. Contact details are replaced before any AI call. Files are not stored.
        </p>
      </div>
      <div className="lp-hero-example">
        <ExampleWindow />
      </div>
    </section>
  )
}
