import type { AlertItem } from '../adminTypes'

type Props = {
  alerts: AlertItem[]
  onStatus: (id: string, status: 'acknowledged' | 'resolved') => void
}

export default function AlertsPanel({ alerts, onStatus }: Props) {
  return (
    <section id="alerts" className="card">
      <div className="admin-panel-header">
        <h2 className="text-heading">Alerts</h2>
      </div>
      {!alerts.length ? (
        <p className="text-caption text-muted">No open alerts.</p>
      ) : (
        <table className="admin-panel-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Title</th>
              <th>Summary</th>
              <th>Last Seen</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((alert) => (
              <tr key={alert.id}>
                <td><span className={`badge ${alert.severity === 'critical' ? 'badge-danger' : 'badge-warning'}`}>{alert.severity}</span></td>
                <td>{alert.title}</td>
                <td>{alert.summary}</td>
                <td>{alert.last_seen_at}</td>
                <td>
                  <div className="admin-actions-inline">
                    <button className="btn btn-outline" onClick={() => onStatus(alert.id, 'acknowledged')}>Acknowledge</button>
                    <button className="btn btn-secondary" onClick={() => onStatus(alert.id, 'resolved')}>Resolve</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
