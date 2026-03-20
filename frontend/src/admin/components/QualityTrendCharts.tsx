import type { TrendPoint } from '../adminTypes'

type Props = {
  trends: Record<string, TrendPoint[]>
}

const LABELS: Record<string, string> = {
  unknown_cases: 'Unknown Cases',
  explicit_negative_feedback: 'Negative Feedback',
  degraded_errors: 'Degraded Errors',
  review_queue_new: 'Review Queue New',
}

export default function QualityTrendCharts({ trends }: Props) {
  return (
    <section id="quality-trends" className="card">
      <div className="admin-panel-header">
        <h2 className="text-heading">Quality Trends</h2>
      </div>
      <div className="admin-trends">
        {Object.entries(LABELS).map(([key, label]) => {
          const series = trends[key] ?? []
          const peak = Math.max(...series.map((point) => point.value), 0)
          return (
            <article key={key} className="card" style={{ marginBottom: 0 }}>
              <div className="admin-panel-header">
                <strong>{label}</strong>
                <span className="text-caption text-muted">{series.length} days</span>
              </div>
              <div className="admin-trend-bars">
                {series.map((point) => (
                  <div key={point.date} title={`${point.date}: ${point.value}`}>
                    <div
                      className="admin-trend-bar"
                      style={{ height: `${peak > 0 ? Math.max((point.value / peak) * 100, 3) : 3}%` }}
                    />
                  </div>
                ))}
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
