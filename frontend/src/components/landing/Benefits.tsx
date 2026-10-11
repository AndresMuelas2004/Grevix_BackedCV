import './Landing.css'

const ICON_PROPS = {
  width: 26,
  height: 26,
  viewBox: '0 0 24 24',
  fill: 'none',
  strokeWidth: 2.2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
  focusable: false,
} as const

export default function Benefits() {
  return (
    <section className="lp-benefits" aria-label="What the check does">
      <div className="lp-benefit">
        <svg {...ICON_PROPS} stroke="#B42318">
          <path d="M8 3h8l5 5v8l-5 5H8l-5-5V8z" />
          <path d="M12 8v5" />
          <path d="M12 16h.01" />
        </svg>
        <h2>Spots the hidden deal-breakers</h2>
        <p>
          Visa sponsorship, office days, a degree date window, experience that is too old. The
          lines screeners reject on without a word.
        </p>
      </div>
      <div className="lp-benefit">
        <svg {...ICON_PROPS} stroke="#B54708">
          <path d="M4 6h16" />
          <path d="M4 12h11" />
          <path d="M4 18h6" />
        </svg>
        <h2>Ranks what to fix first</h2>
        <p>
          Problems in order of how much they hurt, each with the posting's sentence next to your CV
          line and one thing to do.
        </p>
      </div>
      <div className="lp-benefit">
        <svg {...ICON_PROPS} stroke="#067647">
          <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />
          <path d="M9 12l2 2 4-4" />
        </svg>
        <h2>Never invents experience</h2>
        <p>
          Every edit cites a line of your CV. If an edit would stretch the truth, it is refused and
          you see why.
        </p>
      </div>
    </section>
  )
}
