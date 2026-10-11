import { useState } from 'react'
import { TIER_LABELS, TIERS, type PriorityItem } from '../../lib/priorities'

interface FixListProps {
  items: PriorityItem[]
}

// How many items show before "Show more". Everything that could rule the candidate out always shows.
const FIRST_ITEMS = 5

export default function FixList({ items }: FixListProps) {
  const [toggled, setToggled] = useState<Record<string, boolean>>({})
  const [showAll, setShowAll] = useState(false)

  const ruleOut = items.filter((item) => item.tier === 'rule_out').length
  const limit = Math.max(FIRST_ITEMS, ruleOut)
  const visible = showAll ? items : items.slice(0, limit)
  const extra = items.length - limit

  return (
    <section className="rp-fix" aria-labelledby="fix-title">
      <div className="rp-fix-head">
        <div>
          <h2 id="fix-title" className="rp-h2">
            What to fix, most important first
          </h2>
          <p className="rp-muted">
            {items.length === 0
              ? 'Nothing to fix. Your CV backs what this posting asks.'
              : `${items.length} ${items.length === 1 ? 'thing' : 'things'}. Start at the top.`}
          </p>
        </div>
        {items.length > 0 && (
          <ul className="rp-legend" aria-label="What the colors mean">
            {TIERS.map((tier) => (
              <li key={tier} className={`rp-legend-item tier-${tier}`}>
                <span className="rp-legend-dot" aria-hidden="true" />
                {TIER_LABELS[tier]}
              </li>
            ))}
          </ul>
        )}
      </div>

      {items.length > 0 && (
        <ol className="rp-fix-list">
          {visible.map((item, index) => {
            const open = toggled[item.key] ?? index === 0
            return (
              <li key={item.key}>
                <FixItem
                  item={item}
                  number={index + 1}
                  open={open}
                  onToggle={() => setToggled((previous) => ({ ...previous, [item.key]: !open }))}
                />
              </li>
            )
          })}
        </ol>
      )}

      {/* The button stays after expanding, so the keyboard focus is never dropped. */}
      {extra > 0 && (
        <button
          type="button"
          className="rp-btn rp-btn-secondary rp-more"
          aria-expanded={showAll}
          onClick={() => setShowAll((previous) => !previous)}
        >
          {showAll ? 'Show fewer' : `Show ${extra} more`}
        </button>
      )}
    </section>
  )
}

interface FixItemProps {
  item: PriorityItem
  number: number
  open: boolean
  onToggle: () => void
}

function FixItem({ item, number, open, onToggle }: FixItemProps) {
  const panelId = `fix-${item.key}-panel`
  const titleId = `fix-${item.key}-title`
  const hasDetail = item.jobQuote !== null || item.cvQuote !== null || item.action !== ''
  return (
    <article className={`rp-item tier-${item.tier}`} aria-labelledby={titleId}>
      <div className="rp-item-head">
        <span className="rp-item-number" aria-hidden="true">
          {number}
        </span>
        <div className="rp-item-body">
          <p className="rp-item-tags">
            <span className="rp-pill">{TIER_LABELS[item.tier]}</span>
            <span className="rp-item-tag">{item.tag}</span>
          </p>
          <h3 id={titleId} className="rp-item-title">
            <span className="visually-hidden">{number}. </span>
            {item.title}
          </h3>
          <p className="rp-item-why">{item.why}</p>
        </div>
        {hasDetail && (
          <button
            type="button"
            className="rp-btn rp-btn-secondary rp-toggle"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={onToggle}
          >
            {open ? 'Hide' : 'See why'}
          </button>
        )}
      </div>

      {hasDetail && (
        <div className="rp-item-detail" id={panelId} hidden={!open}>
          <div className="rp-sides">
            <div className="rp-side">
              <p className="rp-side-label">The job says</p>
              <p className="rp-side-text">
                {item.jobQuote ? `"${item.jobQuote}"` : 'No exact sentence for this in the posting.'}
              </p>
            </div>
            <div className="rp-side">
              <p className="rp-side-label">
                Your CV says{item.cvQuote && item.cvSource ? ` · ${item.cvSource}` : ''}
              </p>
              <p className={item.cvQuote ? 'rp-side-text' : 'rp-side-text is-empty'}>
                {item.cvQuote ? `"${item.cvQuote}"` : 'Nothing in your CV mentions it.'}
              </p>
            </div>
          </div>
          {item.action !== '' && (
            <p className="rp-todo">
              <strong>What to do:</strong> <span>{item.action}</span>
            </p>
          )}
        </div>
      )}
    </article>
  )
}
