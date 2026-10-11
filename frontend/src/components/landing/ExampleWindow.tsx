import {
  useEffect,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type FocusEvent,
  type PointerEvent,
} from 'react'
import { EXAMPLE, TIER_LABELS, type ExampleSnippet } from '../../demo/example'
import './Landing.css'
import './ExampleWindow.css'

type Scene = 'inputs' | 'steps' | 'report' | 'detail'

const SCENES: readonly { id: Scene; label: string }[] = [
  { id: 'inputs', label: 'Inputs' },
  { id: 'steps', label: 'Checking' },
  { id: 'report', label: 'Report' },
  { id: 'detail', label: 'Details' },
]

// One beat of the loop: the frame on screen, how many steps are ticked, and how long it stays.
interface Beat {
  scene: Scene
  stepsDone: number
  ms: number
}

const STEP_COUNT = EXAMPLE.steps.length

const BEATS: readonly Beat[] = [
  { scene: 'inputs', stepsDone: 0, ms: 3400 },
  ...EXAMPLE.steps.map((_, index): Beat => ({ scene: 'steps', stepsDone: index, ms: 750 })),
  { scene: 'steps', stepsDone: STEP_COUNT, ms: 900 },
  { scene: 'report', stepsDone: STEP_COUNT, ms: 4200 },
  { scene: 'detail', stepsDone: STEP_COUNT, ms: 5200 },
]

const LAST_BEAT = BEATS.length - 1

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)'

function subscribeReducedMotion(onChange: () => void): () => void {
  const query = window.matchMedia(REDUCED_MOTION)
  query.addEventListener('change', onChange)
  return () => query.removeEventListener('change', onChange)
}

function prefersReducedMotion(): boolean {
  return window.matchMedia(REDUCED_MOTION).matches
}

function focusedByKeyboard(element: Element): boolean {
  try {
    return element.matches(':focus-visible')
  } catch {
    return false
  }
}

function stagger(index: number): CSSProperties {
  return { '--i': index } as CSSProperties
}

// Decorative for screen readers, who get a text alternative instead. Hovering pauses the loop;
// keyboard focus on the control stops it until Play is pressed.
export default function ExampleWindow() {
  const reduced = useSyncExternalStore(subscribeReducedMotion, prefersReducedMotion, () => false)
  const [beatIndex, setBeatIndex] = useState(0)
  const [hovered, setHovered] = useState(false)
  const [stopped, setStopped] = useState(false)
  const playing = !reduced && !hovered && !stopped

  useEffect(() => {
    if (!playing) return
    const timer = window.setTimeout(
      () => setBeatIndex((index) => (index + 1) % BEATS.length),
      BEATS[beatIndex].ms,
    )
    return () => window.clearTimeout(timer)
  }, [beatIndex, playing])

  const beat = BEATS[reduced ? LAST_BEAT : beatIndex]
  const sceneIndex = SCENES.findIndex((scene) => scene.id === beat.scene)
  const showReport = beat.scene === 'report' || beat.scene === 'detail'

  function onPointerEnter(event: PointerEvent<HTMLDivElement>) {
    if (event.pointerType === 'mouse') setHovered(true)
  }

  // Keyboard users stop the example by reaching its control; it plays again only on Play.
  function onControlFocus(event: FocusEvent<HTMLButtonElement>) {
    if (focusedByKeyboard(event.currentTarget)) setStopped(true)
  }

  return (
    <figure className="ew">
      <div
        className={playing ? 'ew-window' : 'ew-window is-paused'}
        aria-hidden="true"
        data-scene={beat.scene}
        onPointerEnter={onPointerEnter}
        onPointerLeave={() => setHovered(false)}
      >
        <div className="ew-bar">
          <span className="ew-bar-dots">
            <span />
            <span />
            <span />
          </span>
          <span className="ew-bar-title">{EXAMPLE.windowTitle}</span>
        </div>

        <div className="ew-stage">
          {/* Never shown: it holds the stage at the height of the last frame, so the window
              does not change size while the frames change. */}
          <ReportLayer className="ew-layer ew-sizer" detailOpen />

          <div className={beat.scene === 'inputs' ? 'ew-layer ew-inputs is-on' : 'ew-layer ew-inputs'}>
            <SnippetCard snippet={EXAMPLE.posting} kind="posting" />
            <SnippetCard snippet={EXAMPLE.cv} kind="cv" />
          </div>

          <div className={beat.scene === 'steps' ? 'ew-layer ew-checking is-on' : 'ew-layer ew-checking'}>
            <p className="ew-checking-title">Checking the CV against the posting</p>
            <div className="ew-meter">
              <span style={{ width: `${(beat.stepsDone / STEP_COUNT) * 100}%` }} />
            </div>
            <ol className="ew-steps">
              {EXAMPLE.steps.map((step, index) => {
                const state =
                  index < beat.stepsDone ? 'done' : index === beat.stepsDone ? 'active' : 'waiting'
                return (
                  <li key={step.label} className={`ew-step is-${state}`}>
                    <span className="ew-step-icon">
                      {state === 'done' ? <CheckIcon /> : <span>{index + 1}</span>}
                    </span>
                    <span className="ew-step-text">
                      <span className="ew-step-label">{step.label}</span>
                      <span className="ew-step-detail">{step.detail}</span>
                    </span>
                  </li>
                )
              })}
            </ol>
          </div>

          <ReportLayer
            className={showReport ? 'ew-layer ew-live is-on' : 'ew-layer ew-live'}
            detailOpen={beat.scene === 'detail'}
          />
        </div>

        {!reduced && (
          <ol className="ew-progress">
            {SCENES.map((scene, index) => (
              <li
                key={scene.id}
                className={
                  index === sceneIndex ? 'is-current' : index < sceneIndex ? 'is-past' : undefined
                }
              >
                <span className="ew-progress-bar" />
                <span className="ew-progress-label">{scene.label}</span>
              </li>
            ))}
          </ol>
        )}
      </div>

      <figcaption className="ew-caption">
        <span className="lp-visually-hidden">{EXAMPLE.description}</span>
        <span className="ew-caption-text" aria-hidden="true">
          {reduced ? EXAMPLE.stillCaption : EXAMPLE.caption}
        </span>
        {!reduced && (
          <button
            type="button"
            className="ew-control"
            onFocus={onControlFocus}
            onClick={() => setStopped((value) => !value)}
          >
            {stopped ? <PlayIcon /> : <PauseIcon />}
            {stopped ? 'Play the example' : 'Pause the example'}
          </button>
        )}
      </figcaption>
    </figure>
  )
}

