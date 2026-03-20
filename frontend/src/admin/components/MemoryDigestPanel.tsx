import type { ObservabilityDashboard } from '../adminTypes'

type Props = {
  memory: ObservabilityDashboard['memory_panels']
}

export default function MemoryDigestPanel({ memory }: Props) {
  const summary = memory.summary
  return (
    <section id="memory-digest" className="card">
      <div className="admin-panel-header">
        <h2 className="text-heading">Memory Digest</h2>
        <span className="text-caption text-muted">{memory.scope}</span>
      </div>
      <div className="admin-grid-cards" style={{ marginBottom: 16 }}>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-micro text-muted">Total Signals</span>
          <strong className="admin-stat-value">{summary.total_signals}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-micro text-muted">Stable Signals</span>
          <strong className="admin-stat-value">{summary.stable_signals}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-micro text-muted">Active Hypotheses</span>
          <strong className="admin-stat-value">{summary.active_hypotheses}</strong>
        </article>
        <article className="card admin-card-stat" style={{ marginBottom: 0 }}>
          <span className="text-micro text-muted">Tentative Hypotheses</span>
          <strong className="admin-stat-value">{summary.tentative_hypotheses}</strong>
        </article>
      </div>
      <div className="admin-grid-two">
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Top Signal Dimensions</strong></div>
          <div className="admin-chip-row">
            {memory.top_signal_dimensions.map((item) => (
              <span key={item.label} className="badge badge-warning">{item.label}: {item.count}</span>
            ))}
          </div>
          <table className="admin-panel-table" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Pattern</th>
                <th>Dimension</th>
                <th>Label</th>
                <th>Status</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {memory.top_signals.map((row, index) => (
                <tr key={`${String(row.canonical_label)}-${index}`}>
                  <td>{String(row.pattern_type ?? '')}</td>
                  <td>{String(row.dimension ?? '')}</td>
                  <td>{String(row.canonical_label ?? '')}</td>
                  <td>{String(row.status ?? '')}</td>
                  <td>{String(row.evidence_score ?? '')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Top Hypotheses</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Dimension</th>
                <th>Label</th>
                <th>Status</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {memory.top_hypotheses.map((row, index) => (
                <tr key={`${String(row.label)}-${index}`}>
                  <td>{String(row.dimension ?? '')}</td>
                  <td>{String(row.label ?? '')}</td>
                  <td>{String(row.status ?? '')}</td>
                  <td>{String(row.confidence ?? '')}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="admin-panel-header" style={{ marginTop: 16 }}>
            <strong>Reporting Bias</strong>
          </div>
          <table className="admin-panel-table">
            <tbody>
              {Object.entries(memory.reporting_bias).map(([key, value]) => (
                <tr key={key}>
                  <td>{key}</td>
                  <td>{value.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
