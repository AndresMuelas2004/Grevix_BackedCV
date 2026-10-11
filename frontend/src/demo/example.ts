// Everything the landing page's live example shows: the hidden-risk sample (a Platform Engineer
// posting at Sable Creek Freight Systems against Mateo Serrano's CV). The snippets are quoted from
// backend/samples/hidden_risk; the report figures are the real report for that sample, which replays
// pinned model answers (backend/samples/pinned_answers.json), so the app shows the same numbers.

// How much a problem hurts, as the report ranks it.
export type ExampleTier = 'rule-out' | 'serious' | 'improve'

export const TIER_LABELS: Record<ExampleTier, string> = {
  'rule-out': 'Could rule you out',
  serious: 'Serious gap',
  improve: 'Worth improving',
}

export interface ExampleSnippet {
  label: string // what the card is: the posting or the CV
  title: string
  lines: string[]
}

export interface ExampleStep {
  label: string
  detail: string // what the step found, shown once it is done
}

export interface ExampleFix {
  title: string
  tier: ExampleTier
}

export interface ExampleDetail {
  fixIndex: number // the fix in `fixes` that opens in the last frame
  jobLabel: string
  jobQuote: string
  cvLabel: string
  cvQuote: string
}

export interface Example {
  windowTitle: string
  caption: string // under the window while it plays
  stillCaption: string // under the window when motion is reduced (only the last frame shows)
  posting: ExampleSnippet
  cv: ExampleSnippet
  steps: ExampleStep[]
  verdictLabel: string
  verdictTitle: string
  scoreLabel: string
  score: number
  fixes: ExampleFix[]
  detail: ExampleDetail
  // Short text alternative for screen readers: the window itself is decorative.
  description: string
}

export const EXAMPLE: Example = {
  windowTitle: 'Example: Platform Engineer posting vs a real-looking CV',
  caption: 'The example plays on its own: inputs, the four steps, then the report.',
  stillCaption: 'Example: the report for a Platform Engineer posting and a real-looking CV.',
  posting: {
    label: 'Job posting',
    title: 'Platform Engineer at Sable Creek Freight Systems',
    lines: [
      'Location: Austin, TX',
      'This is a hybrid role: three days a week in our Austin office.',
      '3+ years of hands-on Kubernetes experience within the last 5 years.',
      'Please note we are unable to sponsor work visas.',
    ],
  },
  cv: {
    label: 'CV',
    title: 'Mateo Serrano Vidal',
    lines: [
      'Valencia, Spain',
      'Platform Engineer, Faro Mesa Software · Mar 2019 - Present',
      'DevOps Engineer, Alameda Ticketing Labs · Sep 2015 - Dec 2017',
      'Deployed and operated microservices on K8s clusters.',
    ],
  },
  steps: [
    { label: 'Read the CV', detail: '2 jobs, a degree and a skills list' },
    { label: 'Read the posting', detail: '14 requirements, 10 of them must-haves' },
    { label: 'Match', detail: '7 of 10 must-haves shown' },
    { label: 'Report', detail: '6 things to fix, ranked' },
  ],
  verdictLabel: '2 answers needed',
  verdictTitle: 'Your skills match in part, but 2 lines in this posting could rule you out.',
  scoreLabel: 'Skills match',
  score: 74,
  fixes: [
    { title: 'Location: Austin hybrid attendance', tier: 'rule-out' },
    { title: 'Work permit: US work authorization', tier: 'rule-out' },
    { title: 'Kubernetes: experience from 2015 to 2017, too old', tier: 'serious' },
  ],
  detail: {
    fixIndex: 2,
    jobLabel: 'The job says',
    jobQuote: '3+ years of hands-on Kubernetes experience within the last 5 years.',
    cvLabel: 'Your CV says · 2015 to 2017',
    cvQuote: 'Deployed and operated microservices on K8s clusters.',
  },
  description:
    'Example report for a Platform Engineer posting and a sample CV. Verdict: 2 answers needed. ' +
    'Your skills match in part, but 2 lines in this posting could rule you out. Skills match: 74. ' +
    'Top fixes: Austin hybrid attendance; US work authorization; ' +
    'Kubernetes experience from 2015 to 2017 is too old.',
}
