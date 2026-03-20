import type { SummaryCard } from '../adminTypes'

type Props = {
  cards: SummaryCard[]
}

export default function SummaryCards({ cards }: Props) {
  return (
    <section id="summary">
      <div className="admin-panel-header">
        <h2 className="text-heading">Summary</h2>
      </div>
      <div className="admin-grid-cards">
        {cards.map((card) => (
          <article key={card.key} className={`card admin-card-stat admin-status-${card.status}`}>
            <span className="text-micro text-muted">{card.title}</span>
            <strong className="admin-stat-value">{card.value}</strong>
            <span className="text-caption text-secondary">{card.subtitle}</span>
          </article>
        ))}
      </div>
    </section>
  )
}
