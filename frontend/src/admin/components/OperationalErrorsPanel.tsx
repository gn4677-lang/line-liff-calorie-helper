import type { ObservabilityDashboard } from '../adminTypes'

type Props = {
  operational: ObservabilityDashboard['operational_panels']
}

export default function OperationalErrorsPanel({ operational }: Props) {
  return (
    <section id="operational-errors" className="card">
      <div className="admin-panel-header">
        <h2 className="text-heading">Operational Errors</h2>
      </div>
      <div className="admin-grid-two">
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Error by Component</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Component</th>
                <th>Total</th>
                <th>Critical</th>
                <th>Degraded</th>
                <th>Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {operational.error_by_component.map((row, index) => (
                <tr key={`${String(row.component)}-${index}`}>
                  <td>{String(row.component ?? '')}</td>
                  <td>{String(row.total_count ?? 0)}</td>
                  <td>{String(row.critical_count ?? 0)}</td>
                  <td>{String(row.degraded_count ?? 0)}</td>
                  <td>{String(row.last_seen_at ?? '')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="admin-panel-header"><strong>Top Error Codes</strong></div>
          <table className="admin-panel-table">
            <thead>
              <tr>
                <th>Error Code</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {operational.top_error_codes.map((row) => (
                <tr key={row.label}>
                  <td>{row.label}</td>
                  <td>{row.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