function SnippetCard({ snippet, kind }: { snippet: ExampleSnippet; kind: 'posting' | 'cv' }) {
  return (
    <div className={`ew-snippet ew-snippet-${kind}`}>
      <span className="ew-snippet-label">{snippet.label}</span>
      <p className="ew-snippet-title">{snippet.title}</p>
      <ul>
        {snippet.lines.map((line, index) => (
          <li key={line} style={stagger(index + 1)}>
            {line}
          </li>
        ))}
      </ul>
    </div>
  )
}

// With detailOpen, the fix that has quotes shows them.
function ReportLayer({ className, detailOpen }: { className: string; detailOpen: boolean }) {
  const { detail } = EXAMPLE
  return (
    <div className={className}>
      <div className="ew-chips">
        {EXAMPLE.steps.map((step, index) => (
          <span
            key={step.label}
            className={index === STEP_COUNT - 1 ? 'ew-chip is-current' : 'ew-chip'}
          >
            {index + 1} {step.label}
          </span>
        ))}
      </div>

      <div className="ew-summary">
        <div className="ew-verdict">
          <span className="ew-verdict-chip">{EXAMPLE.verdictLabel}</span>
          <p className="ew-verdict-title">{EXAMPLE.verdictTitle}</p>
        </div>
        <div className="ew-score">
          <span className="ew-score-label">{EXAMPLE.scoreLabel}</span>
          <span className="ew-score-value">{EXAMPLE.score}</span>
        </div>
      </div>

      <ol className="ew-fixes">
        {EXAMPLE.fixes.map((fix, index) => {
          const opens = index === detail.fixIndex
          const open = opens && detailOpen
          return (
            <li
              key={fix.title}
              className={`ew-fix tier-${fix.tier}${open ? ' is-open' : ''}`}
              style={stagger(index)}
            >
              <div className="ew-fix-row">
                <span className="ew-fix-number">{index + 1}</span>
                <span className="ew-fix-title">{fix.title}</span>
                <span className="ew-fix-tier">{TIER_LABELS[fix.tier]}</span>
              </div>
              {opens && (
                <div className="ew-detail">
                  <div className="ew-detail-inner">
                    <div className="ew-quote">
                      <span className="ew-quote-label">{detail.jobLabel}</span>"{detail.jobQuote}"
                    </div>
                    <div className="ew-quote">
                      <span className="ew-quote-label">{detail.cvLabel}</span>"{detail.cvQuote}"
                    </div>
                  </div>
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  )
}

function PauseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
      <rect x="6" y="5" width="4" height="14" rx="1" />
      <rect x="14" y="5" width="4" height="14" rx="1" />
    </svg>
  )
}

function PlayIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
      <path d="M7 4.5v15a1 1 0 0 0 1.5.86l12.5-7.5a1 1 0 0 0 0-1.72L8.5 3.64A1 1 0 0 0 7 4.5z" />
    </svg>
  )
}
