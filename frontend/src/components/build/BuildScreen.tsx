import { cvDownloadUrl } from '../../api/client'
import type { AnalysisReport, BuildReport, DiffLine } from '../../api/types'
import { CitedText } from '../CitationTag'
import HowComputed from '../HowComputed'
import ScoreValue from '../review/ScoreValue'
import LineDiff from './LineDiff'
import './BuildScreen.css'

interface BuildScreenProps {
  analysis: AnalysisReport
  onStartOver: () => void
}

export default function BuildScreen({ analysis, onStartOver }: BuildScreenProps) {
  const report = analysis.build_report
  if (!report) {
    return (
      <section className="card" aria-labelledby="missing-title">
        <h1 id="missing-title" tabIndex={-1} data-screen-heading>
          The build report is missing.
        </h1>
        <div className="downloads">
          <button type="button" className="btn btn-secondary" onClick={onStartOver}>
            Start over
          </button>
        </div>
      </section>
    )
  }

  const coverageBefore = report.coverage_before ?? analysis.score?.coverage ?? null
  const fit = report.fit ?? analysis.score?.fit ?? null
  const titles = new Map<string, string>(
    (analysis.document?.sections ?? []).map((section): [string, string] => [section.id, section.heading]),
  )

  return (
    <div className="build">
      <section className="card build-summary" aria-labelledby="build-title">
        <p className="eyebrow">Built</p>
        <h1 id="build-title" tabIndex={-1} data-screen-heading>
          Your new CV is ready
        </h1>
        <p className="order-note">{orderNote(report.built_by)}</p>

        <section className="build-fact" aria-labelledby="coverage-title">
          <h3 id="coverage-title">Keyword coverage</h3>
          <div className="compare">
            <div className="compare-item">
              <span className="compare-label">Before</span>
              <span className="compare-value">
                <ScoreValue value={coverageBefore} />
              </span>
            </div>
            <span className="compare-arrow" aria-hidden="true">
              →
            </span>
            <div className="compare-item">
              <span className="compare-label">After</span>
              <span className="compare-value">
                <ScoreValue value={report.coverage_after} />
              </span>
            </div>
          </div>
        </section>

        <section className="build-fact" aria-labelledby="fit-title">
          <h3 id="fit-title">Fit</h3>
          <p>
            <span className="fit-value">
              <ScoreValue value={fit} />
            </span>{' '}
            <span className="fit-status">(unchanged)</span>
          </p>
          <p className="screen-note">Rewording cannot add experience, so fit stays the same.</p>
        </section>

        <section className="build-fact" aria-labelledby="check-title">
          <h3 id="check-title">PDF check</h3>
          {report.roundtrip_ok === true && (
            <p className="notice notice-info">The PDF reads back correctly.</p>
          )}
          {report.roundtrip_ok === false && (
            <div className="notice notice-warn">
              <p>The PDF does not read back correctly.</p>
              {report.roundtrip_issues.length > 0 && (
                <ul className="issue-list">
                  {report.roundtrip_issues.map((issue, index) => (
                    <li key={index}>
                      <CitedText text={issue} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {report.roundtrip_ok === null && <p className="notice">The PDF was not checked.</p>}
          {report.validation_errors.length > 0 && (
            <div className="notice notice-warn">
              <p>Some checks failed:</p>
              <ul className="issue-list">
                {report.validation_errors.map((error, index) => (
                  <li key={index}>
                    <CitedText text={error} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <div className="downloads">
          <a
            className="btn btn-primary"
            href={cvDownloadUrl(analysis.analysis_id, 'docx')}
            download
          >
            Download DOCX
          </a>
          <a className="btn btn-primary" href={cvDownloadUrl(analysis.analysis_id, 'pdf')} download>
            Download PDF
          </a>
          <button type="button" className="btn btn-secondary" onClick={onStartOver}>
            Start over
          </button>
        </div>
      </section>

      <section className="card" aria-labelledby="changes-title">
        <h3 id="changes-title">What changed</h3>
        <p className="screen-note">{countChanges(report.diff)}</p>
        <LineDiff lines={report.diff} titles={titles} />
      </section>

      <HowComputed usage={analysis.usage} />
    </div>
  )
}

// How the section order was chosen, in plain words.
function orderNote(builtBy: BuildReport['built_by']): string {
  return builtBy === 'agent'
    ? 'An AI agent chose the section order. It can only move sections: the only text changes are the suggestions you accepted.'
    : 'Standard section order used. The only text changes are the suggestions you accepted.'
}

// For example: "2 changed, 1 added, 0 removed, 14 unchanged".
function countChanges(diff: DiffLine[]): string {
  const count = (status: DiffLine['status']) => diff.filter((line) => line.status === status).length
  return [
    `${count('changed')} changed`,
    `${count('added')} added`,
    `${count('removed')} removed`,
    `${count('unchanged')} unchanged`,
  ].join(', ')
}
